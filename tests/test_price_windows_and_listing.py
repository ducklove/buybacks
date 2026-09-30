"""R5-R6: index window union, listing-based latest prices, compact output, shrink guard."""

import argparse
import json
from datetime import date, timedelta

import pytest

from scripts.buybacks import build_buybacks_dataset as build
from scripts.buybacks import fetch_krx_prices as prices
from scripts.buybacks.fetch_listed_issues import ListedIssue, parse_naver_listed_issues
from scripts.buybacks.models import BuybackEvent, Company, LatestPriceSnapshot
from scripts.buybacks.validate_buybacks_dataset import shrink_errors

PAGE = 100  # KIS index daily TR returns a capped page


def trading_days(start: date, end: date) -> list[str]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


INDEX_DAYS = trading_days(date(2024, 10, 1), date(2026, 9, 25))
INDEX_ROWS = [{"date": day, "close": 2000 + index} for index, day in enumerate(INDEX_DAYS)]


def forward_page(anchor: date) -> list[dict]:
    """Upstream variant 1: up to PAGE rows from the anchor forward."""
    return [row for row in INDEX_ROWS if row["date"] >= anchor.isoformat()][:PAGE]


def backward_page(anchor: date) -> list[dict]:
    """Upstream variant 2: up to PAGE rows ending at the anchor."""
    return [row for row in INDEX_ROWS if row["date"] <= anchor.isoformat()][-PAGE:]


def event(event_id: str, disclosure_date: str, stock_code: str) -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code="0",
        stock_code=stock_code,
        corp_name="Company",
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
        rcept_no=None,
        source_url=None,
        raw_report_name=None,
    )


@pytest.mark.parametrize("pager", [forward_page, backward_page], ids=["forward", "backward"])
def test_fetch_index_rows_pages_until_the_whole_window_is_covered(pager):
    class Client:
        calls: list[date] = []

        def index_history(self, market, start_date):
            self.calls.append(start_date)
            return pager(start_date)

    client = Client()
    rows, warnings = prices.fetch_index_rows(client, "kospi", date(2025, 1, 6), date(2026, 6, 1))

    assert warnings == []
    dates = [row.date for row in rows]
    assert dates == sorted(set(dates))
    assert dates[0] <= "2025-01-06"
    assert dates[-1] >= "2026-05-29"
    assert 3 <= len(client.calls) < prices.INDEX_HISTORY_MAX_CALLS


def test_fetch_index_rows_stops_when_the_api_does_not_advance():
    class Client:
        calls = 0

        def index_history(self, market, start_date):
            self.calls += 1
            return INDEX_ROWS[:5]  # ignores the anchor entirely

    client = Client()
    rows, _ = prices.fetch_index_rows(client, "kospi", date(2024, 9, 1), date(2026, 6, 1))
    assert len(rows) == 5
    assert client.calls <= 3


@pytest.mark.parametrize("pager", [forward_page, backward_page], ids=["forward", "backward"])
def test_old_event_gets_market_return_when_a_newer_stock_is_iterated_first(monkeypatch, pager):
    # dedupe_events sorts newest first, so the first stock's window used to be
    # the only index window: the 2025 event got no index rows at all.
    events = [event("new", "2026-03-02", "000660"), event("old", "2025-02-03", "005930")]
    companies = [
        Company("1", "000660", "SK hynix", "KOSPI", None, "2026-06-30"),
        Company("2", "005930", "Samsung", "KOSPI", None, "2026-06-30"),
    ]
    index_calls: list[tuple[str, date]] = []

    def fake_stock_history(self, stock_code, start_date, end_date):
        return [
            {"date": row["date"], "close": 100 + index, "volume": 1000}
            for index, row in enumerate(INDEX_ROWS)
            if start_date.isoformat() <= row["date"] <= end_date.isoformat()
        ]

    def fake_index_history(self, market, start_date):
        index_calls.append((market, start_date))
        return pager(start_date)

    monkeypatch.setattr(prices.KISProxyPriceClient, "stock_history", fake_stock_history)
    monkeypatch.setattr(prices.KISProxyPriceClient, "index_history", fake_index_history)
    monkeypatch.setattr(prices, "kst_today", lambda: date(2026, 9, 30))

    reactions, series, warnings = prices.calculate_kis_proxy_price_reactions(
        events, companies, base_url="http://proxy.local"
    )

    by_id = {reaction.event_id: reaction for reaction in reactions}
    assert warnings == []
    assert by_id["old"].market_return_20d is not None
    assert by_id["new"].market_return_20d is not None
    # The index market is fetched as one window (paged), never per stock.
    assert {market for market, _ in index_calls} == {"kospi"}
    assert all(item.daily_abnormal[0] is not None for item in series)


def test_kis_proxy_index_market_is_case_insensitive():
    assert prices.kis_proxy_index_market("KOSDAQ") == "kosdaq"
    assert prices.kis_proxy_index_market("kosdaq") == "kosdaq"
    assert prices.kis_proxy_index_market("KOSPI") == "kospi"
    assert prices.kis_proxy_index_market("OTHER") == "kospi"


def naver_row(code, name, **extra):
    row = {
        "stockType": "domestic",
        "stockEndType": "stock",
        "itemCode": code,
        "stockName": name,
        "tradeStopType": {"code": "1", "name": "TRADING"},
        "stockExchangeType": {"nameEng": "KOSPI"},
    }
    row.update(extra)
    return row


def test_parse_listing_keeps_price_fields_from_the_same_response():
    issues = parse_naver_listed_issues(
        {
            "stocks": [
                naver_row(
                    "005930",
                    "삼성전자",
                    closePrice="84,300",
                    closePriceRaw="84300",
                    fluctuationsRatio="-1.23",
                    marketValue="5,032,540",
                    marketValueRaw="503254000000000",
                    localTradedAt="2026-09-29T16:10:00+09:00",
                ),
                naver_row("00680K", "미래에셋증권2우B", closePrice="7,000", marketValue="1,234"),
                naver_row("000660", "SK하이닉스"),
            ]
        },
        "KOSPI",
    )
    by_code = {issue.stock_code: issue for issue in issues}

    assert by_code["005930"].close_price == 84300
    assert by_code["005930"].change_rate == pytest.approx(-0.0123)
    assert by_code["005930"].market_cap_krw == 503254000000000
    assert by_code["005930"].traded_date == "2026-09-29"
    assert by_code["00680K"].close_price == 7000
    assert by_code["00680K"].market_cap_krw == 123_400_000_000
    assert by_code["00680K"].traded_date is None
    assert by_code["000660"].close_price is None


def latest_args(**overrides):
    values = {"price_source": "auto", "latest_price_lookback_days": 10}
    values.update(overrides)
    return argparse.Namespace(**values)


def listed(code, close, traded_date=None):
    return ListedIssue(code, code, "KOSPI", True, close_price=close, change_rate=0.01, traded_date=traded_date)


def test_latest_prices_come_from_the_listing_and_kis_proxy_only_fills_gaps(monkeypatch):
    kis_calls: list[list[str]] = []

    def fake_kis(codes, base_url, token="", lookback_days=10, as_of=None):
        codes = list(codes)
        kis_calls.append(codes)
        return [LatestPriceSnapshot(code, "2026-09-29", 500.0, "kis_proxy") for code in codes], []

    monkeypatch.setenv("KIS_PROXY_URL", "http://proxy.local")
    monkeypatch.setattr(build, "calculate_kis_proxy_latest_prices", fake_kis)
    issues = [listed("005930", 84300.0, "2026-09-29"), listed("000660", 180000.0), listed("035420", None)]

    snapshots, warnings, source = build.build_latest_prices(
        latest_args(), ["005930", "000660", "035420", "999999"], issues
    )

    by_code = {snapshot.stock_code: snapshot for snapshot in snapshots}
    assert source == "naver_listing+kis_proxy"
    assert warnings == []
    assert by_code["005930"].source == "naver_listing"
    assert by_code["005930"].close == 84300.0
    assert by_code["000660"].price_date == "2026-09-29"  # listing-wide trade date
    # Only codes without a listing close go to kis_proxy, in one batch.
    assert kis_calls == [["035420", "999999"]]
    assert by_code["035420"].source == "kis_proxy"


def test_listing_without_trade_date_is_dated_by_one_kis_probe(monkeypatch):
    kis_calls: list[list[str]] = []

    def fake_kis(codes, base_url, token="", lookback_days=10, as_of=None):
        codes = list(codes)
        kis_calls.append(codes)
        return [LatestPriceSnapshot(code, "2026-09-26", 1.0, "kis_proxy") for code in codes], []

    monkeypatch.setenv("KIS_PROXY_URL", "http://proxy.local")
    monkeypatch.setattr(build, "calculate_kis_proxy_latest_prices", fake_kis)
    issues = [listed("005930", 84300.0), listed("000660", 180000.0)]

    snapshots, _, source = build.build_latest_prices(latest_args(), ["000660", "005930"], issues)

    assert kis_calls == [["005930"]]
    assert source == "naver_listing"
    assert {snapshot.price_date for snapshot in snapshots} == {"2026-09-26"}
    assert [snapshot.stock_code for snapshot in snapshots] == ["000660", "005930"]


def test_listing_prices_work_without_kis_proxy_when_rows_are_dated(monkeypatch):
    monkeypatch.delenv("KIS_PROXY_URL", raising=False)
    issues = [listed("005930", 84300.0, "2026-09-29")]

    snapshots, warnings, source = build.build_latest_prices(latest_args(), ["005930", "000660"], issues)

    assert [snapshot.stock_code for snapshot in snapshots] == ["005930"]
    assert source == "naver_listing"
    assert any("000660" not in warning and "1 stocks" in warning for warning in warnings)


def test_dataset_arrays_are_written_one_compact_record_per_line(tmp_path):
    path = tmp_path / "events.json"
    rows = [{"event_id": "a", "name": "삼성"}, {"event_id": "b", "value": None}]

    build.write_json(path, rows)

    text = path.read_text(encoding="utf-8")
    assert text == '[\n{"event_id":"a","name":"삼성"},\n{"event_id":"b","value":null}\n]\n'
    assert json.loads(text) == rows
    build.write_json(path, [])
    assert path.read_text(encoding="utf-8") == "[]\n"
    build.write_json(tmp_path / "data_status.json", {"a": 1})
    assert (tmp_path / "data_status.json").read_text(encoding="utf-8") == '{\n  "a": 1\n}\n'


def test_price_reaction_floats_are_rounded_to_six_decimals(tmp_path):
    path = tmp_path / "price_reactions.json"
    build.write_price_reactions(
        path,
        [{"event_id": "e", "close_t0": 7990.0, "return_1d": 0.010676156583629859, "return_5d": None}],
    )
    row = json.loads(path.read_text(encoding="utf-8"))[0]
    assert row == {"event_id": "e", "close_t0": 7990.0, "return_1d": 0.010676, "return_5d": None}


def write_rows(directory, name, count):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps([{"i": index} for index in range(count)]), encoding="utf-8")


def test_shrink_guard_allows_small_drops_and_fails_large_ones(tmp_path):
    baseline, current = tmp_path / "baseline", tmp_path / "current"
    write_rows(baseline, "events.json", 1000)
    write_rows(baseline, "holding_snapshots.json", 1000)
    write_rows(baseline, "executions.json", 100)
    write_rows(current, "events.json", 985)  # -1.5%: tolerated
    write_rows(current, "holding_snapshots.json", 900)  # -10%: purge
    write_rows(current, "executions.json", 120)  # growth is always fine

    errors = shrink_errors(current, baseline)

    assert len(errors) == 1
    assert errors[0].startswith("holding_snapshots shrank from 1000 to 900 rows (-10.0%)")


def test_shrink_guard_skips_files_missing_from_the_baseline(tmp_path):
    baseline, current = tmp_path / "baseline", tmp_path / "current"
    write_rows(baseline, "events.json", 10)
    write_rows(current, "events.json", 10)
    assert shrink_errors(current, baseline) == []
    # A file that disappeared entirely counts as zero rows.
    write_rows(baseline, "executions.json", 10)
    assert shrink_errors(current, baseline)[0].startswith("executions shrank from 10 to 0 rows")
