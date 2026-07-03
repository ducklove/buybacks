from scripts.buybacks.build_buybacks_dataset import (
    merge_reaction_series,
    reaction_series_coverage_warnings,
    select_price_reaction_events,
)
from scripts.buybacks.car_curves import aggregate_car_curves, cumulative_abnormal
from scripts.buybacks.fetch_krx_prices import (
    KISProxyPriceClient,
    PriceRow,
    calculate_kis_proxy_price_reactions,
    calculate_price_reaction,
    calculate_price_reaction_with_series,
)
from scripts.buybacks.models import BuybackEvent, Company, PriceReaction, ReactionSeries


def make_prices(length=70):
    return [
        PriceRow(date=f"2026-01-{day:02d}", close=100 + day, volume=1000 + day * 10)
        for day in range(1, length + 1)
        if day <= 31
    ] + [
        PriceRow(date=f"2026-02-{day:02d}", close=132 + day, volume=1300 + day * 10)
        for day in range(1, 29)
    ] + [
        PriceRow(date=f"2026-03-{day:02d}", close=161 + day, volume=1600 + day * 10)
        for day in range(1, 20)
    ]


def make_market_prices():
    return [PriceRow(date=row.date, close=200 + index, volume=None) for index, row in enumerate(make_prices(), start=1)]


def event(event_id: str, disclosure_date: str, stock_code: str = "005930", event_type: str = "direct_acquisition") -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code="00126380",
        stock_code=stock_code,
        corp_name="Company",
        event_type=event_type,  # type: ignore[arg-type]
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
        rcept_no=None,
        source_url=None,
        raw_report_name=None,
    )


def reaction(event_id: str, event_date: str, quality: str = "partial") -> PriceReaction:
    complete = quality == "complete"
    return PriceReaction(
        event_id=event_id,
        stock_code="005930",
        event_date=event_date,
        close_t0=100,
        return_1d=0.01,
        return_5d=0.02 if complete else None,
        return_20d=0.03 if complete else None,
        return_60d=0.05 if complete else None,
        max_drawdown_20d=None,
        max_drawdown_60d=None,
        market_return_5d=0.01 if complete else None,
        abnormal_return_5d=0.01 if complete else None,
        market_return_20d=0.01 if complete else None,
        abnormal_return_20d=0.02 if complete else None,
        market_return_60d=0.02 if complete else None,
        abnormal_return_60d=0.03 if complete else None,
        volume_change_20d=None,
        data_quality=quality,  # type: ignore[arg-type]
    )


def series(event_id: str, event_date: str, daily_abnormal=None, stock_code: str = "005930") -> ReactionSeries:
    abnormal = daily_abnormal if daily_abnormal is not None else [0.01]
    return ReactionSeries(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date,
        t0_date=event_date,
        daily_return=[0.01] * len(abnormal),
        daily_abnormal=abnormal,
        data_quality="partial",
    )


def test_series_uses_next_trading_day_t0_and_daily_returns():
    reaction_result, series_result = calculate_price_reaction_with_series(
        event_id="event-1",
        stock_code="005930",
        event_date="2026-01-10",
        stock_prices=make_prices(),
    )

    assert series_result is not None
    assert series_result.event_id == "event-1"
    assert series_result.event_date == "2026-01-10"
    assert series_result.t0_date == "2026-01-11"
    # 78 rows leave 67 trading days after t0: capped at the 60-day window.
    assert len(series_result.daily_return) == 60
    assert len(series_result.daily_abnormal) == 60
    assert series_result.data_quality == "complete"
    # Daily simple returns between consecutive trading days, not vs the t0 close.
    assert series_result.daily_return[0] == round(112 / 111 - 1, 6)
    assert series_result.daily_return[1] == round(113 / 112 - 1, 6)
    # Without market prices every abnormal entry stays null.
    assert all(value is None for value in series_result.daily_abnormal)
    # The snapshot half of the pair matches the unchanged public function.
    assert reaction_result == calculate_price_reaction(
        "event-1", "005930", "2026-01-10", make_prices()
    )


def test_series_daily_abnormal_subtracts_daily_index_return():
    _, series_result = calculate_price_reaction_with_series(
        event_id="event-2",
        stock_code="005930",
        event_date="2026-01-10",
        stock_prices=make_prices(),
        market_prices=make_market_prices(),
    )

    assert series_result is not None
    stock_daily = 112 / 111 - 1
    market_daily = 212 / 211 - 1  # market t0 close is 211 at the same offset
    assert series_result.daily_abnormal[0] == round(stock_daily - market_daily, 6)
    assert all(value is not None for value in series_result.daily_abnormal)


def test_series_is_partial_and_short_near_the_data_edge():
    _, series_result = calculate_price_reaction_with_series(
        event_id="event-3",
        stock_code="005930",
        event_date="2026-03-17",
        stock_prices=make_prices(),
    )

    assert series_result is not None
    assert series_result.t0_date == "2026-03-18"
    assert series_result.daily_return == [round(180 / 179 - 1, 6)]
    assert series_result.daily_abnormal == [None]
    assert series_result.data_quality == "partial"


def test_series_is_omitted_without_any_post_event_prices():
    reaction_result, series_result = calculate_price_reaction_with_series(
        event_id="event-4",
        stock_code="005930",
        event_date="2026-04-01",
        stock_prices=make_prices(),
    )

    assert reaction_result.data_quality == "missing"
    assert series_result is None


def test_calculate_kis_proxy_price_reactions_returns_series_from_same_fetch(monkeypatch):
    events = [event("e1", "2026-01-10"), event("e2", "2026-01-10", stock_code="999999")]
    companies = [Company("00126380", "005930", "Samsung", "KOSPI", None, "2026-06-30")]
    stock_history_calls: list[str] = []

    def fake_stock_history(self, stock_code, start_date, end_date):
        stock_history_calls.append(stock_code)
        if stock_code == "005930":
            return [{"date": row.date, "close": row.close, "volume": row.volume} for row in make_prices()]
        return []

    def fake_index_history(self, market, start_date):
        return [{"date": row.date, "close": row.close} for row in make_market_prices()]

    monkeypatch.setattr(KISProxyPriceClient, "stock_history", fake_stock_history)
    monkeypatch.setattr(KISProxyPriceClient, "index_history", fake_index_history)

    reactions, series_list, warnings = calculate_kis_proxy_price_reactions(
        events, companies, base_url="http://proxy.local"
    )

    assert [item.event_id for item in reactions] == ["e1", "e2"]
    assert reactions[1].data_quality == "missing"
    # One series per event with data; no extra per-series price fetches happen.
    assert [item.event_id for item in series_list] == ["e1"]
    assert sorted(stock_history_calls) == ["005930", "999999"]
    assert series_list[0].daily_abnormal[0] is not None
    assert warnings == []


def test_aggregate_car_curves_hand_computed_three_event_case():
    events_payload = [
        {"event_id": "a", "event_type": "direct_acquisition", "stock_code": "111111"},
        {"event_id": "b", "event_type": "direct_acquisition", "stock_code": "222222"},
        {"event_id": "c", "event_type": "direct_acquisition", "stock_code": "333333"},
    ]
    companies_payload = [
        {"stock_code": "111111", "market": "KOSPI"},
        {"stock_code": "222222", "market": "KOSPI"},
        {"stock_code": "333333", "market": "KOSDAQ"},
    ]
    series_payload = [
        {"event_id": "a", "stock_code": "111111", "daily_abnormal": [0.01, 0.02]},
        {"event_id": "b", "stock_code": "222222", "daily_abnormal": [0.03]},
        {"event_id": "c", "stock_code": "333333", "daily_abnormal": [-0.01, 0.01, 0.02]},
    ]

    curves = aggregate_car_curves(series_payload, events_payload, companies_payload, window=3, min_events=1)

    assert curves["window"] == 3
    assert curves["min_events"] == 1
    groups = {(group["event_type"], group["market"]): group for group in curves["groups"]}
    assert set(groups) == {
        ("direct_acquisition", "ALL"),
        ("direct_acquisition", "KOSPI"),
        ("direct_acquisition", "KOSDAQ"),
    }
    # Per-event CARs: a -> [0.01, 0.03], b -> [0.03], c -> [-0.01, 0.0, 0.02].
    all_group = groups[("direct_acquisition", "ALL")]
    assert all_group["n"] == 3
    assert all_group["mean_car"][0] == round((0.01 + 0.03 - 0.01) / 3, 6)
    # b's series ends before k=1, so only a and c contribute there.
    assert all_group["mean_car"][1] == round((0.03 + 0.0) / 2, 6)
    assert all_group["mean_car"][2] == 0.02
    kospi = groups[("direct_acquisition", "KOSPI")]
    assert kospi["n"] == 2
    assert kospi["mean_car"] == [0.02, 0.03, None]
    kosdaq = groups[("direct_acquisition", "KOSDAQ")]
    assert kosdaq["n"] == 1
    assert kosdaq["mean_car"] == [-0.01, 0.0, 0.02]


def test_aggregate_car_curves_drops_small_groups_and_dangling_series():
    events_payload = [{"event_id": "a", "event_type": "direct_acquisition", "stock_code": "111111"}]
    companies_payload = [{"stock_code": "111111", "market": "KOSPI"}]
    series_payload = [
        {"event_id": "a", "stock_code": "111111", "daily_abnormal": [0.01]},
        {"event_id": "gone", "stock_code": "999999", "daily_abnormal": [0.5]},
    ]

    curves = aggregate_car_curves(series_payload, events_payload, companies_payload, window=60, min_events=5)

    assert curves["groups"] == []


def test_cumulative_abnormal_stops_at_first_null_entry():
    assert cumulative_abnormal([0.01, None, 0.02]) == [0.01]
    assert cumulative_abnormal([]) == []
    assert cumulative_abnormal([0.01, -0.005]) == [0.01, 0.005]


def test_merge_reaction_series_replaces_prunes_and_keeps_unrefreshed():
    events_list = [event("new", "2026-06-20"), event("old", "2026-05-01")]
    existing = [
        series("old", "2026-05-01", [0.01]),
        series("gone", "2026-04-01", [0.02]),
    ]
    refreshed = [series("new", "2026-06-20", [0.03])]

    merged = merge_reaction_series(existing, refreshed, events_list)

    # gone's event disappeared (dedupe): its series is dropped; old is kept
    # even though it was not refreshed; ordering matches price_reactions.
    assert [item.event_id for item in merged] == ["new", "old"]
    assert merged[1].daily_abnormal == [0.01]

    replaced = merge_reaction_series(existing, [series("old", "2026-05-01", [0.09])], events_list)
    assert [item.event_id for item in replaced] == ["old"]
    assert replaced[0].daily_abnormal == [0.09]


def test_select_price_reaction_events_scope_missing_series_adds_events_without_series():
    events_list = [
        event("complete-no-series", "2026-01-01"),
        event("complete-with-series", "2026-01-02"),
        event("recent-partial", "2026-06-10"),
    ]
    reactions = [
        reaction("complete-no-series", "2026-01-01", "complete"),
        reaction("complete-with-series", "2026-01-02", "complete"),
        reaction("recent-partial", "2026-06-10", "partial"),
    ]

    default_scope = select_price_reaction_events(events_list, reactions, set(), 30, "20260621")
    assert [item.event_id for item in default_scope] == ["recent-partial"]

    missing_series = select_price_reaction_events(
        events_list,
        reactions,
        set(),
        30,
        "20260621",
        scope="missing-series",
        series_event_ids={"complete-with-series", "recent-partial"},
    )
    assert [item.event_id for item in missing_series] == ["complete-no-series", "recent-partial"]

    full = select_price_reaction_events(
        events_list,
        reactions,
        set(),
        30,
        "20260621",
        scope="all",
        series_event_ids={"complete-with-series"},
    )
    assert [item.event_id for item in full] == [item.event_id for item in events_list]


def test_reaction_series_coverage_warnings_reports_missing_only():
    assert reaction_series_coverage_warnings(10, 10) == []
    warnings = reaction_series_coverage_warnings(10, 7)
    assert len(warnings) == 1
    assert "3 of 10" in warnings[0]
    assert "missing-series" in warnings[0]
