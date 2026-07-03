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


def execution(**overrides) -> dict:
    row = {
        "execution_id": "dart-20260620000100-acquisition_result",
        "corp_code": "00126380",
        "stock_code": "005930",
        "corp_name": "Samsung Electronics",
        "execution_type": "acquisition_result",
        "disclosure_date": "2026-06-20",
        "origin_report_date": "2026-06-20",
        "period_start": None,
        "period_end": None,
        "ordered_shares": 1100,
        "actual_shares": 1000,
        "actual_amount_krw": 100_000_000,
        "avg_price_krw": 100_000,
        "planned_amount_krw": 100_000_000,
        "planned_shares": None,
        "shortfall": False,
        "shortfall_reason": None,
        "holding_after_qty": None,
        "holding_after_ratio": None,
        "trust_contract_amount_krw": None,
        "trust_progress_ratio": None,
        "as_of_date": "2026-06-20",
        "linked_event_id": "dart-1-direct_acquisition",
        "link_method": "report_date",
        "source": "DART",
        "rcept_no": "20260620000100",
        "source_url": None,
        "raw_report_name": "자기주식취득결과보고서",
    }
    row.update(overrides)
    return row


def series_row(**overrides) -> dict:
    row = {
        "event_id": "dart-1-direct_acquisition",
        "stock_code": "005930",
        "event_date": "2026-06-20",
        "t0_date": "2026-06-23",
        "daily_return": [0.012, -0.005],
        "daily_abnormal": [0.008, None],
        "data_quality": "partial",
    }
    row.update(overrides)
    return row


def car_payload(**overrides) -> dict:
    payload = {
        "window": 3,
        "min_events": 1,
        "groups": [
            {
                "event_type": "direct_acquisition",
                "market": "ALL",
                "n": 1,
                "mean_car": [0.008, 0.01, None],
            }
        ],
    }
    payload.update(overrides)
    return payload


def write_dataset(
    data_dir,
    holdings,
    executions=None,
    status_overrides=None,
    reaction_series=None,
    car_curves=None,
) -> None:
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
            "planned_shares_common": 1000,
        }
    ]
    reactions = [{"event_id": "dart-1-direct_acquisition", "data_quality": "missing"}]
    status = {
        "companies_count": len(companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(reactions),
        "warnings": [],
        **(status_overrides or {}),
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    payloads = [
        ("companies.json", companies),
        ("events.json", events),
        ("holding_snapshots.json", holdings),
        ("price_reactions.json", reactions),
        ("data_status.json", status),
    ]
    if executions is not None:
        payloads.append(("executions.json", executions))
    if reaction_series is not None:
        payloads.append(("reaction_series.json", reaction_series))
    if car_curves is not None:
        payloads.append(("car_curves.json", car_curves))
    for name, payload in payloads:
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


def test_validate_dataset_accepts_valid_optional_executions(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        executions=[execution()],
        status_overrides={"executions_count": 1},
    )

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert warnings == []


def test_validate_dataset_reports_dangling_execution_link_as_error(tmp_path):
    write_dataset(tmp_path, [holding()], executions=[execution(linked_event_id="missing-event")])

    errors, _ = validate_dataset(tmp_path)

    assert any("unknown linked_event_id" in error for error in errors)


def test_validate_dataset_rejects_unlinked_execution_with_link_target(tmp_path):
    write_dataset(tmp_path, [holding()], executions=[execution(link_method="unlinked")])

    errors, _ = validate_dataset(tmp_path)

    assert any("unlinked row has linked_event_id" in error for error in errors)


def test_validate_dataset_flags_executions_count_mismatch(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        executions=[execution()],
        status_overrides={"executions_count": 5},
    )

    errors, _ = validate_dataset(tmp_path)

    assert any("data_status.executions_count=5 expected 1" in error for error in errors)


def test_validate_dataset_warns_on_completion_rate_anomaly_without_failing(tmp_path):
    # actual_shares far above the linked event's planned shares: warning only.
    write_dataset(tmp_path, [holding()], executions=[execution(actual_shares=5000)])

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert any("completion rate" in warning for warning in warnings)


def test_validate_dataset_warns_on_trust_progress_anomaly(tmp_path):
    trust_row = execution(
        execution_id="dart-20260620000200-trust_status",
        rcept_no="20260620000200",
        execution_type="trust_status",
        linked_event_id=None,
        link_method="unlinked",
        trust_progress_ratio=1.5,
    )
    write_dataset(tmp_path, [holding()], executions=[trust_row])

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert any("completion rate 1.50" in warning for warning in warnings)


def test_validate_dataset_without_executions_file_stays_clean(tmp_path):
    # Datasets built before execution tracking (like the committed public
    # data) have no executions.json and must keep validating with exit 0.
    write_dataset(tmp_path, [holding()])

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert warnings == []


def test_validate_dataset_accepts_valid_optional_series_and_car_curves(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[series_row()],
        car_curves=car_payload(),
        status_overrides={"reaction_series_count": 1, "car_groups_count": 1},
    )

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert warnings == []


def test_validate_dataset_reports_dangling_and_duplicate_series_event_ids(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[
            series_row(),
            series_row(),
            series_row(event_id="missing-event"),
        ],
    )

    errors, _ = validate_dataset(tmp_path)

    assert any("duplicate event_id" in error for error in errors)
    assert any("unknown event_id missing-event" in error for error in errors)


def test_validate_dataset_rejects_series_length_problems(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[
            series_row(daily_return=[0.001] * 61, daily_abnormal=[0.001] * 61),
        ],
    )
    errors, _ = validate_dataset(tmp_path)
    assert any("exceeds 60" in error for error in errors)

    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[series_row(daily_abnormal=[0.008])],
    )
    errors, _ = validate_dataset(tmp_path)
    assert any("!= daily_abnormal length" in error for error in errors)


def test_validate_dataset_warns_on_extreme_daily_returns_without_failing(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[series_row(daily_return=[0.6, -0.01], daily_abnormal=[0.55, None])],
    )

    errors, warnings = validate_dataset(tmp_path)

    assert errors == []
    assert len(warnings) == 1
    assert "beyond +-0.5" in warnings[0]


def test_validate_dataset_rejects_car_groups_below_min_events_and_bad_length(tmp_path):
    bad_car = car_payload(
        min_events=5,
        groups=[
            {
                "event_type": "direct_acquisition",
                "market": "ALL",
                "n": 2,
                "mean_car": [0.01, 0.02],
            }
        ],
    )
    write_dataset(tmp_path, [holding()], car_curves=bad_car)

    errors, _ = validate_dataset(tmp_path)

    assert any("n=2 below min_events 5" in error for error in errors)
    assert any("mean_car length must equal window" in error for error in errors)


def test_validate_dataset_flags_series_and_car_count_mismatches(tmp_path):
    write_dataset(
        tmp_path,
        [holding()],
        reaction_series=[series_row()],
        car_curves=car_payload(),
        status_overrides={"reaction_series_count": 9, "car_groups_count": 9},
    )

    errors, _ = validate_dataset(tmp_path)

    assert any("data_status.reaction_series_count=9 expected 1" in error for error in errors)
    assert any("data_status.car_groups_count=9 expected 1" in error for error in errors)


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
