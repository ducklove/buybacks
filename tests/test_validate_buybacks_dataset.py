import json
import sys

import pytest

from scripts.buybacks.validate_buybacks_dataset import holding_flow_warnings, main, validate_dataset


def holding(**overrides) -> dict:
    snapshot = {
        "corp_code": "00126380",
        "stock_code": "005930",
        "corp_name": "Samsung Electronics",
        "as_of_date": "2025-12-31",
        "report_year": 2025,
        "report_code": "11011",
        "stock_kind": "보통주",
        "beginning_qty": 100,
        "acquired_qty": 30,
        "disposed_qty": 10,
        "retired_qty": 5,
        "ending_qty": 115,
        "issued_shares": 1000,
        "treasury_ratio": 0.115,
        "floating_shares": 885,
        "source_rcept_no": None,
    }
    snapshot.update(overrides)
    return snapshot


def test_holding_flow_warnings_pass_for_consistent_snapshot():
    assert holding_flow_warnings([holding()]) == []


def test_holding_flow_warnings_report_mismatch_with_diff():
    warnings = holding_flow_warnings([holding(ending_qty=999)])

    assert len(warnings) == 1
    assert "flow mismatch" in warnings[0]
    assert "115" in warnings[0]
    assert "999" in warnings[0]
    assert "005930" in warnings[0]


def test_holding_flow_warnings_skip_snapshots_with_null_or_non_numeric_fields():
    assert holding_flow_warnings([holding(beginning_qty=None)]) == []
    assert holding_flow_warnings([holding(retired_qty=None)]) == []
    assert holding_flow_warnings([holding(acquired_qty="30")]) == []


def write_dataset(data_dir, holdings) -> None:
    companies = [
        {
            "corp_code": "00126380",
            "stock_code": "005930",
            "corp_name": "Samsung Electronics",
            "market": "KOSPI",
            "sector": None,
            "last_updated": "2026-06-20",
        }
    ]
    events = [
        {
            "event_id": "dart-1-direct_acquisition",
            "stock_code": "005930",
            "event_type": "direct_acquisition",
            "source": "DART",
            "disclosure_date": "2026-06-20",
        }
    ]
    reactions = [{"event_id": "dart-1-direct_acquisition", "data_quality": "missing"}]
    status = {
        "companies_count": len(companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(reactions),
        "warnings": [],
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in [
        ("companies.json", companies),
        ("events.json", events),
        ("holding_snapshots.json", holdings),
        ("price_reactions.json", reactions),
        ("data_status.json", status),
    ]:
        (data_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_validate_dataset_reports_flow_violation_as_warning_not_error(tmp_path):
    write_dataset(tmp_path, [holding(ending_qty=999)])

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert len(warnings) == 1
    assert "flow mismatch" in warnings[0]


def test_validate_dataset_still_fails_on_structural_errors(tmp_path):
    write_dataset(tmp_path, [holding(stock_code="UNKNWN")])

    errors, warnings = validate_dataset(tmp_path)

    assert any("unknown stock_code" in error for error in errors)


def test_main_exits_zero_when_only_flow_warnings_exist(tmp_path, monkeypatch, capsys):
    write_dataset(tmp_path, [holding(ending_qty=999)])
    monkeypatch.setattr(sys, "argv", ["validate_buybacks_dataset.py", str(tmp_path)])

    main()  # No SystemExit means exit code 0.

    output = capsys.readouterr().out
    assert "flow mismatch" in output
    assert "Dataset validation passed" in output


def test_main_exits_nonzero_on_structural_error(tmp_path, monkeypatch):
    write_dataset(tmp_path, [holding(stock_code="UNKNWN")])
    monkeypatch.setattr(sys, "argv", ["validate_buybacks_dataset.py", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
