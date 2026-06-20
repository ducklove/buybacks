from scripts.buybacks.fetch_dart_buybacks import normalize_decision_event, normalize_holding_snapshot
from scripts.buybacks.parsers import classify_event_type, normalize_date, parse_number, parse_ratio_percent


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


def test_classify_event_type():
    assert classify_event_type("주요사항보고서(자기주식취득결정)") == "direct_acquisition"
    assert classify_event_type("주요사항보고서(자기주식처분결정)") == "direct_disposition"
    assert classify_event_type("자기주식취득 신탁계약 체결 결정") == "trust_contract_start"
    assert classify_event_type("자기주식취득 신탁계약 해지 결정") == "trust_contract_end"
    assert classify_event_type("주식소각결정") == "retirement"


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

