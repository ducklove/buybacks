from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.dart_client import OpenDartClient, OpenDartNoData
    from scripts.buybacks.models import BuybackEvent, Company, TreasuryHoldingSnapshot, to_jsonable
    from scripts.buybacks.parsers import (
        classify_event_type,
        dart_source_url,
        event_id,
        market_from_corp_cls,
        normalize_date,
        parse_number,
        parse_ratio_percent,
    )
else:
    from .dart_client import OpenDartClient, OpenDartNoData
    from .models import BuybackEvent, Company, TreasuryHoldingSnapshot, to_jsonable
    from .parsers import (
        classify_event_type,
        dart_source_url,
        event_id,
        market_from_corp_cls,
        normalize_date,
        parse_number,
        parse_ratio_percent,
    )

LOGGER = logging.getLogger(__name__)

DECISION_ENDPOINTS = {
    "tsstkAqDecsn.json": "direct_acquisition",
    "tsstkDpDecsn.json": "direct_disposition",
    "tsstkAqTrctrCnsDecsn.json": "trust_contract_start",
    "tsstkAqTrctrCcDecsn.json": "trust_contract_end",
}
REPORT_CODES = ["11011", "11014", "11012", "11013"]
BUYBACK_REPORT_KEYWORDS = [
    "자기주식취득",
    "자기주식 취득",
    "자기주식처분",
    "자기주식 처분",
    "자기주식취득신탁계약체결",
    "자기주식취득 신탁계약 체결",
    "자기주식취득신탁계약해지",
    "자기주식취득 신탁계약 해지",
    "주식소각결정",
    "주식 소각 결정",
    "자기주식소각",
    "자기주식 소각",
    "자기주식취득결정",
    "자기주식처분결정",
]


def collect_dart_dataset(
    api_key: str,
    companies: Iterable[Company],
    bgn_de: str,
    end_de: str,
    years: Iterable[int],
    raw_dir: Path | None = None,
    disclosure_items: Iterable[dict] | None = None,
) -> tuple[list[Company], list[BuybackEvent], list[TreasuryHoldingSnapshot], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    hydrated_companies: list[Company] = []
    events: list[BuybackEvent] = []
    holdings: list[TreasuryHoldingSnapshot] = []
    warnings: list[str] = []
    disclosures_by_corp: dict[str, list[dict]] = {}
    for item in disclosure_items or []:
        disclosures_by_corp.setdefault(str(item.get("corp_code") or ""), []).append(item)

    for company in companies:
        hydrated_companies.append(company)
        for endpoint in DECISION_ENDPOINTS:
            try:
                data = client.request_json(
                    endpoint,
                    {"corp_code": company.corp_code, "bgn_de": bgn_de, "end_de": end_de},
                )
            except OpenDartNoData:
                continue
            except Exception as exc:  # noqa: BLE001 - keep live collection resilient.
                warning = f"{company.stock_code} {endpoint} failed: {exc}"
                LOGGER.warning(warning)
                warnings.append(warning)
                continue
            for item in data.get("list", []):
                apply_market_from_item(company, item)
                events.append(normalize_decision_event(item, company.stock_code, endpoint))

        for year in years:
            for report_code in REPORT_CODES:
                stock_totals: list[dict] = []
                try:
                    stock_total_data = client.request_json(
                        "stockTotqySttus.json",
                        {
                            "corp_code": company.corp_code,
                            "bsns_year": str(year),
                            "reprt_code": report_code,
                        },
                    )
                    stock_totals = stock_total_data.get("list", [])
                    for item in stock_totals:
                        apply_market_from_item(company, item)
                except OpenDartNoData:
                    stock_totals = []
                except Exception as exc:  # noqa: BLE001
                    warning = f"{company.stock_code} stock totals {year}/{report_code} failed: {exc}"
                    LOGGER.warning(warning)
                    warnings.append(warning)
                try:
                    data = client.request_json(
                        "tesstkAcqsDspsSttus.json",
                        {
                            "corp_code": company.corp_code,
                            "bsns_year": str(year),
                            "reprt_code": report_code,
                        },
                    )
                except OpenDartNoData:
                    continue
                except Exception as exc:  # noqa: BLE001
                    warning = f"{company.stock_code} holdings {year}/{report_code} failed: {exc}"
                    LOGGER.warning(warning)
                    warnings.append(warning)
                    continue
                normalized = normalize_holding_rows(
                    data.get("list", []),
                    stock_totals,
                    company.stock_code,
                    year,
                    report_code,
                )
                holdings.extend(normalized)
                if not normalized:
                    holdings.extend(
                        normalize_stock_total_snapshots(stock_totals, company.stock_code, year, report_code)
                    )

        events.extend(
            normalize_disclosure_events(
                disclosures_by_corp.get(company.corp_code, []),
                company.stock_code,
                existing_rcept_nos={event.rcept_no for event in events if event.rcept_no},
            )
        )

    return hydrated_companies, dedupe_events(events), dedupe_holdings(holdings), warnings


def fetch_buyback_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    raw_dir: Path | None = None,
    page_limit: int = 20,
) -> tuple[list[dict], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    disclosures: list[dict] = []
    warnings: list[str] = []
    page_no = 1
    while page_no <= page_limit:
        try:
            data = client.request_json(
                "list.json",
                {
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "last_reprt_at": "Y",
                    "pblntf_ty": "B",
                    "sort": "date",
                    "sort_mth": "desc",
                    "page_no": str(page_no),
                    "page_count": "100",
                },
            )
        except OpenDartNoData:
            break
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"OpenDART disclosure search failed on page {page_no}: {exc}")
            break

        page_rows = [item for item in data.get("list", []) if is_buyback_report(item.get("report_nm"))]
        disclosures.extend(page_rows)

        total_page = int(parse_number(data.get("total_page")) or 1)
        if page_no >= total_page:
            break
        page_no += 1

    return dedupe_disclosures(disclosures), warnings


def normalize_decision_event(item: dict, stock_code: str, endpoint: str) -> BuybackEvent:
    event_type = DECISION_ENDPOINTS[endpoint]
    disclosure_date = normalize_date(item.get("rcept_dt")) or normalize_date(item.get("bddd")) or date.today().isoformat()
    rcept_no = item.get("rcept_no")

    if event_type == "direct_acquisition":
        planned_shares_common = parse_number(item.get("aqpln_stk_ostk"))
        planned_shares_other = parse_number(item.get("aqpln_stk_estk"))
        planned_amount_krw = parse_number(item.get("aqpln_prc_ostk"))
        period_start = normalize_date(item.get("aqexpd_bgd"))
        period_end = normalize_date(item.get("aqexpd_edd"))
        method = clean_text(item.get("aq_mth"))
        purpose = clean_text(item.get("aq_pp"))
        broker = clean_text(item.get("cs_iv_bk"))
        holding_before_common = parse_number(item.get("aq_wtn_div_ostk"))
        holding_before_ratio_common = parse_ratio_percent(item.get("aq_wtn_div_ostk_rt"))
    elif event_type == "direct_disposition":
        planned_shares_common = parse_number(item.get("dppln_stk_ostk"))
        planned_shares_other = parse_number(item.get("dppln_stk_estk"))
        planned_amount_krw = parse_number(item.get("dppln_prc_ostk"))
        period_start = normalize_date(item.get("dpprpd_bgd") or item.get("dpprd_bgd"))
        period_end = normalize_date(item.get("dpprpd_edd") or item.get("dpprd_edd"))
        method = disposition_method(item)
        purpose = clean_text(item.get("dp_pp"))
        broker = clean_text(item.get("cs_iv_bk"))
        holding_before_common = parse_number(item.get("aq_wtn_div_ostk") or item.get("dp_bf_ostk"))
        holding_before_ratio_common = parse_ratio_percent(item.get("aq_wtn_div_ostk_rt") or item.get("dp_bf_ostk_rt"))
    else:
        planned_shares_common = None
        planned_shares_other = None
        planned_amount_krw = parse_number(item.get("ctr_prc") or item.get("ctr_prc_bfcc") or item.get("trctr_prc"))
        period_start = normalize_date(item.get("ctr_pd_bgd") or item.get("ctr_pd_bfcc_bgd") or item.get("trctr_bgd"))
        period_end = normalize_date(item.get("ctr_pd_edd") or item.get("ctr_pd_bfcc_edd") or item.get("trctr_edd"))
        method = "자기주식취득 신탁계약"
        purpose = clean_text(item.get("ctr_pp") or item.get("trctr_pp") or item.get("cc_pp"))
        broker = clean_text(item.get("ctr_cns_int") or item.get("cc_int") or item.get("trustee") or item.get("cs_iv_bk"))
        holding_before_common = parse_number(item.get("aq_wtn_div_ostk"))
        holding_before_ratio_common = parse_ratio_percent(item.get("aq_wtn_div_ostk_rt"))

    return BuybackEvent(
        event_id=event_id("DART", rcept_no, stock_code, event_type, disclosure_date),
        corp_code=item.get("corp_code", ""),
        stock_code=stock_code,
        corp_name=item.get("corp_name", ""),
        event_type=event_type,  # type: ignore[arg-type]
        disclosure_date=disclosure_date,
        decision_date=normalize_date(item.get("bdtm") or item.get("decide_dt") or item.get("bddd")),
        period_start=period_start,
        period_end=period_end,
        planned_shares_common=planned_shares_common,
        planned_shares_other=planned_shares_other,
        planned_amount_krw=planned_amount_krw,
        actual_shares=None,
        actual_amount_krw=None,
        method=method,
        purpose=purpose,
        broker=broker,
        holding_before_common=holding_before_common,
        holding_before_ratio_common=holding_before_ratio_common,
        source="DART",
        rcept_no=rcept_no,
        source_url=dart_source_url(rcept_no),
        raw_report_name=item.get("report_nm"),
    )


def normalize_holding_snapshot(
    item: dict,
    stock_code: str,
    report_year: int,
    report_code: str,
    stock_total: dict | None = None,
) -> TreasuryHoldingSnapshot:
    ending_qty = parse_number(item.get("trmend_qy"))
    issued_shares = parse_number(
        item.get("isu_stock_totqy")
        or item.get("istc_totqy")
        or (stock_total or {}).get("istc_totqy")
        or (stock_total or {}).get("now_to_isu_stock_totqy")
    )
    if ending_qty is None:
        ending_qty = parse_number((stock_total or {}).get("tesstk_co"))
    if issued_shares is None:
        issued_shares = parse_number((stock_total or {}).get("distb_stock_co"))
    floating_shares = int(issued_shares - ending_qty) if issued_shares is not None and ending_qty is not None else None
    if (stock_total or {}).get("distb_stock_co") is not None:
        floating_shares = as_int(parse_number((stock_total or {}).get("distb_stock_co")))
    treasury_ratio = float(ending_qty) / float(issued_shares) if issued_shares and ending_qty is not None else None
    return TreasuryHoldingSnapshot(
        corp_code=item.get("corp_code", ""),
        stock_code=stock_code,
        corp_name=item.get("corp_name", ""),
        as_of_date=normalize_date(item.get("stlm_dt")) or f"{report_year}-12-31",
        report_year=report_year,
        report_code=report_code,
        stock_kind=item.get("stock_knd") or "",
        beginning_qty=as_int(parse_number(item.get("bsis_qy"))),
        acquired_qty=as_int(parse_number(item.get("change_qy_acqs"))),
        disposed_qty=as_int(parse_number(item.get("change_qy_dsps"))),
        retired_qty=as_int(parse_number(item.get("change_qy_incnr"))),
        ending_qty=as_int(ending_qty),
        issued_shares=as_int(issued_shares),
        treasury_ratio=treasury_ratio,
        floating_shares=floating_shares,
        source_rcept_no=item.get("rcept_no"),
    )


def normalize_holding_rows(
    rows: list[dict],
    stock_totals: list[dict],
    stock_code: str,
    report_year: int,
    report_code: str,
) -> list[TreasuryHoldingSnapshot]:
    selected_rows = select_holding_rows(rows)
    snapshots: list[TreasuryHoldingSnapshot] = []
    for row in selected_rows:
        stock_total = best_stock_total(row.get("stock_knd"), stock_totals)
        snapshots.append(normalize_holding_snapshot(row, stock_code, report_year, report_code, stock_total))
    return snapshots


def normalize_stock_total_snapshots(
    stock_totals: list[dict],
    stock_code: str,
    report_year: int,
    report_code: str,
) -> list[TreasuryHoldingSnapshot]:
    snapshots: list[TreasuryHoldingSnapshot] = []
    for item in select_stock_total_rows(stock_totals):
        ending_qty = parse_number(item.get("tesstk_co"))
        issued_shares = parse_number(item.get("istc_totqy"))
        if ending_qty is None and issued_shares is None:
            continue
        snapshots.append(
            TreasuryHoldingSnapshot(
                corp_code=item.get("corp_code", ""),
                stock_code=stock_code,
                corp_name=item.get("corp_name", ""),
                as_of_date=normalize_date(item.get("stlm_dt")) or f"{report_year}-12-31",
                report_year=report_year,
                report_code=report_code,
                stock_kind=item.get("se") or "보통주",
                beginning_qty=None,
                acquired_qty=None,
                disposed_qty=None,
                retired_qty=None,
                ending_qty=as_int(ending_qty),
                issued_shares=as_int(issued_shares),
                treasury_ratio=float(ending_qty) / float(issued_shares) if issued_shares and ending_qty is not None else None,
                floating_shares=as_int(parse_number(item.get("distb_stock_co"))),
                source_rcept_no=item.get("rcept_no"),
            )
        )
    return snapshots


def normalize_disclosure_events(
    items: list[dict],
    stock_code: str,
    existing_rcept_nos: set[str | None],
) -> list[BuybackEvent]:
    events: list[BuybackEvent] = []
    for item in items:
        rcept_no = item.get("rcept_no")
        if rcept_no in existing_rcept_nos:
            continue
        report_name = item.get("report_nm")
        event_type = classify_event_type(report_name)
        if event_type == "unknown":
            continue
        disclosure_date = normalize_date(item.get("rcept_dt")) or date.today().isoformat()
        events.append(
            BuybackEvent(
                event_id=event_id("DART", rcept_no, stock_code, event_type, disclosure_date),
                corp_code=item.get("corp_code", ""),
                stock_code=stock_code,
                corp_name=item.get("corp_name", ""),
                event_type=event_type,
                disclosure_date=disclosure_date,
                decision_date=None,
                period_start=None,
                period_end=None,
                planned_shares_common=None,
                planned_shares_other=None,
                planned_amount_krw=None,
                actual_shares=None,
                actual_amount_krw=None,
                method=None,
                purpose=None,
                broker=None,
                holding_before_common=None,
                holding_before_ratio_common=None,
                source="DART",
                rcept_no=rcept_no,
                source_url=dart_source_url(rcept_no),
                raw_report_name=report_name,
            )
        )
    return events


def select_holding_rows(rows: list[dict]) -> list[dict]:
    listed = [row for row in rows if row.get("stock_knd")]
    if not listed:
        return []
    totals = [row for row in listed if is_total_holding_row(row)]
    source_rows = totals or [row for row in listed if not is_subtotal_holding_row(row)] or listed
    best_by_kind: dict[str, dict] = {}
    for row in source_rows:
        key = normalize_stock_kind(row.get("stock_knd"))
        previous = best_by_kind.get(key)
        if previous is None or holding_row_score(row) > holding_row_score(previous):
            best_by_kind[key] = row
    return list(best_by_kind.values())


def select_stock_total_rows(rows: list[dict]) -> list[dict]:
    valid = [row for row in rows if normalize_stock_kind(row.get("se")) not in {"합계", "비고", ""}]
    return valid or rows[:1]


def best_stock_total(stock_kind: object, stock_totals: list[dict]) -> dict | None:
    wanted = normalize_stock_kind(stock_kind)
    if not stock_totals:
        return None
    for row in stock_totals:
        if normalize_stock_kind(row.get("se")) == wanted:
            return row
    if "보통" in wanted:
        for row in stock_totals:
            if "보통" in normalize_stock_kind(row.get("se")):
                return row
    return next((row for row in stock_totals if normalize_stock_kind(row.get("se")) not in {"합계", "비고", ""}), stock_totals[0])


def is_buyback_report(report_name: object) -> bool:
    text = str(report_name or "")
    return any(keyword in text for keyword in BUYBACK_REPORT_KEYWORDS)


def dedupe_disclosures(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for item in items:
        key = str(item.get("rcept_no") or f"{item.get('corp_code')}-{item.get('report_nm')}-{item.get('rcept_dt')}")
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def dedupe_events(events: list[BuybackEvent]) -> list[BuybackEvent]:
    seen: set[str] = set()
    output: list[BuybackEvent] = []
    for event in sorted(events, key=lambda item: (item.disclosure_date, item.event_id), reverse=True):
        key = event.rcept_no or event.event_id
        typed_key = f"{key}:{event.event_type}"
        if typed_key in seen:
            continue
        seen.add(typed_key)
        output.append(event)
    return output


def dedupe_holdings(snapshots: list[TreasuryHoldingSnapshot]) -> list[TreasuryHoldingSnapshot]:
    seen: set[tuple[str, str, int, str, str]] = set()
    output: list[TreasuryHoldingSnapshot] = []
    for snapshot in sorted(
        snapshots,
        key=lambda item: (item.as_of_date, item.stock_code, item.report_code, item.stock_kind),
        reverse=True,
    ):
        key = (
            snapshot.stock_code,
            snapshot.as_of_date,
            snapshot.report_year,
            snapshot.report_code,
            normalize_stock_kind(snapshot.stock_kind),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(snapshot)
    return output


def is_total_holding_row(row: dict) -> bool:
    fields = [row.get("acqs_mth1"), row.get("acqs_mth2"), row.get("acqs_mth3")]
    return any(str(value or "").strip() in {"총계", "합계"} for value in fields)


def is_subtotal_holding_row(row: dict) -> bool:
    fields = [row.get("acqs_mth1"), row.get("acqs_mth2"), row.get("acqs_mth3")]
    return any(str(value or "").strip() in {"총계", "합계", "소계"} for value in fields)


def holding_row_score(row: dict) -> int:
    score = 0
    for index, field in enumerate(["acqs_mth3", "acqs_mth2", "acqs_mth1"]):
        value = str(row.get(field) or "").strip()
        if value in {"총계", "합계"}:
            score += 10 - index
        elif value == "소계":
            score += 4 - index
    return score


def normalize_stock_kind(value: object) -> str:
    text = str(value or "").replace(" ", "")
    if "보통" in text:
        return "보통주"
    if "우선" in text:
        return "우선주"
    return text


def disposition_method(item: dict) -> str | None:
    parts = []
    labels = [
        ("시장매도", "dp_m_mkt"),
        ("시간외대량매매", "dp_m_ovtm"),
        ("장외처분", "dp_m_otc"),
        ("기타", "dp_m_etc"),
    ]
    for label, key in labels:
        amount = parse_number(item.get(key))
        if amount:
            parts.append(f"{label} {as_int(amount):,}주")
    return ", ".join(parts) if parts else clean_text(item.get("dp_mth"))


def apply_market_from_item(company: Company, item: dict) -> None:
    market = market_from_corp_cls(item.get("corp_cls"))
    if market != "OTHER":
        company.market = market


def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_int(value: int | float | None) -> int | None:
    return int(value) if value is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", type=Path, default=Path("data/fixtures/buybacks/companies.json"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/buybacks/dart_buybacks.json"))
    parser.add_argument("--start", default="20250101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--years", default=str(date.today().year - 1))
    args = parser.parse_args()
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART_API_KEY is required")
    companies = [Company(**item) for item in json.loads(args.companies.read_text(encoding="utf-8"))]
    years = [int(part) for part in args.years.split(",") if part]
    payload = collect_dart_dataset(api_key, companies, args.start, args.end, years, Path("data/raw/buybacks"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
