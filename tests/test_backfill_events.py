import argparse
import json

from scripts.buybacks.backfill_events import (
    compare_backfill_events,
    date_chunks,
    merge_backfill,
    years_for_range,
)
from scripts.buybacks.build_buybacks_dataset import write_json
from scripts.buybacks.fetch_krx_prices import missing_reaction
from scripts.buybacks.models import BuybackEvent, BuybackExecution, Company, to_jsonable


def event(event_id: str, rcept_no: str | None, disclosure_date: str = "2026-06-01") -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code="00126380",
        stock_code="005930",
        corp_name="Samsung Electronics",
        event_type="direct_acquisition",
        disclosure_date=disclosure_date,
        decision_date=disclosure_date,
        period_start=None,
        period_end=None,
        planned_shares_common=None,
        planned_shares_other=None,
        planned_amount_krw=None,
        planned_amount_common_krw=None,
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
        rcept_no=rcept_no,
        source_url=None,
        raw_report_name=None,
    )


def test_date_chunks_split_backfill_window_at_open_dart_safe_size():
    chunks = date_chunks("20240101", "20240415", 89)

    assert [(chunk.start, chunk.end) for chunk in chunks] == [
        ("20240101", "20240329"),
        ("20240330", "20240415"),
    ]


def test_years_for_range_covers_cross_year_backfill():
    assert years_for_range("20231215", "20240201") == [2023, 2024]


def test_compare_backfill_events_counts_receipt_duplicates_and_new_events():
    duplicate_count, new_count = compare_backfill_events(
        [event("existing", "20260601000001")],
        [
            event("duplicate-by-rcept", "20260601000001"),
            event("new", "20260602000001"),
        ],
    )

    assert duplicate_count == 1
    assert new_count == 1


def execution(rcept_no: str, origin_report_date: str | None) -> BuybackExecution:
    return BuybackExecution(
        execution_id=f"dart-{rcept_no}-acquisition_result",
        corp_code="00126380",
        stock_code="005930",
        corp_name="Samsung Electronics",
        execution_type="acquisition_result",
        disclosure_date="2026-06-20",
        origin_report_date=origin_report_date,
        period_start=None,
        period_end=None,
        ordered_shares=None,
        actual_shares=1000,
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
        as_of_date=None,
        linked_event_id=None,
        link_method="unlinked",
        source="DART",
        rcept_no=rcept_no,
        source_url=None,
        raw_report_name="자기주식취득결과보고서",
    )


def write_merge_fixtures(tmp_path, run_events, run_executions=None) -> argparse.Namespace:
    run_id = "run-1"
    run_dir = tmp_path / "backfills" / run_id
    data_dir = tmp_path / "data"
    company = Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20")
    existing_event = event("dart-20260501000001-direct_acquisition", "20260501000001", "2026-05-01")

    write_json(run_dir / "status.json", {"state": "succeeded", "run_id": run_id})
    write_json(run_dir / "companies.json", to_jsonable([company]))
    write_json(run_dir / "events.json", to_jsonable(run_events))
    if run_executions is not None:
        write_json(run_dir / "executions.json", to_jsonable(run_executions))

    write_json(data_dir / "companies.json", to_jsonable([company]))
    write_json(data_dir / "events.json", to_jsonable([existing_event]))
    write_json(
        data_dir / "price_reactions.json",
        to_jsonable([missing_reaction(existing_event.event_id, "005930", "2026-05-01")]),
    )
    write_json(data_dir / "latest_prices.json", [])
    write_json(
        data_dir / "data_status.json",
        {
            "generated_at": "2026-06-30T00:00:00+00:00",
            "companies_count": 1,
            "events_count": 1,
            "holdings_count": 0,
            "price_reactions_count": 1,
            "latest_prices_count": 0,
            "warnings": [],
        },
    )
    return argparse.Namespace(run_id=run_id, backfill_dir=str(tmp_path / "backfills"), data_dir=str(data_dir))


def test_merge_backfill_links_and_stores_run_executions(tmp_path):
    backfill_event = event("dart-20260601000001-direct_acquisition", "20260601000001", "2026-06-01")
    args = write_merge_fixtures(
        tmp_path,
        run_events=[backfill_event],
        run_executions=[execution("20260620000100", origin_report_date="2026-06-01")],
    )

    status = merge_backfill(args)

    stored = json.loads((tmp_path / "data" / "executions.json").read_text(encoding="utf-8"))
    assert [item["rcept_no"] for item in stored] == ["20260620000100"]
    # Linking runs against the merged events, so the backfilled decision event
    # collected in the same run is matched through its disclosure date.
    assert stored[0]["linked_event_id"] == backfill_event.event_id
    assert stored[0]["link_method"] == "report_date"
    assert status["merge_state"] == "merged"

    data_status = json.loads((tmp_path / "data" / "data_status.json").read_text(encoding="utf-8"))
    assert data_status["executions_count"] == 1


def test_merge_backfill_without_executions_keeps_legacy_behavior(tmp_path):
    args = write_merge_fixtures(
        tmp_path,
        run_events=[event("dart-20260601000001-direct_acquisition", "20260601000001", "2026-06-01")],
        run_executions=None,
    )

    status = merge_backfill(args)

    assert status["merge_state"] == "merged"
    # No executions.json in the run or the dataset: the file must not appear.
    assert not (tmp_path / "data" / "executions.json").exists()
    data_status = json.loads((tmp_path / "data" / "data_status.json").read_text(encoding="utf-8"))
    assert "executions_count" not in data_status
