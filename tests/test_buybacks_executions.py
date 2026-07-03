from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import scripts.buybacks.executions as executions_module
from scripts.buybacks.executions import (
    execution_type_for_report_name,
    fetch_dart_viewer_document,
    fetch_execution_disclosures,
    latest_trust_status_by_contract,
    link_executions,
    merge_executions,
    money_unit_multiplier,
    normalize_execution,
    parse_acquisition_result_html,
    parse_disposition_result_html,
    parse_trust_status_html,
    parse_viewer_toc_nodes,
)
from scripts.buybacks.models import BuybackEvent, BuybackExecution
from scripts.buybacks.parsers import classify_event_type

FIXTURES = Path(__file__).parent / "fixtures" / "dart_viewers"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_event(
    event_id: str = "dart-20260610000270-direct_acquisition",
    corp_code: str = "01159652",
    event_type: str = "direct_acquisition",
    disclosure_date: str = "2026-06-10",
    period_start: str | None = "2026-06-11",
    period_end: str | None = "2026-07-01",
) -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code=corp_code,
        stock_code="362320",
        corp_name="청담글로벌",
        event_type=event_type,  # type: ignore[arg-type]
        disclosure_date=disclosure_date,
        decision_date=disclosure_date,
        period_start=period_start,
        period_end=period_end,
        planned_shares_common=458_400,
        planned_shares_other=None,
        planned_amount_krw=2_000_002_200,
        planned_amount_common_krw=2_000_002_200,
        planned_amount_other_krw=None,
        planned_share_ratio_common=None,
        planned_share_ratio_other=None,
        actual_shares=None,
        actual_amount_krw=None,
        method=None,
        purpose=None,
        broker=None,
        holding_before_common=None,
        holding_before_ratio_common=None,
        source="DART",
        rcept_no="20260610000270",
        source_url=None,
        raw_report_name="주요사항보고서(자기주식취득결정)",
    )


def make_execution(
    rcept_no: str = "20260703000080",
    execution_type: str = "acquisition_result",
    corp_code: str = "01159652",
    disclosure_date: str = "2026-07-03",
    origin_report_date: str | None = "2026-06-10",
    period_start: str | None = "2026-06-11",
    period_end: str | None = "2026-07-01",
    as_of_date: str | None = None,
    actual_shares: int | None = 458_373,
) -> BuybackExecution:
    return BuybackExecution(
        execution_id=f"dart-{rcept_no}-{execution_type}",
        corp_code=corp_code,
        stock_code="362320",
        corp_name="청담글로벌",
        execution_type=execution_type,  # type: ignore[arg-type]
        disclosure_date=disclosure_date,
        origin_report_date=origin_report_date,
        period_start=period_start,
        period_end=period_end,
        ordered_shares=None,
        actual_shares=actual_shares,
        actual_amount_krw=None,
        avg_price_krw=None,
        planned_amount_krw=None,
        planned_shares=None,
        shortfall=None,
        shortfall_reason=None,
        holding_after_qty=None,
        holding_after_ratio=None,
        trust_contract_amount_krw=None,
        trust_progress_ratio=None,
        as_of_date=as_of_date,
        linked_event_id=None,
        link_method="unlinked",
        source="DART",
        rcept_no=rcept_no,
        source_url=None,
        raw_report_name=None,
    )


# ---------------------------------------------------------------------------
# classify_event_type guard (must run before E001/E002 discovery is enabled)
# ---------------------------------------------------------------------------


def test_classify_event_type_never_marks_result_reports_as_decision_events():
    assert classify_event_type("자기주식취득결과보고서") == "unknown"
    assert classify_event_type("[기재정정]자기주식취득결과보고서") == "unknown"
    assert classify_event_type("자기주식처분결과보고서") == "unknown"
    assert classify_event_type("신탁계약에의한취득상황보고서") == "unknown"
    assert classify_event_type("신탁계약에의한 취득상황보고서") == "unknown"


def test_classify_event_type_keeps_decision_reports_unchanged():
    assert classify_event_type("주요사항보고서(자기주식취득결정)") == "direct_acquisition"
    assert classify_event_type("주요사항보고서(자기주식처분결정)") == "direct_disposition"
    assert classify_event_type("자기주식취득 신탁계약 체결 결정") == "trust_contract_start"
    assert classify_event_type("자기주식취득 신탁계약 해지 결정") == "trust_contract_end"
    assert classify_event_type("주식소각결정") == "retirement"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_execution_type_for_report_name_matches_forms_and_correction_variants():
    assert execution_type_for_report_name("자기주식취득결과보고서") == "acquisition_result"
    assert execution_type_for_report_name("[기재정정]자기주식취득결과보고서") == "acquisition_result"
    assert execution_type_for_report_name("자기주식처분결과보고서") == "disposition_result"
    assert execution_type_for_report_name("신탁계약에의한취득상황보고서") == "trust_status"
    assert execution_type_for_report_name("신탁계약에의한 취득상황보고서") == "trust_status"
    assert execution_type_for_report_name("주요사항보고서(자기주식취득결정)") is None
    assert execution_type_for_report_name("주요사항보고서(자기주식처분결정)") is None
    assert execution_type_for_report_name(None) is None


def test_fetch_execution_disclosures_queries_e001_and_e002_and_filters_report_names(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, api_key, raw_dir=None):
            pass

        def request_json(self, endpoint, params):
            assert endpoint == "list.json"
            assert params["last_reprt_at"] == "Y"
            calls.append(params["pblntf_detail_ty"])
            if params["pblntf_detail_ty"] == "E001":
                return {
                    "total_page": "1",
                    "list": [
                        {
                            "corp_code": "01159652",
                            "corp_name": "청담글로벌",
                            "stock_code": "362320",
                            "corp_cls": "K",
                            "report_nm": "자기주식취득결과보고서",
                            "rcept_no": "20260703000080",
                            "rcept_dt": "20260703",
                        },
                        {
                            "corp_code": "00120182",
                            "corp_name": "신원",
                            "stock_code": "009270",
                            "corp_cls": "Y",
                            "report_nm": "[기재정정]자기주식취득결과보고서",
                            "rcept_no": "20260701000608",
                            "rcept_dt": "20260701",
                        },
                        {
                            "corp_code": "00999999",
                            "corp_name": "기타공시",
                            "stock_code": "111111",
                            "corp_cls": "Y",
                            "report_nm": "자기주식취득결과보고서",
                            "rcept_no": "20260703000080",
                            "rcept_dt": "20260703",
                        },
                        {
                            "corp_code": "00888888",
                            "corp_name": "무관공시",
                            "stock_code": "222222",
                            "corp_cls": "Y",
                            "report_nm": "주요사항보고서(자기주식취득결정)",
                            "rcept_no": "20260702000001",
                            "rcept_dt": "20260702",
                        },
                    ],
                }
            return {
                "total_page": "1",
                "list": [
                    {
                        "corp_code": "01338724",
                        "corp_name": "오션인더블유",
                        "stock_code": "476040",
                        "corp_cls": "K",
                        "report_nm": "신탁계약에의한 취득상황보고서",
                        "rcept_no": "20260623000282",
                        "rcept_dt": "20260623",
                    }
                ],
            }

    monkeypatch.setattr(executions_module, "OpenDartClient", FakeClient)

    disclosures, warnings = fetch_execution_disclosures("fixture", "20260601", "20260703", raw_dir=tmp_path)

    assert warnings == []
    assert calls == ["E001", "E002"]
    # Duplicate rcept_no deduped, decision report filtered out.
    assert [item["rcept_no"] for item in disclosures] == [
        "20260703000080",
        "20260701000608",
        "20260623000282",
    ]


# ---------------------------------------------------------------------------
# Multi-section viewer fetch
# ---------------------------------------------------------------------------


def test_parse_viewer_toc_nodes_extracts_every_section():
    nodes = parse_viewer_toc_nodes(fixture_html("main_toc.html"))

    assert [node["ele_id"] for node in nodes] == ["1", "2", "5", "8", "9", "10", "11"]
    assert nodes[0]["rcp_no"] == "20260703000080"
    assert nodes[0]["dcm_no"] == "11461818"
    assert nodes[3]["text"] == "3. 취득내용"
    assert all(node["dtd"] == "dart4.xsd" for node in nodes)


def test_fetch_dart_viewer_document_merges_sections_and_caches(monkeypatch, tmp_path):
    main_html = fixture_html("main_toc.html")
    fetched_urls = []

    def fake_fetch_url(url: str) -> bytes:
        fetched_urls.append(url)
        parsed = urlparse(url)
        if parsed.path.endswith("main.do"):
            return main_html.encode("utf-8")
        params = parse_qs(parsed.query)
        return f"<p>section {params['eleId'][0]} body</p>".encode("utf-8")

    monkeypatch.setattr(executions_module, "fetch_url", fake_fetch_url)
    monkeypatch.setattr(executions_module, "VIEWER_SECTION_FETCH_INTERVAL_SECONDS", 0)

    document = fetch_dart_viewer_document("20260703000080", raw_dir=tmp_path)

    # 1 main.do + 7 sections.
    assert len(fetched_urls) == 8
    assert document.count("<!-- SECTION eleId=") == 7
    assert "<!-- SECTION eleId=8 text=3. 취득내용 -->" in document
    assert "<p>section 8 body</p>" in document
    assert (tmp_path / "dart_viewers" / "20260703000080_full.html").exists()

    # Second call is served from the raw_dir cache without new requests.
    cached = fetch_dart_viewer_document("20260703000080", raw_dir=tmp_path)
    assert cached == document
    assert len(fetched_urls) == 8


# ---------------------------------------------------------------------------
# Report parsers (real DART sample sections)
# ---------------------------------------------------------------------------


def test_parse_acquisition_result_normal_completion():
    details = parse_acquisition_result_html(fixture_html("acq_result_normal.html"))

    assert details["origin_report_date"] == "2026-06-10"
    assert details["period_start"] == "2026-06-11"
    assert details["period_end"] == "2026-07-01"
    assert details["ordered_shares"] == 510_800
    assert details["actual_shares"] == 458_373
    assert details["avg_price_krw"] == 4_363
    assert details["actual_amount_krw"] == 1_999_998_640
    assert details["planned_amount_krw"] == 2_000_002_200
    assert details["shortfall"] is False
    assert details["shortfall_reason"] is None
    assert details["holding_after_qty"] == 458_373
    assert details["holding_after_ratio"] == pytest.approx(0.0217)
    assert details["as_of_date"] == "2026-07-03"


def test_parse_acquisition_result_correction_with_amount_shortfall():
    # [기재정정] report: a leading 정정신고 section shifts every section index,
    # so title-based matching must still find the corrected body tables.
    details = parse_acquisition_result_html(fixture_html("acq_result_correction_shortfall.html"))

    assert details["origin_report_date"] == "2026-05-28"
    assert details["period_start"] == "2026-05-29"
    assert details["period_end"] == "2026-06-26"
    assert details["ordered_shares"] == 2_564_350
    # Amount fell short but the planned share count was fully acquired.
    assert details["actual_shares"] == 2_000_000
    assert details["actual_amount_krw"] == 2_158_214_553
    assert details["planned_amount_krw"] == 2_202_000_000
    assert details["shortfall"] is True
    assert "매수 완료" in details["shortfall_reason"]
    assert details["holding_after_qty"] == 27_000_000
    assert details["holding_after_ratio"] == pytest.approx(0.2353)


def test_parse_disposition_result_with_million_krw_holding_table():
    details = parse_disposition_result_html(fixture_html("disp_result_million_unit.html"))

    assert details["origin_report_date"] == "2026-04-30"
    assert details["period_start"] == "2026-06-01"
    assert details["period_end"] == "2026-06-01"
    assert details["ordered_shares"] == 22_368
    assert details["actual_shares"] == 22_368
    assert details["avg_price_krw"] == 249_500
    assert details["actual_amount_krw"] == 5_580_816_000
    assert details["planned_shares"] == 22_368
    assert details["shortfall"] is False
    assert details["shortfall_reason"] is None
    # The 보유상황 table is declared in 백만원; share counts must not be scaled.
    assert details["holding_after_qty"] == 853_276
    assert details["holding_after_ratio"] == pytest.approx(0.0185)
    assert details["as_of_date"] == "2026-06-01"


def test_parse_trust_status_cumulative_report():
    details = parse_trust_status_html(fixture_html("trust_status_cumulative.html"))

    assert details["origin_report_date"] == "2026-03-19"
    assert details["actual_shares"] == 260_696
    assert details["actual_amount_krw"] == 436_877_706
    assert details["avg_price_krw"] == 1_676
    assert details["period_start"] == "2026-03-19"
    assert details["period_end"] == "2026-09-21"
    assert details["trust_contract_amount_krw"] == 2_000_000_000
    assert details["trust_progress_ratio"] == pytest.approx(0.2184, abs=1e-4)
    assert details["holding_after_qty"] == 260_696
    assert details["holding_after_ratio"] == pytest.approx(0.016)
    assert details["as_of_date"] == "2026-06-19"


def test_parse_trust_status_scales_million_krw_contract_amount():
    details = parse_trust_status_html(fixture_html("trust_status_million_unit.html"))

    assert details["origin_report_date"] == "2026-03-11"
    assert details["actual_shares"] == 134_106
    # 취득내용 is in KRW while 계약금액 tables are in 백만원.
    assert details["actual_amount_krw"] == 17_707_838_400
    assert details["trust_contract_amount_krw"] == 30_000_000_000
    assert details["trust_progress_ratio"] == pytest.approx(0.5903, abs=1e-4)
    assert details["period_start"] == "2026-03-19"
    assert details["period_end"] == "2026-09-18"
    assert details["holding_after_qty"] == 2_758_523
    assert details["holding_after_ratio"] == pytest.approx(0.1097)
    assert details["as_of_date"] == "2026-06-18"


def test_money_unit_multiplier_reads_unit_declarations():
    assert money_unit_multiplier("(단위 : 원, 주)") == 1
    assert money_unit_multiplier("(단위 : 백만원, 주, %)") == 1_000_000
    assert money_unit_multiplier("(단위 : 천원)") == 1_000
    assert money_unit_multiplier("단위 선언 없음") == 1
    assert money_unit_multiplier(None) == 1


def test_normalize_execution_builds_ids_and_falls_back_to_receipt_date():
    execution = normalize_execution(
        {
            "rcept_no": "20260703000080",
            "corp_code": "01159652",
            "corp_name": "청담글로벌",
            "stock_code": "362320",
            "report_nm": "자기주식취득결과보고서",
        },
        "acquisition_result",
        {"actual_shares": 458_373},
    )

    assert execution.execution_id == "dart-20260703000080-acquisition_result"
    assert execution.disclosure_date == "2026-07-03"
    assert execution.actual_shares == 458_373
    assert execution.link_method == "unlinked"
    assert execution.source_url.endswith("20260703000080")


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


def test_link_executions_prefers_origin_report_date_match():
    event = make_event()
    execution = make_execution()

    linked = link_executions([execution], [event])

    assert linked[0].linked_event_id == event.event_id
    assert linked[0].link_method == "report_date"


def test_link_executions_falls_back_to_period_overlap():
    # Origin reference points at the pre-correction date, so the report-date
    # key misses and the period-overlap fallback must pick the decision event.
    event = make_event(disclosure_date="2026-06-12")
    execution = make_execution(origin_report_date="2026-06-10")

    linked = link_executions([execution], [event])

    assert linked[0].linked_event_id == event.event_id
    assert linked[0].link_method == "period_overlap"


def test_link_executions_keeps_unmatched_reports_as_unlinked():
    other_corp_event = make_event(corp_code="00000000")
    execution = make_execution(origin_report_date="2026-01-05", period_start=None, period_end=None)

    linked = link_executions([execution], [other_corp_event])

    assert linked[0].linked_event_id is None
    assert linked[0].link_method == "unlinked"


def test_link_executions_maps_trust_status_to_trust_contract_start():
    event = make_event(
        event_id="dart-20260319000100-trust_contract_start",
        event_type="trust_contract_start",
        disclosure_date="2026-03-19",
        period_start="2026-03-19",
        period_end="2026-09-21",
    )
    execution = make_execution(
        rcept_no="20260623000282",
        execution_type="trust_status",
        disclosure_date="2026-06-23",
        origin_report_date="2026-03-19",
        period_start="2026-03-19",
        period_end="2026-09-21",
    )

    linked = link_executions([execution], [event])

    assert linked[0].linked_event_id == event.event_id
    assert linked[0].link_method == "report_date"


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def test_merge_executions_dedupes_by_rcept_no_with_incoming_priority():
    existing = make_execution(actual_shares=1)
    incoming = make_execution(actual_shares=458_373)

    merged = merge_executions([existing], [incoming])

    assert len(merged) == 1
    assert merged[0].actual_shares == 458_373


def test_merge_executions_correction_supersedes_original_report():
    original = make_execution(rcept_no="20260630000100", disclosure_date="2026-06-30")
    correction = make_execution(rcept_no="20260701000608", disclosure_date="2026-07-01")

    merged = merge_executions([original], [correction])

    assert [execution.rcept_no for execution in merged] == ["20260701000608"]


def test_merge_executions_preserves_recurring_trust_status_history():
    first_quarter = make_execution(
        rcept_no="20260623000282",
        execution_type="trust_status",
        disclosure_date="2026-06-23",
        origin_report_date="2026-03-19",
        as_of_date="2026-06-19",
    )
    second_quarter = make_execution(
        rcept_no="20260923000100",
        execution_type="trust_status",
        disclosure_date="2026-09-23",
        origin_report_date="2026-03-19",
        as_of_date="2026-09-19",
    )
    first_quarter_correction = make_execution(
        rcept_no="20260625000900",
        execution_type="trust_status",
        disclosure_date="2026-06-25",
        origin_report_date="2026-03-19",
        as_of_date="2026-06-19",
    )

    merged = merge_executions([first_quarter, second_quarter], [first_quarter_correction])

    # Quarterly reports for the same contract are both kept, but the corrected
    # filing replaces the original one for the same base date.
    assert sorted(execution.rcept_no for execution in merged) == [
        "20260625000900",
        "20260923000100",
    ]


def test_latest_trust_status_by_contract_picks_latest_as_of_per_contract():
    first = make_execution(
        rcept_no="20260623000282",
        execution_type="trust_status",
        disclosure_date="2026-06-23",
        origin_report_date="2026-03-19",
        as_of_date="2026-06-19",
    )
    second = make_execution(
        rcept_no="20260923000100",
        execution_type="trust_status",
        disclosure_date="2026-09-23",
        origin_report_date="2026-03-19",
        as_of_date="2026-09-19",
    )
    other_contract = make_execution(
        rcept_no="20260701000700",
        execution_type="trust_status",
        disclosure_date="2026-07-01",
        origin_report_date="2026-04-02",
        as_of_date="2026-06-30",
    )
    non_trust = make_execution()

    representatives = latest_trust_status_by_contract([first, second, other_contract, non_trust])

    assert sorted(execution.rcept_no for execution in representatives) == [
        "20260701000700",
        "20260923000100",
    ]
