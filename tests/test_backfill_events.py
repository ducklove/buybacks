from scripts.buybacks.backfill_events import compare_backfill_events, date_chunks, years_for_range
from scripts.buybacks.models import BuybackEvent


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
