"""Execution-tracking pipeline for treasury stock result reports.

OpenDART has no structured API for 자기주식 결과/상황 보고서 (only decision
disclosures are structured), so this module discovers result reports through
``list.json`` (pblntf_detail_ty E001/E002), fetches the full multi-section
DART viewer document, and parses the standardized FSS report forms:

- 자기주식취득결과보고서      -> execution_type "acquisition_result"
- 자기주식처분결과보고서      -> execution_type "disposition_result"
- 신탁계약에의한취득상황보고서 -> execution_type "trust_status"

Parsed rows become BuybackExecution records stored in executions.json and are
re-linked to decision BuybackEvent rows on every build.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.dart_client import OpenDartClient, OpenDartNoData
    from scripts.buybacks.fetch_dart_buybacks import (
        DART_MAIN_URL,
        DART_VIEWER_URL,
        as_int,
        decode_html,
        dedupe_disclosures,
        fetch_url,
        html_to_text,
        receipt_date_from_no,
    )
    from scripts.buybacks.models import BuybackEvent, BuybackExecution
    from scripts.buybacks.parsers import (
        MISSING_VALUES,
        dart_source_url,
        kst_today,
        normalize_date,
        parse_number,
        parse_ratio_percent,
    )
else:
    from .dart_client import OpenDartClient, OpenDartNoData
    from .fetch_dart_buybacks import (
        DART_MAIN_URL,
        DART_VIEWER_URL,
        as_int,
        decode_html,
        dedupe_disclosures,
        fetch_url,
        html_to_text,
        receipt_date_from_no,
    )
    from .models import BuybackEvent, BuybackExecution
    from .parsers import (
        MISSING_VALUES,
        dart_source_url,
        kst_today,
        normalize_date,
        parse_number,
        parse_ratio_percent,
    )

LOGGER = logging.getLogger(__name__)

# list.json detail types that carry execution result reports:
# E001 = 자기주식취득/처분, E002 = 신탁계약체결/해지.
EXECUTION_DISCLOSURE_DETAIL_TYPES = ["E001", "E002"]

# Report-name matching is done on a compacted name (spaces and any [기재정정]
# style bracket prefixes removed) so correction reports match too.
EXECUTION_REPORT_NAMES: dict[str, str] = {
    "자기주식취득결과보고서": "acquisition_result",
    "자기주식처분결과보고서": "disposition_result",
    "신탁계약에의한취득상황보고서": "trust_status",
}

EXECUTION_TO_EVENT_TYPE: dict[str, str] = {
    "acquisition_result": "direct_acquisition",
    "disposition_result": "direct_disposition",
    "trust_status": "trust_contract_start",
}

# dart.fss.or.kr viewer requests are unofficial web endpoints; keep a polite
# interval between per-section requests (tests may set this to 0).
VIEWER_SECTION_FETCH_INTERVAL_SECONDS = 0.3

# TOC entries in main.do are emitted as repeated node1[...] assignment blocks.
# Anchoring on this block (instead of viewDoc(...) calls) is stable across
# viewer script changes and captures every section of the document.
VIEWER_TOC_NODE_RE = re.compile(
    r"node1\['text'\]\s*=\s*\"(?P<text>[^\"]*)\";\s*"
    r"node1\['id'\]\s*=\s*\"[^\"]*\";\s*"
    r"node1\['rcpNo'\]\s*=\s*\"(?P<rcp_no>\d+)\";\s*"
    r"node1\['dcmNo'\]\s*=\s*\"(?P<dcm_no>\d+)\";\s*"
    r"node1\['eleId'\]\s*=\s*\"(?P<ele_id>\d+)\";\s*"
    r"node1\['offset'\]\s*=\s*\"(?P<offset>\d+)\";\s*"
    r"node1\['length'\]\s*=\s*\"(?P<length>\d+)\";\s*"
    r"node1\['dtd'\]\s*=\s*\"(?P<dtd>[^\"]+)\";"
)

SECTION_MARKER_RE = re.compile(r"<!--\s*SECTION\s+eleId=(?P<ele_id>\d+)\s+text=(?P<text>.*?)\s*-->")

DATE_PATTERN = r"[0-9]{4}[.\-/년\s]*[0-9]{1,2}[.\-/월\s]*[0-9]{1,2}"
ORIGIN_REPORT_LABEL = r"주요사항보고서\s*제출일\s*[:：]?\s*"
DATE_RANGE_RE = re.compile(r"(" + DATE_PATTERN + r")\s*일?\s*[~∼]\s*(" + DATE_PATTERN + r")")
AS_OF_RE = re.compile(r"\[\s*(" + DATE_PATTERN + r")\s*일?\s*현재\s*\]")

STOCK_KIND_TOKENS = {"보통주식", "보통주", "종류주식", "기타주식", "우선주식", "우선주"}
TOTAL_ROW_TOKEN = r"(?:[0-9][0-9,\.]*|-|보통주식|보통주|종류주식|기타주식|우선주식|우선주)"
# "계" total rows in the standardized tables: the marker character followed by
# a run of numeric/dash/stock-kind tokens. "계(A+B)" headers and "신탁계약"
# style in-word occurrences do not match.
TOTAL_ROW_RE = re.compile(
    r"(?<![가-힣0-9A-Za-z)])계\s+((?:" + TOTAL_ROW_TOKEN + r"\s+){1,11}" + TOTAL_ROW_TOKEN + r")"
)

MATCH_VALUE = r"(?:[0-9][0-9,\.]*|-)"
# 일치/미달 여부 tables put four value columns (보통주식/기타주식 planned then
# actual) after the last "기타주식" header token, followed by the verdict and
# an optional reason.
MATCH_ROW_RE = re.compile(
    r"기타주식\s+(" + MATCH_VALUE + r")\s+(" + MATCH_VALUE + r")\s+("
    + MATCH_VALUE + r")\s+(" + MATCH_VALUE + r")\s+(\S+)\s*(.*)$",
    re.DOTALL,
)

# Money-unit declarations such as "(단위 : 백만원, 주, %)". Longer unit names
# must be checked before "원".
MONEY_UNIT_MULTIPLIERS: list[tuple[str, int]] = [
    ("백만원", 1_000_000),
    ("십억원", 1_000_000_000),
    ("천만원", 10_000_000),
    ("백억원", 10_000_000_000),
    ("천원", 1_000),
    ("억원", 100_000_000),
    ("원", 1),
]


# ---------------------------------------------------------------------------
# Discovery (OpenDART list.json, pblntf_detail_ty E001/E002)
# ---------------------------------------------------------------------------


def execution_type_for_report_name(report_name: object) -> str | None:
    """Map a list.json report_nm to an execution type, or None.

    Bracket prefixes such as "[기재정정]" and internal spacing variants
    ("신탁계약에의한 취득상황보고서") are normalized away before matching.
    """
    text = re.sub(r"\[[^\]]*\]", "", str(report_name or ""))
    text = re.sub(r"\s+", "", text)
    for name, execution_type in EXECUTION_REPORT_NAMES.items():
        if name in text:
            return execution_type
    return None


def is_execution_report(report_name: object) -> bool:
    return execution_type_for_report_name(report_name) is not None


def fetch_execution_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    raw_dir: Path | None = None,
    page_limit: int = 20,
) -> tuple[list[dict], list[str]]:
    """Discover execution result report rows through list.json.

    Mirrors fetch_buyback_disclosures (page loop, last_reprt_at=Y, rate limit
    via OpenDartClient) but queries pblntf_detail_ty E001/E002 and keeps only
    rows whose report name matches a result-report form.
    """
    client = OpenDartClient(api_key, raw_dir=raw_dir)
    disclosures: list[dict] = []
    warnings: list[str] = []
    for detail_type in EXECUTION_DISCLOSURE_DETAIL_TYPES:
        page_no = 1
        while page_no <= page_limit:
            try:
                data = client.request_json(
                    "list.json",
                    {
                        "bgn_de": bgn_de,
                        "end_de": end_de,
                        "last_reprt_at": "Y",
                        "pblntf_detail_ty": detail_type,
                        "sort": "date",
                        "sort_mth": "desc",
                        "page_no": str(page_no),
                        "page_count": "100",
                    },
                )
            except OpenDartNoData:
                break
            except Exception as exc:  # noqa: BLE001 - keep discovery resilient.
                warnings.append(
                    f"OpenDART execution search failed for pblntf_detail_ty={detail_type} page {page_no}: {exc}"
                )
                break

            page_rows = [item for item in data.get("list", []) if is_execution_report(item.get("report_nm"))]
            disclosures.extend(page_rows)

            total_page = int(parse_number(data.get("total_page")) or 1)
            if page_no >= total_page:
                break
            page_no += 1

    return dedupe_disclosures(disclosures), warnings


# ---------------------------------------------------------------------------
# Multi-section viewer document fetch
# ---------------------------------------------------------------------------


def parse_viewer_toc_nodes(main_html: str) -> list[dict[str, str]]:
    """Extract the full TOC (every section) from a main.do response."""
    nodes: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in VIEWER_TOC_NODE_RE.finditer(main_html):
        node = match.groupdict()
        key = (node["ele_id"], node["offset"], node["length"])
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)
    return nodes


def fetch_dart_viewer_document(rcept_no: str, raw_dir: Path | None = None) -> str:
    """Fetch every TOC section of a DART viewer document and merge them.

    Result reports span 6-8 TOC sections, and the first viewDoc match used by
    fetch_dart_viewer_html only returns the cover page, so this walks the
    node1[...] TOC from main.do and concatenates each report/viewer.do section
    behind a "<!-- SECTION eleId=... text=... -->" marker. Merged documents are
    cached under raw_dir/dart_viewers/{rcept_no}_full.html.
    """
    cache_path = Path(raw_dir) / "dart_viewers" / f"{rcept_no}_full.html" if raw_dir else None
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    main_html = decode_html(fetch_url(f"{DART_MAIN_URL}?{urlencode({'rcpNo': rcept_no})}"))
    nodes = parse_viewer_toc_nodes(main_html)
    if not nodes:
        raise ValueError("DART viewer TOC metadata not found")

    parts: list[str] = []
    for index, node in enumerate(nodes):
        if index and VIEWER_SECTION_FETCH_INTERVAL_SECONDS:
            time.sleep(VIEWER_SECTION_FETCH_INTERVAL_SECONDS)
        params = {
            "rcpNo": node["rcp_no"],
            "dcmNo": node["dcm_no"],
            "eleId": node["ele_id"],
            "offset": node["offset"],
            "length": node["length"],
            "dtd": node["dtd"],
        }
        section_html = decode_html(fetch_url(f"{DART_VIEWER_URL}?{urlencode(params)}"))
        parts.append(f"<!-- SECTION eleId={node['ele_id']} text={node['text']} -->\n{section_html}")

    document = "\n".join(parts)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(document, encoding="utf-8")
    return document


# ---------------------------------------------------------------------------
# Section slicing helpers
# ---------------------------------------------------------------------------


def split_viewer_sections(html: str) -> list[tuple[str | None, str]]:
    """Split a merged viewer document into (toc_title, section_html) pairs.

    Documents without SECTION markers collapse to a single wildcard section
    (title None) so parsers can still run best-effort on plain HTML.
    """
    matches = list(SECTION_MARKER_RE.finditer(html))
    if not matches:
        return [(None, html)]
    sections: list[tuple[str | None, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        sections.append((match.group("text"), html[match.end():end]))
    return sections


def section_text(
    sections: list[tuple[str | None, str]],
    include: tuple[str, ...],
    exclude: tuple[str, ...] = (),
) -> str | None:
    """Flattened text of the first section whose TOC title matches.

    Matching is title-based (not positional) because correction reports insert
    a leading "정 정 신 고 (보고)" section that shifts every section index.
    """
    for title, section_html in sections:
        if title is None:
            return html_to_text(section_html)
        normalized = title.replace(" ", "")
        if any(keyword in normalized for keyword in include) and not any(
            keyword in normalized for keyword in exclude
        ):
            return html_to_text(section_html)
    return None


def money_unit_multiplier(text: str | None) -> int:
    """Multiplier for money columns from the section's "(단위 : ...)" note.

    Some filers report money tables in 백만원 (e.g. holding tables), so amounts
    must be scaled by the declared unit instead of assumed to be KRW.
    """
    if not text:
        return 1
    match = re.search(r"\(\s*단\s*위\s*[:：]\s*([^)]*)\)", text)
    if not match:
        return 1
    unit_declaration = match.group(1).replace(" ", "")
    for unit, multiplier in MONEY_UNIT_MULTIPLIERS:
        if unit in unit_declaration:
            return multiplier
    return 1


def scale_money(value: int | float | None, multiplier: int) -> int | float | None:
    if value is None:
        return None
    scaled = value * multiplier
    return int(scaled) if float(scaled).is_integer() else scaled


def first_date_after(text: str, label_pattern: str) -> str | None:
    match = re.search(label_pattern + r"(" + DATE_PATTERN + r")", text)
    return normalize_date(match.group(1)) if match else None


def date_range_after(text: str, label_pattern: str) -> tuple[str | None, str | None]:
    match = re.search(
        label_pattern + r"(" + DATE_PATTERN + r")\s*일?\s*(?:부터|[~∼])\s*(" + DATE_PATTERN + r")",
        text,
    )
    if not match:
        return None, None
    return normalize_date(match.group(1)), normalize_date(match.group(2))


def as_of_date_from(text: str | None) -> str | None:
    if not text:
        return None
    match = AS_OF_RE.search(text)
    return normalize_date(match.group(1)) if match else None


def total_flow_values(text: str) -> list[int | float | None] | None:
    """[qty_a, qty_b, avg_price, total_amount] from a 취득/처분내용 "계" row.

    Column meaning varies by report type (acq/disp: 주문수량/체결수량,
    trust: 누적취득수량/처분수량) but the shape is shared: strip stock-kind
    tokens and the leading 종류 placeholder dash, then read four values.
    """
    for match in TOTAL_ROW_RE.finditer(text):
        tokens = [token for token in match.group(1).split() if token not in STOCK_KIND_TOKENS]
        while tokens and tokens[0] == "-":
            tokens.pop(0)
        if len(tokens) < 3:
            continue
        values = [parse_number(token) for token in tokens[:4]]
        if sum(1 for value in values if value is not None) >= 2:
            values += [None] * (4 - len(values))
            return values
    return None


def holding_total_values(text: str) -> list[int | float | None] | None:
    """Nine value columns of the 보유상황 "계" row.

    Layout: A(수량 비율 총가액) B(수량 비율 계약금액) 계(수량 비율 금액).
    Positional dashes matter here, so leading dashes are preserved.
    """
    for match in TOTAL_ROW_RE.finditer(text):
        tokens = [token for token in match.group(1).split() if token not in STOCK_KIND_TOKENS]
        if len(tokens) < 9:
            continue
        return [parse_number(token) for token in tokens[:9]]
    return None


def parse_match_section(text: str) -> dict | None:
    """Parse the 일치/미달 여부 table: four values, verdict, optional reason."""
    match = MATCH_ROW_RE.search(text)
    if not match:
        return None
    values = [parse_number(match.group(index)) for index in range(1, 5)]
    verdict = match.group(5)
    if "미달" in verdict or "불일치" in verdict:
        shortfall: bool | None = True
    elif "일치" in verdict or verdict in {"-", "–", "—"}:
        shortfall = False
    else:
        shortfall = None
    reason_text = re.split(r"※|주\d+\)|\(\*", match.group(6))[0]
    reason_text = reason_text.strip().strip("-–—").strip()
    reason = None if not reason_text or reason_text in MISSING_VALUES else reason_text
    return {"values": values, "shortfall": shortfall, "reason": reason}


def sum_present(*values: int | float | None) -> int | float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


# ---------------------------------------------------------------------------
# Report parsers (soft-fail: unparsed fields stay None)
# ---------------------------------------------------------------------------


def parse_acquisition_result_html(html: str) -> dict:
    """자기주식취득결과보고서 parser."""
    sections = split_viewer_sections(html)
    report_text = section_text(sections, ("취득보고에관한",))
    flow_text = section_text(sections, ("취득내용",), exclude=("일치", "예정"))
    match_text = section_text(sections, ("일치",))
    holding_text = section_text(sections, ("보유상황",), exclude=("최대주주",))

    details: dict = {}
    if report_text:
        details["origin_report_date"] = first_date_after(report_text, ORIGIN_REPORT_LABEL)
        start, end = date_range_after(report_text, r"취득기간\s*[:：]?\s*")
        details["period_start"] = start
        details["period_end"] = end
    if flow_text:
        multiplier = money_unit_multiplier(flow_text)
        flow = total_flow_values(flow_text)
        if flow:
            ordered, actual, avg_price, total_amount = flow
            details["ordered_shares"] = as_int(ordered)
            details["actual_shares"] = as_int(actual)
            details["avg_price_krw"] = scale_money(avg_price, multiplier)
            details["actual_amount_krw"] = scale_money(total_amount, multiplier)
    if match_text:
        parsed_match = parse_match_section(match_text)
        if parsed_match:
            multiplier = money_unit_multiplier(match_text)
            planned_common, planned_other = parsed_match["values"][0], parsed_match["values"][1]
            details["planned_amount_krw"] = scale_money(sum_present(planned_common, planned_other), multiplier)
            details["shortfall"] = parsed_match["shortfall"]
            details["shortfall_reason"] = parsed_match["reason"]
    if holding_text:
        details["as_of_date"] = as_of_date_from(holding_text)
        totals = holding_total_values(holding_text)
        if totals:
            details["holding_after_qty"] = as_int(totals[6])
            details["holding_after_ratio"] = ratio_from_percent_value(totals[7])
    return details


def parse_disposition_result_html(html: str) -> dict:
    """자기주식처분결과보고서 parser."""
    sections = split_viewer_sections(html)
    report_text = section_text(sections, ("처분보고에관한",), exclude=("일치",))
    flow_text = section_text(sections, ("처분내용",), exclude=("일치",))
    match_text = section_text(sections, ("일치",))
    holding_text = section_text(sections, ("보유상황",), exclude=("최대주주",))

    details: dict = {}
    if report_text:
        details["origin_report_date"] = first_date_after(report_text, ORIGIN_REPORT_LABEL)
        start, end = date_range_after(report_text, r"처분기간\s*[:：]?\s*")
        details["period_start"] = start
        details["period_end"] = end
    if flow_text:
        multiplier = money_unit_multiplier(flow_text)
        flow = total_flow_values(flow_text)
        if flow:
            ordered, actual, avg_price, total_amount = flow
            details["ordered_shares"] = as_int(ordered)
            details["actual_shares"] = as_int(actual)
            details["avg_price_krw"] = scale_money(avg_price, multiplier)
            details["actual_amount_krw"] = scale_money(total_amount, multiplier)
    if match_text:
        parsed_match = parse_match_section(match_text)
        if parsed_match:
            # Disposition match tables compare share counts (주), not amounts.
            planned_common, planned_other = parsed_match["values"][0], parsed_match["values"][1]
            details["planned_shares"] = as_int(sum_present(planned_common, planned_other))
            details["shortfall"] = parsed_match["shortfall"]
            details["shortfall_reason"] = parsed_match["reason"]
    if holding_text:
        details["as_of_date"] = as_of_date_from(holding_text)
        totals = holding_total_values(holding_text)
        if totals:
            details["holding_after_qty"] = as_int(totals[6])
            details["holding_after_ratio"] = ratio_from_percent_value(totals[7])
    return details


def parse_trust_status_html(html: str) -> dict:
    """신탁계약에의한취득상황보고서 parser. Flow figures are cumulative."""
    sections = split_viewer_sections(html)
    report_text = section_text(sections, ("체결보고", "신탁계약체결"))
    flow_text = section_text(sections, ("취득내용",), exclude=("일치",))
    holding_text = section_text(sections, ("보유상황",), exclude=("최대주주",))
    misc_text = section_text(sections, ("기타",))

    details: dict = {}
    if report_text:
        details["origin_report_date"] = first_date_after(report_text, ORIGIN_REPORT_LABEL)
    if flow_text:
        multiplier = money_unit_multiplier(flow_text)
        flow = total_flow_values(flow_text)
        if flow:
            acquired, _disposed, avg_price, total_amount = flow
            details["actual_shares"] = as_int(acquired)
            details["avg_price_krw"] = scale_money(avg_price, multiplier)
            details["actual_amount_krw"] = scale_money(total_amount, multiplier)

    contract_amount: int | float | None = None
    if misc_text:
        misc_multiplier = money_unit_multiplier(misc_text)
        start, end, amount = trust_contract_summary(misc_text)
        details["period_start"] = start
        details["period_end"] = end
        contract_amount = scale_money(amount, misc_multiplier)
    if holding_text:
        details["as_of_date"] = as_of_date_from(holding_text) or as_of_date_from(misc_text)
        totals = holding_total_values(holding_text)
        if totals:
            details["holding_after_qty"] = as_int(totals[6])
            details["holding_after_ratio"] = ratio_from_percent_value(totals[7])
            if contract_amount is None:
                # Column 5 is the trust-contract amount of the B block.
                contract_amount = scale_money(totals[5], money_unit_multiplier(holding_text))
    if details.get("as_of_date") is None:
        details["as_of_date"] = as_of_date_from(misc_text)

    details["trust_contract_amount_krw"] = contract_amount
    actual_amount = details.get("actual_amount_krw")
    if contract_amount and actual_amount is not None:
        details["trust_progress_ratio"] = float(actual_amount) / float(contract_amount)
    return details


def trust_contract_summary(text: str) -> tuple[str | None, str | None, int | float | None]:
    """(계약기간 시작, 종료, 계약금액) from the 신탁계약현황 table.

    The flattened table reads "... 계약기간 체결기관 계약금액 ... <체결일>
    <기간~기간> <기관명> <금액>", so the first date range anchors the row and
    the first number after it is the contract amount.
    """
    match = DATE_RANGE_RE.search(text)
    if not match:
        return None, None, None
    start = normalize_date(match.group(1))
    end = normalize_date(match.group(2))
    tail = text[match.end():][:160]
    amount_match = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", tail)
    amount = parse_number(amount_match.group(1)) if amount_match else None
    return start, end, amount


def ratio_from_percent_value(value: int | float | None) -> float | None:
    return parse_ratio_percent(value) if value is not None else None


EXECUTION_PARSERS = {
    "acquisition_result": parse_acquisition_result_html,
    "disposition_result": parse_disposition_result_html,
    "trust_status": parse_trust_status_html,
}


# ---------------------------------------------------------------------------
# Normalization and collection
# ---------------------------------------------------------------------------


def normalize_execution(item: dict, execution_type: str, details: dict) -> BuybackExecution:
    rcept_no = str(item.get("rcept_no") or "")
    disclosure_date = (
        normalize_date(item.get("rcept_dt"))
        or receipt_date_from_no(rcept_no)
        or kst_today().isoformat()  # Disclosure dates are Korea-local.
    )
    return BuybackExecution(
        execution_id=f"dart-{rcept_no}-{execution_type}",
        corp_code=str(item.get("corp_code") or ""),
        stock_code=str(item.get("stock_code") or "").strip().upper(),
        corp_name=str(item.get("corp_name") or ""),
        execution_type=execution_type,  # type: ignore[arg-type]
        disclosure_date=disclosure_date,
        origin_report_date=details.get("origin_report_date"),
        period_start=details.get("period_start"),
        period_end=details.get("period_end"),
        ordered_shares=details.get("ordered_shares"),
        actual_shares=details.get("actual_shares"),
        actual_amount_krw=details.get("actual_amount_krw"),
        avg_price_krw=details.get("avg_price_krw"),
        planned_amount_krw=details.get("planned_amount_krw"),
        planned_shares=details.get("planned_shares"),
        shortfall=details.get("shortfall"),
        shortfall_reason=details.get("shortfall_reason"),
        holding_after_qty=details.get("holding_after_qty"),
        holding_after_ratio=details.get("holding_after_ratio"),
        trust_contract_amount_krw=details.get("trust_contract_amount_krw"),
        trust_progress_ratio=details.get("trust_progress_ratio"),
        as_of_date=details.get("as_of_date"),
        linked_event_id=None,
        link_method="unlinked",
        source="DART",
        rcept_no=rcept_no,
        source_url=dart_source_url(rcept_no),
        raw_report_name=item.get("report_nm"),
    )


def collect_execution_reports(
    api_key: str,
    bgn_de: str,
    end_de: str,
    raw_dir: Path | None = None,
    page_limit: int = 20,
) -> tuple[list[BuybackExecution], list[str]]:
    """Discover, fetch, and parse execution result reports for a window.

    Viewer fetch/parse failures are soft: the execution row is kept with null
    detail fields (fetch failure drops the row entirely) and a warning is
    recorded, so a dart.fss.or.kr outage never breaks the event pipeline.
    """
    disclosures, warnings = fetch_execution_disclosures(
        api_key=api_key,
        bgn_de=bgn_de,
        end_de=end_de,
        raw_dir=raw_dir,
        page_limit=page_limit,
    )
    executions: list[BuybackExecution] = []
    for item in disclosures:
        execution_type = execution_type_for_report_name(item.get("report_nm"))
        rcept_no = str(item.get("rcept_no") or "")
        if not execution_type or not rcept_no:
            continue
        details: dict = {}
        try:
            document = fetch_dart_viewer_document(rcept_no, raw_dir=raw_dir)
            details = EXECUTION_PARSERS[execution_type](document)
        except Exception as exc:  # noqa: BLE001 - keep collection resilient.
            warning = f"{rcept_no} execution report fetch/parse failed: {exc}"
            LOGGER.warning(warning)
            warnings.append(warning)
        execution = normalize_execution(item, execution_type, details)
        if execution.actual_shares is None and execution.actual_amount_krw is None:
            warnings.append(
                f"{rcept_no} execution report has no parsed actual shares/amount; fields kept null."
            )
        executions.append(execution)
    return merge_executions([], executions), warnings


# ---------------------------------------------------------------------------
# Linking and merging
# ---------------------------------------------------------------------------


def link_executions(
    executions: Iterable[BuybackExecution],
    events: Iterable[BuybackEvent],
) -> list[BuybackExecution]:
    """Deterministically (re)link executions to decision events.

    Primary key: corp_code + 본문의 주요사항보고서 제출일 == event disclosure
    date + mapped event type. Fallback: period overlap with the nearest
    preceding decision disclosure. Unmatched rows are preserved as unlinked so
    later event backfills can promote them on the next build.
    """
    events_by_date_key: dict[tuple[str, str, str], list[BuybackEvent]] = {}
    events_by_corp_type: dict[tuple[str, str], list[BuybackEvent]] = {}
    for event in events:
        date_key = (event.corp_code, event.event_type, event.disclosure_date)
        events_by_date_key.setdefault(date_key, []).append(event)
        events_by_corp_type.setdefault((event.corp_code, event.event_type), []).append(event)

    linked: list[BuybackExecution] = []
    for execution in executions:
        event_type = EXECUTION_TO_EVENT_TYPE[execution.execution_type]
        candidates = (
            events_by_date_key.get((execution.corp_code, event_type, execution.origin_report_date), [])
            if execution.origin_report_date
            else []
        )
        if candidates:
            event = pick_report_date_event(candidates, execution)
            linked.append(replace(execution, linked_event_id=event.event_id, link_method="report_date"))
            continue
        fallback = pick_period_overlap_event(
            events_by_corp_type.get((execution.corp_code, event_type), []),
            execution,
        )
        if fallback:
            linked.append(replace(execution, linked_event_id=fallback.event_id, link_method="period_overlap"))
            continue
        linked.append(replace(execution, linked_event_id=None, link_method="unlinked"))
    return linked


def pick_report_date_event(candidates: list[BuybackEvent], execution: BuybackExecution) -> BuybackEvent:
    if len(candidates) == 1:
        return candidates[0]
    # Same-day duplicates of the same decision type are rare; tie-break on
    # period overlap, then a deterministic id sort.
    overlapping = [event for event in candidates if periods_overlap(event, execution)]
    pool = overlapping or candidates
    return sorted(pool, key=lambda event: event.event_id)[0]


def pick_period_overlap_event(
    candidates: list[BuybackEvent],
    execution: BuybackExecution,
) -> BuybackEvent | None:
    matching = [
        event
        for event in candidates
        if periods_overlap(event, execution) and event.disclosure_date <= execution.disclosure_date
    ]
    if not matching:
        return None
    return sorted(matching, key=lambda event: (event.disclosure_date, event.event_id), reverse=True)[0]


def periods_overlap(event: BuybackEvent, execution: BuybackExecution) -> bool:
    if not execution.period_start or not event.period_start:
        return False
    execution_end = execution.period_end or execution.period_start
    event_end = event.period_end or "9999-12-31"
    return execution.period_start <= event_end and event.period_start <= execution_end


def merge_executions(
    existing: Iterable[BuybackExecution],
    incoming: Iterable[BuybackExecution],
) -> list[BuybackExecution]:
    """Merge execution rows keyed by rcept_no; corrections supersede originals.

    A [기재정정] result report gets a new rcept_no, so acquisition/disposition
    rows sharing (corp_code, execution_type, origin_report_date) keep only the
    latest disclosure. Trust status reports are recurring cumulative filings
    for the same contract (every ~3 months), so their supersede group also
    includes as_of_date: quarterly history is preserved while a corrected
    filing for the same base date still replaces the original. Use
    latest_trust_status_by_contract for aggregation to avoid double counting.
    """
    by_rcept: dict[str, BuybackExecution] = {}
    for execution in [*existing, *incoming]:  # incoming wins on the same rcept_no
        by_rcept[execution.rcept_no or execution.execution_id] = execution

    best: dict[tuple, BuybackExecution] = {}
    for execution in by_rcept.values():
        key = correction_group_key(execution)
        previous = best.get(key)
        if previous is None or (execution.disclosure_date, execution.rcept_no) > (
            previous.disclosure_date,
            previous.rcept_no,
        ):
            best[key] = execution
    return sorted(best.values(), key=lambda item: (item.disclosure_date, item.execution_id), reverse=True)


def correction_group_key(execution: BuybackExecution) -> tuple:
    if execution.origin_report_date is None:
        return ("rcept", execution.rcept_no or execution.execution_id)
    if execution.execution_type == "trust_status":
        if execution.as_of_date is None:
            return ("rcept", execution.rcept_no or execution.execution_id)
        return (
            execution.corp_code,
            execution.execution_type,
            execution.origin_report_date,
            execution.as_of_date,
        )
    return (execution.corp_code, execution.execution_type, execution.origin_report_date)


def latest_trust_status_by_contract(
    executions: Iterable[BuybackExecution],
) -> list[BuybackExecution]:
    """One representative (latest as-of) trust status row per contract.

    Trust reports are cumulative, so summing every quarterly filing double
    counts. Aggregations should use this selection instead of raw rows.
    """
    best: dict[object, BuybackExecution] = {}
    for execution in executions:
        if execution.execution_type != "trust_status":
            continue
        key: object = execution.linked_event_id or (
            execution.corp_code,
            execution.origin_report_date or execution.rcept_no,
        )
        previous = best.get(key)
        if previous is None or trust_status_recency(execution) > trust_status_recency(previous):
            best[key] = execution
    return sorted(best.values(), key=lambda item: (item.disclosure_date, item.execution_id), reverse=True)


def trust_status_recency(execution: BuybackExecution) -> tuple[str, str, str]:
    return (
        execution.as_of_date or execution.disclosure_date,
        execution.disclosure_date,
        execution.rcept_no or "",
    )
