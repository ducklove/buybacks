from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.dart_client import OpenDartClient, OpenDartNoData
    from scripts.buybacks.models import BuybackEvent, Company, TreasuryHoldingSnapshot, to_jsonable
    from scripts.buybacks.parsers import (
        dart_source_url,
        event_id,
        normalize_date,
        parse_number,
        parse_ratio_percent,
    )
else:
    from .dart_client import OpenDartClient, OpenDartNoData
    from .models import BuybackEvent, Company, TreasuryHoldingSnapshot, to_jsonable
    from .parsers import (
        dart_source_url,
        event_id,
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


def collect_dart_dataset(
    api_key: str,
    companies: Iterable[Company],
    bgn_de: str,
    end_de: str,
    years: Iterable[int],
    raw_dir: Path | None = None,
) -> tuple[list[Company], list[BuybackEvent], list[TreasuryHoldingSnapshot], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    hydrated_companies: list[Company] = []
    events: list[BuybackEvent] = []
    holdings: list[TreasuryHoldingSnapshot] = []
    warnings: list[str] = []

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
                events.append(normalize_decision_event(item, company.stock_code, endpoint))

        for year in years:
            for report_code in REPORT_CODES:
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
                for item in data.get("list", []):
                    holdings.append(normalize_holding_snapshot(item, company.stock_code, year, report_code))

    return hydrated_companies, events, holdings, warnings


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
        period_start = normalize_date(item.get("dpprd_bgd"))
        period_end = normalize_date(item.get("dpprd_edd"))
        method = clean_text(item.get("dp_mth"))
        purpose = clean_text(item.get("dp_pp"))
        broker = clean_text(item.get("cs_iv_bk"))
        holding_before_common = parse_number(item.get("dp_bf_ostk"))
        holding_before_ratio_common = parse_ratio_percent(item.get("dp_bf_ostk_rt"))
    else:
        planned_shares_common = None
        planned_shares_other = None
        planned_amount_krw = parse_number(item.get("ctr_prc") or item.get("trctr_prc"))
        period_start = normalize_date(item.get("trctr_bgd") or item.get("ctr_bgd"))
        period_end = normalize_date(item.get("trctr_edd") or item.get("ctr_edd"))
        method = "자기주식취득 신탁계약"
        purpose = clean_text(item.get("ctr_pp") or item.get("trctr_pp") or item.get("cc_pp"))
        broker = clean_text(item.get("trustee") or item.get("cs_iv_bk"))
        holding_before_common = None
        holding_before_ratio_common = None

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
) -> TreasuryHoldingSnapshot:
    ending_qty = parse_number(item.get("trmend_qy"))
    issued_shares = parse_number(item.get("isu_stock_totqy") or item.get("istc_totqy"))
    floating_shares = int(issued_shares - ending_qty) if issued_shares is not None and ending_qty is not None else None
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
