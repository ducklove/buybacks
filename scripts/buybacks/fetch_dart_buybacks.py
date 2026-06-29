from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
EVENT_TYPE_TO_ENDPOINT = {event_type: endpoint for endpoint, event_type in DECISION_ENDPOINTS.items()}
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
BUYBACK_DISCLOSURE_TYPES = ["B", "I"]
DART_MAIN_URL = "https://dart.fss.or.kr/dsaf001/main.do"
DART_VIEWER_URL = "https://dart.fss.or.kr/report/viewer.do"


def collect_dart_dataset(
    api_key: str,
    companies: Iterable[Company],
    bgn_de: str,
    end_de: str,
    years: Iterable[int],
    raw_dir: Path | None = None,
    disclosure_items: Iterable[dict] | None = None,
    report_codes: Iterable[str] | None = None,
    include_holdings: bool = True,
) -> tuple[list[Company], list[BuybackEvent], list[TreasuryHoldingSnapshot], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    hydrated_companies: list[Company] = []
    events: list[BuybackEvent] = []
    holdings: list[TreasuryHoldingSnapshot] = []
    warnings: list[str] = []
    disclosures_by_corp: dict[str, list[dict]] = {}
    for item in disclosure_items or []:
        disclosures_by_corp.setdefault(str(item.get("corp_code") or ""), []).append(item)
    years_to_fetch = list(years)
    report_codes_to_fetch = list(report_codes or REPORT_CODES)

    for company in companies:
        hydrated_companies.append(company)
        for endpoint in decision_endpoints_for_company(disclosures_by_corp.get(company.corp_code, [])):
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

        if include_holdings:
            company_holdings, holding_warnings = collect_company_holding_snapshots(
                client,
                company,
                years_to_fetch,
                report_codes_to_fetch,
            )
            holdings.extend(company_holdings)
            warnings.extend(holding_warnings)

        events.extend(
            normalize_disclosure_events(
                disclosures_by_corp.get(company.corp_code, []),
                company.stock_code,
                existing_rcept_nos={event.rcept_no for event in events if event.rcept_no},
                retirement_details_by_rcept_no=collect_retirement_details(
                    disclosures_by_corp.get(company.corp_code, []),
                    raw_dir=raw_dir,
                    warnings=warnings,
                ),
            )
        )

    return hydrated_companies, dedupe_events(events), dedupe_holdings(holdings), warnings


def collect_dart_holding_snapshots(
    api_key: str,
    companies: Iterable[Company],
    years: Iterable[int],
    raw_dir: Path | None = None,
    report_codes: Iterable[str] | None = None,
    include_treasury_tables: bool = True,
) -> tuple[list[TreasuryHoldingSnapshot], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    company_list = list(companies)
    years_to_fetch = list(years)
    report_codes_to_fetch = list(report_codes or REPORT_CODES)
    holdings: list[TreasuryHoldingSnapshot] = []
    warnings: list[str] = []

    for index, company in enumerate(company_list, start=1):
        if index == 1 or index % 100 == 0 or index == len(company_list):
            print(f"collecting holding snapshots {index}/{len(company_list)}", flush=True)
        company_holdings, holding_warnings = collect_company_holding_snapshots(
            client,
            company,
            years_to_fetch,
            report_codes_to_fetch,
            include_treasury_tables=include_treasury_tables,
        )
        holdings.extend(company_holdings)
        warnings.extend(holding_warnings)

    return dedupe_holdings(holdings), warnings


def collect_company_holding_snapshots(
    client: OpenDartClient,
    company: Company,
    years: Iterable[int],
    report_codes: Iterable[str],
    include_treasury_tables: bool = True,
) -> tuple[list[TreasuryHoldingSnapshot], list[str]]:
    holdings: list[TreasuryHoldingSnapshot] = []
    warnings: list[str] = []

    for year in years:
        for report_code in report_codes:
            rows: list[dict] = []
            if include_treasury_tables:
                try:
                    data = client.request_json(
                        "tesstkAcqsDspsSttus.json",
                        {
                            "corp_code": company.corp_code,
                            "bsns_year": str(year),
                            "reprt_code": report_code,
                        },
                    )
                    rows = data.get("list", [])
                    for item in rows:
                        apply_market_from_item(company, item)
                except OpenDartNoData:
                    rows = []
                except Exception as exc:  # noqa: BLE001
                    warning = f"{company.stock_code} holdings {year}/{report_code} failed: {exc}"
                    LOGGER.warning(warning)
                    warnings.append(warning)

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

            normalized = normalize_holding_rows(
                rows,
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

    return holdings, warnings


def decision_endpoints_for_company(disclosures: list[dict]) -> list[str]:
    if not disclosures:
        return []
    hinted_types = {classify_event_type(item.get("report_nm")) for item in disclosures}
    endpoints = [
        EVENT_TYPE_TO_ENDPOINT[event_type]
        for event_type in [
            "direct_acquisition",
            "direct_disposition",
            "trust_contract_start",
            "trust_contract_end",
        ]
        if event_type in hinted_types
    ]
    return endpoints


def fetch_buyback_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    raw_dir: Path | None = None,
    page_limit: int = 20,
    disclosure_types: Iterable[str] | None = None,
) -> tuple[list[dict], list[str]]:
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    disclosures: list[dict] = []
    warnings: list[str] = []
    for disclosure_type in list(disclosure_types or BUYBACK_DISCLOSURE_TYPES):
        page_no = 1
        while page_no <= page_limit:
            try:
                data = client.request_json(
                    "list.json",
                    {
                        "bgn_de": bgn_de,
                        "end_de": end_de,
                        "last_reprt_at": "Y",
                        "pblntf_ty": disclosure_type,
                        "sort": "date",
                        "sort_mth": "desc",
                        "page_no": str(page_no),
                        "page_count": "100",
                    },
                )
            except OpenDartNoData:
                break
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    f"OpenDART disclosure search failed for pblntf_ty={disclosure_type} page {page_no}: {exc}"
                )
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
    rcept_no = item.get("rcept_no")
    disclosure_date = (
        normalize_date(item.get("rcept_dt"))
        or receipt_date_from_no(rcept_no)
        or normalize_date(item.get("bddd"))
        or date.today().isoformat()
    )

    if event_type == "direct_acquisition":
        planned_shares_common = parse_number(item.get("aqpln_stk_ostk"))
        planned_shares_other = parse_number(item.get("aqpln_stk_estk"))
        planned_amount_common_krw = parse_number(item.get("aqpln_prc_ostk"))
        planned_amount_other_krw = parse_number(item.get("aqpln_prc_estk"))
        planned_amount_krw = sum_optional(planned_amount_common_krw, planned_amount_other_krw)
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
        planned_amount_common_krw = parse_number(item.get("dppln_prc_ostk"))
        planned_amount_other_krw = parse_number(item.get("dppln_prc_estk"))
        planned_amount_krw = sum_optional(planned_amount_common_krw, planned_amount_other_krw)
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
        planned_amount_common_krw = planned_amount_krw
        planned_amount_other_krw = None
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
        planned_amount_common_krw=planned_amount_common_krw,
        planned_amount_other_krw=planned_amount_other_krw,
        planned_share_ratio_common=None,
        planned_share_ratio_other=None,
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
        stock_kind=clean_stock_kind(item.get("stock_knd")),
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
    retirement_details_by_rcept_no: dict[str, dict] | None = None,
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
        details = (retirement_details_by_rcept_no or {}).get(str(rcept_no or ""), {})
        disclosure_date = normalize_date(item.get("rcept_dt")) or receipt_date_from_no(rcept_no) or date.today().isoformat()
        events.append(
            BuybackEvent(
                event_id=event_id("DART", rcept_no, stock_code, event_type, disclosure_date),
                corp_code=item.get("corp_code", ""),
                stock_code=stock_code,
                corp_name=item.get("corp_name", ""),
                event_type=event_type,
                disclosure_date=disclosure_date,
                decision_date=details.get("decision_date"),
                period_start=details.get("period_start"),
                period_end=details.get("period_end"),
                planned_shares_common=details.get("planned_shares_common"),
                planned_shares_other=details.get("planned_shares_other"),
                planned_amount_krw=details.get("planned_amount_krw"),
                planned_amount_common_krw=details.get("planned_amount_common_krw"),
                planned_amount_other_krw=details.get("planned_amount_other_krw"),
                planned_share_ratio_common=details.get("planned_share_ratio_common"),
                planned_share_ratio_other=details.get("planned_share_ratio_other"),
                actual_shares=None,
                actual_amount_krw=None,
                method=details.get("method"),
                purpose=details.get("purpose"),
                broker=details.get("broker"),
                holding_before_common=None,
                holding_before_ratio_common=None,
                source="DART",
                rcept_no=rcept_no,
                source_url=dart_source_url(rcept_no),
                raw_report_name=report_name,
            )
        )
    return events


def collect_retirement_details(
    disclosures: list[dict],
    raw_dir: Path | None = None,
    warnings: list[str] | None = None,
) -> dict[str, dict]:
    details: dict[str, dict] = {}
    for item in disclosures:
        if classify_event_type(item.get("report_nm")) != "retirement":
            continue
        rcept_no = str(item.get("rcept_no") or "")
        if not rcept_no:
            continue
        try:
            html = fetch_dart_viewer_html(rcept_no, raw_dir=raw_dir)
        except Exception as exc:  # noqa: BLE001 - keep collection resilient.
            warning = f"{rcept_no} retirement detail fetch failed: {exc}"
            LOGGER.warning(warning)
            if warnings is not None:
                warnings.append(warning)
            continue
        parsed = parse_retirement_details_from_html(html)
        if parsed:
            details[rcept_no] = parsed
    return details


def fetch_dart_viewer_html(rcept_no: str, raw_dir: Path | None = None) -> str:
    cache_path = raw_dir / "dart_viewers" / f"{rcept_no}.html" if raw_dir else None
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    main_html = decode_html(fetch_url(f"{DART_MAIN_URL}?{urlencode({'rcpNo': rcept_no})}"))
    match = re.search(
        r"viewDoc\(\s*['\"](?P<rcp_no>\d+)['\"]\s*,\s*['\"](?P<dcm_no>\d+)['\"]\s*,\s*['\"](?P<ele_id>\d+)['\"]\s*,\s*['\"](?P<offset>\d+)['\"]\s*,\s*['\"](?P<length>\d+)['\"]\s*,\s*['\"](?P<dtd>[^'\"]+)['\"]",
        main_html,
    )
    if not match:
        raise ValueError("DART viewer metadata not found")

    params = {
        "rcpNo": match.group("rcp_no"),
        "dcmNo": match.group("dcm_no"),
        "eleId": match.group("ele_id"),
        "offset": match.group("offset"),
        "length": match.group("length"),
        "dtd": match.group("dtd"),
    }
    html = decode_html(fetch_url(f"{DART_VIEWER_URL}?{urlencode(params)}"))
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
    return html


def fetch_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "value-invest-buybacks/0.1"})
    try:
        with urlopen(request, timeout=12) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"DART HTML request failed: {exc}") from exc


def decode_html(raw: bytes) -> str:
    for encoding in ["utf-8", "euc-kr", "cp949"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def parse_retirement_details_from_html(html: str) -> dict:
    text = html_to_text(html)
    planned_common = number_after(
        text,
        r"소각할\s*주식의\s*종류와\s*수\s*보통주식\s*\(주\)",
    )
    planned_other = number_after(
        text,
        r"소각할\s*주식의\s*종류와\s*수.*?(?:종류|기타)주식\s*\(주\)",
    )
    issued_common = number_after(
        text,
        r"발행주식\s*총수\s*보통주식\s*\(주\)",
    )
    issued_other = number_after(
        text,
        r"발행주식\s*총수.*?(?:종류|기타)주식\s*\(주\)",
    )
    planned_amount = number_after(text, r"소각예정금액\s*\(원\)")
    decision_date = date_after(text, r"이사회결의일\s*\(결정일\)")
    retirement_date = date_after(text, r"소각\s*예정일")

    details = {
        "planned_shares_common": as_int(planned_common),
        "planned_shares_other": as_int(planned_other),
        "planned_amount_krw": as_int(planned_amount),
        "planned_amount_common_krw": None,
        "planned_amount_other_krw": None,
        "planned_share_ratio_common": safe_ratio(planned_common, issued_common),
        "planned_share_ratio_other": safe_ratio(planned_other, issued_other),
        "decision_date": decision_date,
        "period_start": None,
        "period_end": retirement_date,
        "method": meaningful_text(text_between(text, r"소각할\s*주식의\s*취득방법", r"\s*\d+\.\s*소각\s*예정일")),
        "purpose": meaningful_text(text_between(text, r"소각\s*목적", r"\s*\d+\.")),
        "broker": meaningful_text(
            text_between(text, r"자기주식\s*취득\s*위탁\s*투자중개업자", r"\s*\d+\.\s*이사회결의일")
        ),
    }
    return {key: value for key, value in details.items() if value not in [None, ""]}


def html_to_text(html: str) -> str:
    html = re.sub(r"(?i)<br\s*/?>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text).replace("\xa0", " ")).strip()


def number_after(text: str, label_pattern: str) -> int | float | None:
    match = re.search(label_pattern + r"\s*([△()0-9,\.\-]+)", text, flags=re.DOTALL)
    return parse_number(match.group(1)) if match else None


def date_after(text: str, label_pattern: str) -> str | None:
    match = re.search(label_pattern + r"\s*([0-9]{4}[.\-/년\s]+[0-9]{1,2}[.\-/월\s]+[0-9]{1,2})", text)
    return normalize_date(match.group(1)) if match else None


def text_between(text: str, start_pattern: str, end_pattern: str) -> str | None:
    match = re.search(start_pattern + r"\s*(.*?)" + end_pattern, text, flags=re.DOTALL)
    return clean_text(match.group(1)) if match else None


def meaningful_text(value: str | None) -> str | None:
    if value in {None, "-", "--"}:
        return None
    return value


def safe_ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def select_holding_rows(rows: list[dict]) -> list[dict]:
    listed = [row for row in rows if not is_placeholder_stock_kind(row.get("stock_knd"))]
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
    valid = [row for row in rows if not is_placeholder_stock_kind(row.get("se"))]
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
    return next((row for row in stock_totals if not is_placeholder_stock_kind(row.get("se"))), stock_totals[0])


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
    for event in sorted(
        events,
        key=lambda item: (item.disclosure_date, item.event_id, event_detail_score(item)),
        reverse=True,
    ):
        key = event.rcept_no or event.event_id
        typed_key = f"{key}:{event.event_type}"
        if typed_key in seen:
            continue
        seen.add(typed_key)
        output.append(event)
    return output


def event_detail_score(event: BuybackEvent) -> int:
    fields = [
        event.decision_date,
        event.period_start,
        event.period_end,
        event.planned_shares_common,
        event.planned_shares_other,
        event.planned_amount_krw,
        event.planned_amount_common_krw,
        event.planned_amount_other_krw,
        event.planned_share_ratio_common,
        event.planned_share_ratio_other,
        event.actual_shares,
        event.actual_amount_krw,
        event.method,
        event.purpose,
        event.broker,
        event.holding_before_common,
        event.holding_before_ratio_common,
    ]
    return sum(1 for value in fields if value not in [None, ""])


def dedupe_holdings(snapshots: list[TreasuryHoldingSnapshot]) -> list[TreasuryHoldingSnapshot]:
    seen: set[tuple[str, str, int, str, str]] = set()
    seen_facts: set[tuple[str, str, int, str, int | None, int | None, float | None]] = set()
    output: list[TreasuryHoldingSnapshot] = []
    for snapshot in sorted(
        snapshots,
        key=lambda item: (
            item.as_of_date,
            item.stock_code,
            item.report_code,
            stock_kind_quality(item.stock_kind),
            item.stock_kind,
        ),
        reverse=True,
    ):
        key = (
            snapshot.stock_code,
            snapshot.as_of_date,
            snapshot.report_year,
            snapshot.report_code,
            normalize_stock_kind(snapshot.stock_kind),
        )
        fact_key = holding_fact_key(snapshot)
        if key in seen or (is_placeholder_stock_kind(snapshot.stock_kind) and fact_key in seen_facts):
            continue
        seen.add(key)
        seen_facts.add(fact_key)
        output.append(snapshot)
    return output


def receipt_date_from_no(rcept_no: object) -> str | None:
    text = str(rcept_no or "")
    if len(text) < 8 or not text[:8].isdigit():
        return None
    return normalize_date(text[:8])


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


def clean_stock_kind(value: object) -> str:
    return "" if is_placeholder_stock_kind(value) else str(value or "").strip()


def is_placeholder_stock_kind(value: object) -> bool:
    return normalize_stock_kind(value) in {"", "-", "–", "—", "합계", "비고"}


def stock_kind_quality(value: object) -> int:
    if is_placeholder_stock_kind(value):
        return 0
    normalized = normalize_stock_kind(value)
    if "보통" in normalized:
        return 3
    return 2


def holding_fact_key(
    snapshot: TreasuryHoldingSnapshot,
) -> tuple[str, str, int, str, int | None, int | None, float | None]:
    ratio = round(snapshot.treasury_ratio, 12) if snapshot.treasury_ratio is not None else None
    return (
        snapshot.stock_code,
        snapshot.as_of_date,
        snapshot.report_year,
        snapshot.report_code,
        snapshot.ending_qty,
        snapshot.issued_shares,
        ratio,
    )


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


def sum_optional(*values: int | float | None) -> int | float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


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
