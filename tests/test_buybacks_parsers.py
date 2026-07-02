from scripts.buybacks.fetch_dart_buybacks import (
    collect_company_holding_snapshots,
    dedupe_events,
    dedupe_holdings,
    fetch_buyback_disclosures,
    normalize_decision_event,
    normalize_disclosure_events,
    normalize_holding_rows,
    normalize_holding_snapshot,
    normalize_stock_total_snapshots,
    parse_retirement_details_from_html,
)
import scripts.buybacks.fetch_dart_buybacks as dart_buybacks
from scripts.buybacks.models import Company
from scripts.buybacks.parsers import (
    KST,
    classify_event_type,
    kst_today,
    normalize_date,
    parse_number,
    parse_ratio_percent,
)


def test_parse_number_handles_commas_missing_and_negative_markers():
    assert parse_number("9,999,999,999") == 9_999_999_999
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number("0") == 0
    assert parse_number("△1,200") == -1200
    assert parse_number("(3.5)") == -3.5


def test_normalize_date_variants():
    assert normalize_date("20260522") == "2026-05-22"
    assert normalize_date("2026.5.2") == "2026-05-02"
    assert normalize_date("2026년 6월 20일") == "2026-06-20"
    assert normalize_date("-") is None


def test_parse_ratio_percent_converts_percent_to_ratio():
    assert parse_ratio_percent("2.48") == 0.0248
    assert parse_ratio_percent("-") is None


def test_kst_is_utc_plus_nine():
    from datetime import datetime, timedelta

    assert KST.utcoffset(datetime(2026, 7, 3, 12, 0)) == timedelta(hours=9)


def test_kst_today_matches_utc_shifted_by_nine_hours():
    from datetime import datetime, timedelta, timezone

    before = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    today = kst_today()
    after = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

    assert before <= today <= after


def test_classify_event_type():
    assert classify_event_type("주요사항보고서(자기주식취득결정)") == "direct_acquisition"
    assert classify_event_type("주요사항보고서(자기주식처분결정)") == "direct_disposition"
    assert classify_event_type("자기주식취득 신탁계약 체결 결정") == "trust_contract_start"
    assert classify_event_type("자기주식취득 신탁계약 해지 결정") == "trust_contract_end"
    assert classify_event_type("주식소각결정") == "retirement"


def test_fetch_buyback_disclosures_includes_exchange_retirement_reports(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, api_key, raw_dir=None):
            pass

        def request_json(self, endpoint, params):
            calls.append(params["pblntf_ty"])
            if params["pblntf_ty"] == "I":
                return {
                    "total_page": "1",
                    "list": [
                        {
                            "corp_code": "00110893",
                            "corp_name": "대신증권",
                            "stock_code": "003540",
                            "corp_cls": "Y",
                            "report_nm": "주식소각결정",
                            "rcept_no": "20260619800826",
                            "rcept_dt": "20260619",
                        }
                    ],
                }
            return {"total_page": "1", "list": []}

    monkeypatch.setattr(dart_buybacks, "OpenDartClient", FakeClient)

    disclosures, warnings = fetch_buyback_disclosures(
        api_key="fixture",
        bgn_de="20260601",
        end_de="20260630",
        raw_dir=tmp_path,
    )

    assert warnings == []
    assert calls == ["B", "I"]
    assert [item["rcept_no"] for item in disclosures] == ["20260619800826"]


def test_normalize_dart_acquisition_response_fixture():
    item = {
        "rcept_no": "20260522000001",
        "rcept_dt": "20260522",
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "aqpln_stk_ostk": "12,500,000",
        "aqpln_stk_estk": "-",
        "aqpln_prc_ostk": "1,000,000,000,000",
        "aqexpd_bgd": "20260523",
        "aqexpd_edd": "20260822",
        "aq_pp": "주주가치 제고",
        "aq_mth": "장내 직접취득",
        "cs_iv_bk": "복수 위탁",
        "aq_wtn_div_ostk": "148,000,000",
        "aq_wtn_div_ostk_rt": "2.48",
    }
    event = normalize_decision_event(item, "005930", "tsstkAqDecsn.json")
    assert event.event_type == "direct_acquisition"
    assert event.planned_shares_common == 12_500_000
    assert event.planned_amount_krw == 1_000_000_000_000
    assert event.holding_before_ratio_common == 0.0248
    assert event.source_url and event.source_url.endswith("20260522000001")


def test_normalize_decision_event_falls_back_to_receipt_number_date():
    item = {
        "rcept_no": "20260617000504",
        "corp_code": "00111722",
        "corp_name": "Mirae Asset Securities",
        "aqpln_stk_ostk": "3,898,635",
        "aqpln_stk_estk": "7,090,936",
        "aqpln_prc_ostk": "200,000,000,000",
        "aqpln_prc_estk": "100,000,000,000",
    }

    event = normalize_decision_event(item, "006800", "tsstkAqDecsn.json")

    assert event.disclosure_date == "2026-06-17"
    assert event.planned_shares_common == 3_898_635
    assert event.planned_shares_other == 7_090_936
    assert event.planned_amount_common_krw == 200_000_000_000
    assert event.planned_amount_other_krw == 100_000_000_000
    assert event.planned_amount_krw == 300_000_000_000


def test_normalize_holding_snapshot_computes_ratio_when_issued_shares_exists():
    item = {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "stlm_dt": "2025-12-31",
        "stock_knd": "보통주",
        "bsis_qy": "100",
        "change_qy_acqs": "30",
        "change_qy_dsps": "10",
        "change_qy_incnr": "5",
        "trmend_qy": "115",
        "isu_stock_totqy": "1000",
        "rcept_no": "20260314000001",
    }
    snapshot = normalize_holding_snapshot(item, "005930", 2025, "11011")
    assert snapshot.ending_qty == 115
    assert snapshot.floating_shares == 885
    assert snapshot.treasury_ratio == 0.115


def test_normalize_disposition_uses_official_period_and_method_fields():
    item = {
        "rcept_no": "20260512000001",
        "rcept_dt": "20260512",
        "corp_code": "00266961",
        "corp_name": "NAVER",
        "dppln_stk_ostk": "180,000",
        "dppln_prc_ostk": "30,000,000,000",
        "dpprpd_bgd": "20260513",
        "dpprpd_edd": "20260612",
        "dp_pp": "임직원 주식보상",
        "dp_m_ovtm": "180,000",
        "aq_wtn_div_ostk": "3,500,000",
        "aq_wtn_div_ostk_rt": "2.15",
    }
    event = normalize_decision_event(item, "035420", "tsstkDpDecsn.json")
    assert event.event_type == "direct_disposition"
    assert event.period_start == "2026-05-13"
    assert event.period_end == "2026-06-12"
    assert event.method == "시간외대량매매 180,000주"
    assert event.holding_before_ratio_common == 0.0215


def test_normalize_disclosure_event_adds_retirement_metadata_when_structured_row_missing():
    events = normalize_disclosure_events(
        [
            {
                "rcept_no": "20260601000001",
                "rcept_dt": "20260601",
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "report_nm": "주식소각결정",
            }
        ],
        "005930",
        existing_rcept_nos=set(),
        retirement_details_by_rcept_no={
            "20260601000001": {
                "planned_shares_common": 1_553_637,
                "planned_shares_other": 1_005_000,
                "planned_amount_krw": 66_496_435_400,
                "planned_share_ratio_common": 0.031564,
                "planned_share_ratio_other": 0.024707,
                "decision_date": "2026-06-01",
                "period_end": "2026-06-10",
                "method": "기취득 자기주식",
            }
        },
    )
    assert len(events) == 1
    assert events[0].event_type == "retirement"
    assert events[0].planned_shares_common == 1_553_637
    assert events[0].planned_shares_other == 1_005_000
    assert events[0].planned_amount_krw == 66_496_435_400
    assert events[0].planned_share_ratio_common == 0.031564
    assert events[0].source_url.endswith("20260601000001")


def test_parse_retirement_details_from_viewer_html_extracts_shares_amount_and_ratios():
    html = """
    <table>
      <tr><td>1. 소각할 주식의 종류와 수</td><td>보통주식 (주)</td><td>1,553,637</td></tr>
      <tr><td></td><td>종류주식 (주)</td><td>1,005,000</td></tr>
      <tr><td>2. 발행주식 총수</td><td>보통주식 (주)</td><td>49,219,763</td></tr>
      <tr><td></td><td>종류주식 (주)</td><td>40,675,895</td></tr>
      <tr><td>4. 소각예정금액(원)</td><td>66,496,435,400</td></tr>
      <tr><td>6. 소각할 주식의 취득방법</td><td>기취득 자기주식</td></tr>
      <tr><td>7. 소각 예정일</td><td>2026-06-29</td></tr>
      <tr><td>9. 이사회결의일(결정일)</td><td>2026-06-19</td></tr>
    </table>
    """

    details = parse_retirement_details_from_html(html)

    assert details["planned_shares_common"] == 1_553_637
    assert details["planned_shares_other"] == 1_005_000
    assert details["planned_amount_krw"] == 66_496_435_400
    assert details["planned_share_ratio_common"] == 1_553_637 / 49_219_763
    assert details["planned_share_ratio_other"] == 1_005_000 / 40_675_895
    assert details["decision_date"] == "2026-06-19"
    assert details["period_end"] == "2026-06-29"
    assert details["method"] == "기취득 자기주식"


def test_dedupe_events_prefers_more_complete_duplicate():
    sparse = normalize_disclosure_events(
        [
            {
                "rcept_no": "20260601000001",
                "rcept_dt": "20260601",
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "report_nm": "주식소각결정",
            }
        ],
        "005930",
        existing_rcept_nos=set(),
    )[0]
    detailed = normalize_disclosure_events(
        [
            {
                "rcept_no": "20260601000001",
                "rcept_dt": "20260601",
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "report_nm": "주식소각결정",
            }
        ],
        "005930",
        existing_rcept_nos=set(),
        retirement_details_by_rcept_no={"20260601000001": {"planned_shares_common": 100}},
    )[0]

    events = dedupe_events([sparse, detailed])

    assert len(events) == 1
    assert events[0].planned_shares_common == 100


def test_normalize_holding_rows_merges_stock_total_denominator():
    rows = [
        {
            "corp_code": "00126380",
            "corp_name": "삼성전자",
            "stlm_dt": "2025-12-31",
            "stock_knd": "보통주",
            "acqs_mth1": "총계",
            "acqs_mth2": "총계",
            "acqs_mth3": "총계",
            "bsis_qy": "100",
            "change_qy_acqs": "30",
            "change_qy_dsps": "10",
            "change_qy_incnr": "5",
            "trmend_qy": "115",
        }
    ]
    stock_totals = [
        {
            "corp_code": "00126380",
            "corp_name": "삼성전자",
            "se": "보통주",
            "stlm_dt": "2025-12-31",
            "istc_totqy": "1,000",
            "tesstk_co": "115",
            "distb_stock_co": "885",
        }
    ]
    snapshots = normalize_holding_rows(rows, stock_totals, "005930", 2025, "11011")
    assert len(snapshots) == 1
    assert snapshots[0].issued_shares == 1000
    assert snapshots[0].floating_shares == 885
    assert snapshots[0].treasury_ratio == 0.115


def test_stock_total_snapshot_stores_total_and_treasury_share_counts():
    snapshots = normalize_stock_total_snapshots(
        [
            {
                "corp_code": "00126380",
                "corp_name": "Samsung Electronics",
                "se": "\uBCF4\uD1B5\uC8FC",
                "stlm_dt": "2025-12-31",
                "istc_totqy": "1,000",
                "tesstk_co": "115",
                "distb_stock_co": "885",
                "rcept_no": "20260314000001",
            }
        ],
        "005930",
        2025,
        "11011",
    )

    assert len(snapshots) == 1
    assert snapshots[0].ending_qty == 115
    assert snapshots[0].issued_shares == 1000
    assert snapshots[0].floating_shares == 885
    assert snapshots[0].treasury_ratio == 0.115


def test_collect_holding_snapshots_can_use_stock_totals_only():
    calls = []

    class FakeClient:
        def request_json(self, endpoint, params):
            calls.append(endpoint)
            assert endpoint == "stockTotqySttus.json"
            return {
                "list": [
                    {
                        "corp_code": params["corp_code"],
                        "corp_name": "Samsung Electronics",
                        "se": "\uBCF4\uD1B5\uC8FC",
                        "stlm_dt": "2025-12-31",
                        "istc_totqy": "1,000",
                        "tesstk_co": "115",
                        "distb_stock_co": "885",
                    }
                ]
            }

    company = Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20")
    snapshots, warnings = collect_company_holding_snapshots(
        FakeClient(),
        company,
        [2025],
        ["11011"],
        include_treasury_tables=False,
    )

    assert calls == ["stockTotqySttus.json"]
    assert warnings == []
    assert snapshots[0].ending_qty == 115
    assert snapshots[0].issued_shares == 1000


def test_holding_rows_ignore_placeholder_stock_kind_duplicates():
    rows = [
        {
            "corp_code": "00301112",
            "corp_name": "Samhwa Networks",
            "stlm_dt": "2025-12-31",
            "stock_knd": "\uBCF4\uD1B5\uC8FC",
            "trmend_qy": "3,583,547",
            "isu_stock_totqy": "43,172,933",
            "rcept_no": "20260318000485",
        },
        {
            "corp_code": "00301112",
            "corp_name": "Samhwa Networks",
            "stlm_dt": "2025-12-31",
            "stock_knd": "-",
            "trmend_qy": "3,583,547",
            "isu_stock_totqy": "43,172,933",
            "rcept_no": "20260318000485",
        },
    ]

    snapshots = normalize_holding_rows(rows, [], "046390", 2025, "11011")

    assert len(snapshots) == 1
    assert snapshots[0].stock_kind == "\uBCF4\uD1B5\uC8FC"


def test_dedupe_holdings_drops_placeholder_duplicate_fact():
    common = normalize_holding_snapshot(
        {
            "corp_code": "00301112",
            "corp_name": "Samhwa Networks",
            "stlm_dt": "2025-12-31",
            "stock_knd": "\uBCF4\uD1B5\uC8FC",
            "trmend_qy": "3,583,547",
            "isu_stock_totqy": "43,172,933",
        },
        "046390",
        2025,
        "11011",
    )
    placeholder = normalize_holding_snapshot(
        {
            "corp_code": "00301112",
            "corp_name": "Samhwa Networks",
            "stlm_dt": "2025-12-31",
            "stock_knd": "-",
            "trmend_qy": "3,583,547",
            "isu_stock_totqy": "43,172,933",
        },
        "046390",
        2025,
        "11011",
    )

    snapshots = dedupe_holdings([placeholder, common])

    assert len(snapshots) == 1
    assert snapshots[0].stock_kind == "\uBCF4\uD1B5\uC8FC"
