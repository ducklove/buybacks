import pytest

import scripts.buybacks.fetch_dart_buybacks as dart_buybacks
from scripts.buybacks.fetch_dart_buybacks import (
    FIELD_ALIASES,
    all_null_ratio_warning,
    collect_dart_holding_snapshots,
    core_field_coverage_warnings,
    get_aliased,
    normalize_decision_event,
    normalize_holding_snapshot,
)
from scripts.buybacks.models import Company


def test_get_aliased_returns_first_present_candidate():
    assert get_aliased({"ctr_prc": "5,000"}, "trust_amount_krw") == "5,000"
    assert get_aliased({"trctr_prc": "5,000"}, "trust_amount_krw") == "5,000"
    assert get_aliased({"ctr_prc": "1", "trctr_prc": "2"}, "trust_amount_krw") == "1"


def test_get_aliased_skips_placeholder_values():
    item = {"ctr_prc": "-", "ctr_prc_bfcc": "", "trctr_prc": "5,000"}
    assert get_aliased(item, "trust_amount_krw") == "5,000"


def test_get_aliased_handles_missing_item_and_absent_fields():
    assert get_aliased(None, "trust_amount_krw") is None
    assert get_aliased({}, "trust_amount_krw") is None
    assert get_aliased({"unrelated": "1"}, "trust_amount_krw") is None


def test_get_aliased_rejects_unknown_logical_name():
    with pytest.raises(KeyError):
        get_aliased({"any": "value"}, "no_such_logical_field")


def test_field_aliases_cover_decision_and_holding_core_fields():
    for logical_name in [
        "acq_planned_shares_common",
        "acq_planned_amount_common_krw",
        "disp_planned_shares_common",
        "trust_amount_krw",
        "holding_ending_qty",
        "holding_issued_shares",
        "stock_total_issued_shares",
        "stock_total_treasury_qty",
    ]:
        assert FIELD_ALIASES[logical_name], logical_name


def test_normalize_disposition_falls_back_to_legacy_period_field_names():
    item = {
        "rcept_no": "20260512000001",
        "rcept_dt": "20260512",
        "corp_code": "00266961",
        "corp_name": "NAVER",
        "dppln_stk_ostk": "180,000",
        "dpprd_bgd": "20260513",
        "dpprd_edd": "20260612",
    }

    event = normalize_decision_event(item, "035420", "tsstkDpDecsn.json")

    assert event.period_start == "2026-05-13"
    assert event.period_end == "2026-06-12"
    assert event.planned_shares_common == 180_000


def test_normalize_disposition_ignores_placeholder_primary_period_field():
    item = {
        "rcept_no": "20260512000001",
        "rcept_dt": "20260512",
        "dpprpd_bgd": "-",
        "dpprd_bgd": "20260513",
    }

    event = normalize_decision_event(item, "035420", "tsstkDpDecsn.json")

    assert event.period_start == "2026-05-13"


def test_normalize_holding_snapshot_uses_stock_total_issued_share_fallbacks():
    item = {
        "corp_code": "00126380",
        "corp_name": "Samsung",
        "stlm_dt": "2025-12-31",
        "stock_knd": "보통주",
        "trmend_qy": "115",
    }
    stock_total = {"now_to_isu_stock_totqy": "1,000"}

    snapshot = normalize_holding_snapshot(item, "005930", 2025, "11011", stock_total)

    assert snapshot.ending_qty == 115
    assert snapshot.issued_shares == 1000
    assert snapshot.treasury_ratio == 0.115


def test_normalize_holding_snapshot_takes_ending_qty_from_stock_total_when_missing():
    item = {
        "corp_code": "00126380",
        "corp_name": "Samsung",
        "stlm_dt": "2025-12-31",
        "stock_knd": "보통주",
    }
    stock_total = {"istc_totqy": "1,000", "tesstk_co": "115", "distb_stock_co": "885"}

    snapshot = normalize_holding_snapshot(item, "005930", 2025, "11011", stock_total)

    assert snapshot.ending_qty == 115
    assert snapshot.issued_shares == 1000
    assert snapshot.floating_shares == 885


def test_normalize_holding_snapshot_keeps_computed_floating_when_distb_is_placeholder():
    item = {
        "corp_code": "00126380",
        "corp_name": "Samsung",
        "stlm_dt": "2025-12-31",
        "stock_knd": "보통주",
        "trmend_qy": "115",
        "isu_stock_totqy": "1,000",
    }
    stock_total = {"distb_stock_co": "-"}

    snapshot = normalize_holding_snapshot(item, "005930", 2025, "11011", stock_total)

    assert snapshot.floating_shares == 885


def null_decision_event(rcept_no: str):
    return normalize_decision_event(
        {"rcept_no": rcept_no, "rcept_dt": "20260620"},
        "005930",
        "tsstkAqDecsn.json",
    )


def filled_decision_event(rcept_no: str):
    return normalize_decision_event(
        {"rcept_no": rcept_no, "rcept_dt": "20260620", "aqpln_stk_ostk": "1,000"},
        "005930",
        "tsstkAqDecsn.json",
    )


def null_holding_snapshot():
    return normalize_holding_snapshot(
        {"corp_code": "00126380", "corp_name": "Samsung", "stock_knd": "보통주"},
        "005930",
        2025,
        "11011",
    )


def filled_holding_snapshot():
    return normalize_holding_snapshot(
        {
            "corp_code": "00126380",
            "corp_name": "Samsung",
            "stock_knd": "보통주",
            "trmend_qy": "115",
            "isu_stock_totqy": "1,000",
        },
        "005930",
        2025,
        "11011",
    )


def test_all_null_ratio_warning_reports_counts_above_threshold():
    events = [null_decision_event("1"), filled_decision_event("2")]
    warning = all_null_ratio_warning(events, ("planned_shares_common",), 0.5, "records look empty")
    assert warning is not None
    assert "1/2" in warning
    assert "FIELD_ALIASES" in warning


def test_all_null_ratio_warning_silent_below_threshold_or_empty():
    events = [null_decision_event("1"), filled_decision_event("2"), filled_decision_event("3")]
    assert all_null_ratio_warning(events, ("planned_shares_common",), 0.5, "records look empty") is None
    assert all_null_ratio_warning([], ("planned_shares_common",), 0.5, "records look empty") is None


def test_core_field_coverage_warns_when_decision_events_are_all_null():
    warnings = core_field_coverage_warnings([null_decision_event("1"), null_decision_event("2")], [])
    assert len(warnings) == 1
    assert "decision events" in warnings[0]


def test_core_field_coverage_warns_when_holdings_lack_share_counts():
    warnings = core_field_coverage_warnings([], [null_holding_snapshot()])
    assert len(warnings) == 1
    assert "holding snapshots" in warnings[0]


def test_core_field_coverage_quiet_for_healthy_records():
    warnings = core_field_coverage_warnings(
        [filled_decision_event("1")],
        [filled_holding_snapshot()],
    )
    assert warnings == []


def test_collect_holding_snapshots_warns_on_renamed_dart_fields(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, api_key, raw_dir=None):
            pass

        def request_json(self, endpoint, params):
            if endpoint == "tesstkAcqsDspsSttus.json":
                return {
                    "list": [
                        {
                            "corp_code": params["corp_code"],
                            "corp_name": "Samsung Electronics",
                            "stock_knd": "보통주",
                            "stlm_dt": "2025-12-31",
                            # Renamed quantity fields simulate a DART format change.
                            "trmend_qy_v2": "115",
                            "isu_stock_totqy_v2": "1,000",
                        }
                    ]
                }
            raise dart_buybacks.OpenDartNoData("no stock totals")

    monkeypatch.setattr(dart_buybacks, "OpenDartClient", FakeClient)

    company = Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20")
    holdings, warnings = collect_dart_holding_snapshots(
        api_key="fixture",
        companies=[company],
        years=[2025],
        raw_dir=tmp_path,
        report_codes=["11011"],
    )

    assert len(holdings) == 1
    assert holdings[0].ending_qty is None
    assert any("holding snapshots" in warning and "FIELD_ALIASES" in warning for warning in warnings)
