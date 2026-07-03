from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.dart_client import OpenDartClient, OpenDartNoData
    from scripts.buybacks.models import Company, DividendRecord
    from scripts.buybacks.parsers import MISSING_VALUES, parse_number, parse_ratio_percent
else:
    from .dart_client import OpenDartClient, OpenDartNoData
    from .models import Company, DividendRecord
    from .parsers import MISSING_VALUES, parse_number, parse_ratio_percent

LOGGER = logging.getLogger(__name__)

# alotMatter.json (정기보고서 주요정보 - 배당에 관한 사항) is an annual matter;
# the annual report (11011) is the only report code collected by default.
DIVIDEND_REPORT_CODES = ["11011"]

# Maps logical field names to ordered OpenDART response field-name candidates,
# mirroring FIELD_ALIASES in fetch_dart_buybacks.py: a DART schema rename only
# requires adding a candidate here. Order matters — first present value wins.
DIVIDEND_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "row_label": ("se",),
    "stock_kind": ("stock_knd", "stock_kind"),
    "current_term_value": ("thstrm", "thstrm_amount", "thstrm_dd"),
}

# Totals and net income are reported in 백만원 by the alotMatter API contract;
# the multiplier is still re-derived from the row label when one is present.
DEFAULT_AMOUNT_MULTIPLIER = 1_000_000
# Ordered by token specificity: "백만원" must match before the bare "원".
UNIT_MULTIPLIER_TOKENS: tuple[tuple[str, int], ...] = (
    ("백만원", 1_000_000),
    ("억원", 100_000_000),
    ("천원", 1_000),
    ("원", 1),
)

# Records with both cash-dividend fields null beyond this ratio trigger a
# warning: a silent DART label/field rename should surface in data_status.
DIVIDEND_NULL_RATIO_THRESHOLD = 0.5


def is_missing_field_value(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() in MISSING_VALUES


def get_dividend_aliased(item: dict | None, logical_name: str) -> object | None:
    """Return the first present value for a logical field via DIVIDEND_FIELD_ALIASES."""
    candidates = DIVIDEND_FIELD_ALIASES[logical_name]
    if not item:
        return None
    for field in candidates:
        value = item.get(field)
        if is_missing_field_value(value):
            continue
        return value
    return None


def compact_label(value: object) -> str:
    return str(value or "").replace(" ", "")


def classify_dividend_row(label: object) -> str | None:
    """Classify an alotMatter 구분(se) label into a logical row name.

    Only the rows the dataset stores are classified; everything else
    (주당액면가액, 주식배당, 배당수익률 rows, ...) returns None.
    """
    compact = compact_label(label)
    if not compact:
        return None
    if "현금배당성향" in compact:
        return "payout_ratio"
    if "현금배당금총액" in compact:
        return "cash_dividend_total"
    if "수익률" in compact:
        return None
    if "주당" in compact and "현금배당금" in compact:
        return "dps"
    if "당기순이익" in compact and "주당" not in compact:
        return "net_income"
    return None


def unit_multiplier_from_label(label: object, default: int) -> int:
    """Derive the KRW multiplier from a row label like "현금배당금총액(백만원)"."""
    compact = compact_label(label)
    for token, multiplier in UNIT_MULTIPLIER_TOKENS:
        if token in compact:
            return multiplier
    return default


def is_common_dividend_kind(row: dict, label: object) -> bool:
    kind = compact_label(get_dividend_aliased(row, "stock_kind")) + compact_label(label)
    return "보통" in kind


def is_preferred_dividend_kind(row: dict, label: object) -> bool:
    kind = compact_label(get_dividend_aliased(row, "stock_kind")) + compact_label(label)
    return "우선" in kind


def select_common_dps(candidates: list[tuple[dict, object]]) -> int | float | None:
    """Pick the common-share 주당 현금배당금 among per-share rows.

    Preference: explicit 보통주 rows, then rows that are not 우선주, then any
    parsable row (legacy responses without a stock kind column).
    """
    scored: list[tuple[int, int, int | float]] = []
    for order, (row, label) in enumerate(candidates):
        value = parse_number(get_dividend_aliased(row, "current_term_value"))
        if value is None:
            continue
        value = value * unit_multiplier_from_label(label, 1)
        if is_common_dividend_kind(row, label):
            score = 2
        elif not is_preferred_dividend_kind(row, label):
            score = 1
        else:
            score = 0
        scored.append((score, -order, value))
    if not scored:
        return None
    scored.sort(reverse=True)
    if scored[0][0] == 0:
        # Every parsable row is an explicit preferred-share row; the common dividend is unknown.
        return None
    return scored[0][2]


def select_net_income(candidates: list[tuple[object, int | float]]) -> int | float | None:
    """Prefer the consolidated (연결) net income row; fall back to the first row."""
    for label, value in candidates:
        if "연결" in compact_label(label):
            return value
    return candidates[0][1] if candidates else None


def normalize_dividend_record(
    rows: list[dict],
    company: Company,
    bsns_year: int,
    report_code: str,
) -> DividendRecord | None:
    dps_candidates: list[tuple[dict, object]] = []
    net_income_candidates: list[tuple[object, int | float]] = []
    cash_dividend_total: int | float | None = None
    payout_ratio: float | None = None
    rcept_no: str | None = None
    corp_name = company.corp_name

    for row in rows:
        rcept_no = rcept_no or row.get("rcept_no")
        corp_name = str(row.get("corp_name") or corp_name)
        label = get_dividend_aliased(row, "row_label")
        kind = classify_dividend_row(label)
        if kind is None:
            continue
        raw_value = get_dividend_aliased(row, "current_term_value")
        if kind == "dps":
            dps_candidates.append((row, label))
        elif kind == "cash_dividend_total" and cash_dividend_total is None:
            value = parse_number(raw_value)
            if value is not None:
                cash_dividend_total = value * unit_multiplier_from_label(label, DEFAULT_AMOUNT_MULTIPLIER)
        elif kind == "payout_ratio" and payout_ratio is None:
            payout_ratio = parse_ratio_percent(raw_value)
        elif kind == "net_income":
            value = parse_number(raw_value)
            if value is not None:
                net_income_candidates.append((label, value * unit_multiplier_from_label(label, DEFAULT_AMOUNT_MULTIPLIER)))

    dps_common = select_common_dps(dps_candidates)
    net_income = select_net_income(net_income_candidates)
    if dps_common is None and cash_dividend_total is None and payout_ratio is None and net_income is None:
        return None
    return DividendRecord(
        corp_code=company.corp_code,
        stock_code=company.stock_code,
        corp_name=corp_name,
        bsns_year=int(bsns_year),
        report_code=report_code,
        dps_common_krw=dps_common,
        cash_dividend_total_krw=cash_dividend_total,
        payout_ratio=payout_ratio,
        net_income_krw=net_income,
        rcept_no=rcept_no,
    )


def collect_dividend_records(
    api_key: str,
    companies: Iterable[Company],
    years: Iterable[int],
    raw_dir: Path | None = None,
    report_codes: Iterable[str] | None = None,
) -> tuple[list[DividendRecord], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    company_list = list(companies)
    years_to_fetch = list(years)
    report_codes_to_fetch = list(report_codes or DIVIDEND_REPORT_CODES)
    records: list[DividendRecord] = []
    warnings: list[str] = []

    for index, company in enumerate(company_list, start=1):
        if index == 1 or index % 100 == 0 or index == len(company_list):
            LOGGER.info("collecting dividend records %d/%d", index, len(company_list))
        for year in years_to_fetch:
            for report_code in report_codes_to_fetch:
                try:
                    data = client.request_json(
                        "alotMatter.json",
                        {
                            "corp_code": company.corp_code,
                            "bsns_year": str(year),
                            "reprt_code": report_code,
                        },
                    )
                except OpenDartNoData:
                    continue
                except Exception as exc:  # noqa: BLE001 - keep live collection resilient.
                    warning = f"{company.stock_code} dividends {year}/{report_code} failed: {exc}"
                    LOGGER.warning(warning)
                    warnings.append(warning)
                    continue
                record = normalize_dividend_record(data.get("list", []), company, year, report_code)
                if record is not None:
                    records.append(record)
                    break  # First report code with data wins for this year.

    deduped = merge_dividends([], records)
    warnings.extend(dividend_coverage_warnings(deduped))
    return deduped, warnings


def merge_dividends(
    existing: list[DividendRecord],
    incoming: list[DividendRecord],
) -> list[DividendRecord]:
    """Merge dividend records by (corp_code, bsns_year); incoming rows win."""
    by_key: dict[tuple[str, int], DividendRecord] = {}
    for record in [*existing, *incoming]:
        by_key[(record.corp_code, record.bsns_year)] = record
    return sorted(by_key.values(), key=lambda item: (item.stock_code, item.bsns_year, item.corp_code))


def dividend_coverage_warnings(
    records: list[DividendRecord],
    threshold: float = DIVIDEND_NULL_RATIO_THRESHOLD,
) -> list[str]:
    """Warn when too many collected records have every cash-dividend field null.

    Catches silent alotMatter label/field renames that would otherwise produce
    structurally valid but empty rows (mirrors core_field_coverage_warnings).
    """
    total = len(records)
    if total == 0:
        return []
    null_count = sum(
        1
        for record in records
        if record.dps_common_krw is None and record.cash_dividend_total_krw is None
    )
    ratio = null_count / total
    if ratio < threshold:
        return []
    warning = (
        f"{null_count}/{total} ({ratio:.0%}) dividend records have both dps_common_krw and "
        "cash_dividend_total_krw null; OpenDART alotMatter labels/fields may have changed "
        "(check DIVIDEND_FIELD_ALIASES and classify_dividend_row)."
    )
    LOGGER.warning(warning)
    return [warning]
