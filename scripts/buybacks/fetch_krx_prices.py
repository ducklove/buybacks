from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.models import (
        BuybackEvent,
        Company,
        LatestPriceSnapshot,
        PriceReaction,
        ReactionSeries,
    )
    from scripts.buybacks.parsers import kst_today, normalize_date, parse_number
else:
    from .models import BuybackEvent, Company, LatestPriceSnapshot, PriceReaction, ReactionSeries
    from .parsers import kst_today, normalize_date, parse_number

LOGGER = logging.getLogger(__name__)

# Maximum trading days stored per event in reaction_series.json (t+1..t+60).
REACTION_SERIES_WINDOW = 60
# Stored series values are rounded to keep the JSON payload compact.
SERIES_DECIMALS = 6


@dataclass(frozen=True)
class PriceRow:
    date: str
    close: float
    volume: float | None = None


class KRXPriceClient:
    """Minimal official Open API client.

    KRX treasury execution endpoints are intentionally not scraped from web UI calls.
    Add endpoint IDs only after official API service approval and license confirmation.
    """

    base_url = "https://openapi.krx.co.kr/contents/OPP/USES/service"

    def __init__(self, auth_key: str, timeout: float = 12.0) -> None:
        self.auth_key = auth_key
        self.timeout = timeout

    def request_json(self, endpoint_path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}/{endpoint_path}?{urlencode(params)}"
        request = Request(url, headers={"AUTH_KEY": self.auth_key, "User-Agent": "value-invest-buybacks/0.1"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


class KISProxyPriceClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request_json(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        headers = {"User-Agent": "value-invest-buybacks/0.1"}
        if self.token:
            headers["X-KIS-Proxy-Token"] = self.token
        request = Request(url, headers=headers)
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def stock_history(self, stock_code: str, start_date: date, end_date: date) -> list[dict]:
        payload = self.request_json(
            f"/v1/stocks/{stock_code}/history",
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "period": "D",
                "adjusted": "true",
            },
        )
        return payload.get("items", [])

    def index_history(self, market: str, start_date: date) -> list[dict]:
        payload = self.request_json(
            f"/v1/indexes/{kis_proxy_index_market(market)}/history",
            {
                "start_date": start_date.isoformat(),
                "period": "D",
            },
        )
        return payload.get("items", [])


def calculate_kis_proxy_price_reactions(
    events: Iterable[BuybackEvent],
    companies: Iterable[Company],
    base_url: str,
    token: str = "",
) -> tuple[list[PriceReaction], list[ReactionSeries], list[str]]:
    client = KISProxyPriceClient(base_url=base_url, token=token)
    event_list = list(events)
    company_by_stock = {company.stock_code: company for company in companies}
    events_by_stock: dict[str, list[BuybackEvent]] = {}
    for event in event_list:
        events_by_stock.setdefault(event.stock_code, []).append(event)

    warnings: list[str] = []
    stock_prices: dict[str, list[PriceRow]] = {}
    market_prices: dict[str, list[PriceRow]] = {}

    # The index window is the union of every stock window in the same market, so
    # old and new events alike get index rows (the index used to be fetched with
    # only the first-iterated stock's start date, leaving ~35% of older events
    # without market-relative returns or silently misaligned).
    stock_windows: dict[str, tuple[date, date]] = {}
    index_windows: dict[str, tuple[date, date]] = {}
    for stock_code, stock_events in events_by_stock.items():
        company = company_by_stock.get(stock_code)
        index_market = kis_proxy_index_market(company.market if company else "OTHER")
        window = price_window(stock_events)
        stock_windows[stock_code] = window
        index_windows[index_market] = union_window(index_windows.get(index_market), window)

    for stock_code, (start_date, end_date) in stock_windows.items():
        try:
            stock_prices[stock_code] = [coerce_price_row(row) for row in client.stock_history(stock_code, start_date, end_date)]
        except Exception as exc:  # noqa: BLE001 - live price enrichment should not break DART data.
            warnings.append(f"kis_proxy stock history failed for {stock_code}: {exc}")
            stock_prices[stock_code] = []

    for index_market, (start_date, end_date) in index_windows.items():
        try:
            market_prices[index_market], index_warnings = fetch_index_rows(client, index_market, start_date, end_date)
            warnings.extend(index_warnings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"kis_proxy index history failed for {index_market}: {exc}")
            market_prices[index_market] = []

    reactions: list[PriceReaction] = []
    series_list: list[ReactionSeries] = []
    for event in event_list:
        company = company_by_stock.get(event.stock_code)
        index_market = kis_proxy_index_market(company.market if company else "OTHER")
        prices = stock_prices.get(event.stock_code, [])
        if not prices:
            reactions.append(missing_reaction(event.event_id, event.stock_code, event.disclosure_date))
            continue
        # The daily return series is derived from the same fetched price rows
        # as the reaction snapshot, so no extra proxy requests are made.
        reaction, series = calculate_price_reaction_with_series(
            event.event_id,
            event.stock_code,
            event.disclosure_date,
            prices,
            market_prices.get(index_market) or None,
        )
        reactions.append(reaction)
        if series is not None:
            series_list.append(series)
    return reactions, series_list, warnings


def union_window(current: tuple[date, date] | None, window: tuple[date, date]) -> tuple[date, date]:
    if current is None:
        return window
    return min(current[0], window[0]), max(current[1], window[1])


# Upper bound on index-history requests per market and build. Each KIS index
# call returns a capped page (~100 trading days), so a multi-year backfill
# window needs several pages; the cap only guards against a non-advancing API.
INDEX_HISTORY_MAX_CALLS = 40


def fetch_index_rows(
    client: "KISProxyPriceClient",
    market: str,
    start_date: date,
    end_date: date,
    max_calls: int = INDEX_HISTORY_MAX_CALLS,
) -> tuple[list[PriceRow], list[str]]:
    """Fetch index closes covering start_date..end_date, paging as needed.

    The kis-proxy index endpoint takes a single anchor date and returns a
    capped page. Depending on the upstream TR the page runs forward from the
    anchor or backward to it, so the first page (anchored at start_date) is
    used to detect the direction and the remaining pages walk the window in
    that direction. Rows are de-duplicated by date and returned sorted.
    """
    rows: dict[str, PriceRow] = {}
    calls = 0
    start_iso, end_iso = start_date.isoformat(), end_date.isoformat()

    def page(anchor: date) -> list[PriceRow]:
        nonlocal calls
        calls += 1
        batch = [coerce_price_row(row) for row in client.index_history(market, anchor)]
        for row in batch:
            rows[row.date] = row
        return batch

    first = page(start_date)
    if first and max(row.date for row in first) > start_iso:
        # Forward pages: continue after the newest row until end_date is covered.
        newest = max(row.date for row in first)
        while calls < max_calls and newest < end_iso:
            batch = page(parse_iso_date(newest) + timedelta(days=1))
            batch_newest = max((row.date for row in batch), default=newest)
            if batch_newest <= newest:
                break
            newest = batch_newest
    else:
        # Backward pages (or an empty first page): walk back from end_date.
        cursor = end_date
        while calls < max_calls:
            batch = page(cursor)
            if not batch:
                break
            oldest = min(row.date for row in batch)
            if oldest <= start_iso:
                break
            next_cursor = parse_iso_date(oldest) - timedelta(days=1)
            if next_cursor >= cursor:
                break
            cursor = next_cursor

    warnings: list[str] = []
    ordered = [rows[key] for key in sorted(rows)]
    if calls >= max_calls:
        warnings.append(f"kis_proxy index history for {market} stopped after {calls} pages")
    if ordered and ordered[0].date > start_iso:
        LOGGER.info("index %s history starts %s (requested %s)", market, ordered[0].date, start_iso)
    return ordered, warnings


def calculate_kis_proxy_latest_prices(
    stock_codes: Iterable[str],
    base_url: str,
    token: str = "",
    lookback_days: int = 10,
    as_of: date | None = None,
) -> tuple[list[LatestPriceSnapshot], list[str]]:
    client = KISProxyPriceClient(base_url=base_url, token=token)
    end_date = as_of or kst_today()  # Korean trading dates, so "today" is KST.
    start_date = end_date - timedelta(days=lookback_days)
    snapshots: list[LatestPriceSnapshot] = []
    warnings: list[str] = []

    for stock_code in sorted(set(stock_codes)):
        try:
            prices = [coerce_price_row(row) for row in client.stock_history(stock_code, start_date, end_date)]
        except Exception as exc:  # noqa: BLE001 - missing latest prices should not break DART data.
            warnings.append(f"kis_proxy latest price failed for {stock_code}: {exc}")
            continue
        snapshot = latest_price_snapshot(stock_code, prices)
        if snapshot is None:
            warnings.append(f"kis_proxy latest price missing for {stock_code}")
            continue
        snapshots.append(snapshot)

    return snapshots, warnings


def latest_price_snapshot(
    stock_code: str,
    stock_prices: Iterable[PriceRow | dict],
    source: str = "kis_proxy",
) -> LatestPriceSnapshot | None:
    prices = sorted([coerce_price_row(row) for row in stock_prices], key=lambda row: row.date)
    if not prices:
        return None
    latest = prices[-1]
    previous = prices[-2] if len(prices) >= 2 else None
    change_rate = latest.close / previous.close - 1 if previous and previous.close > 0 else None
    return LatestPriceSnapshot(
        stock_code=stock_code,
        price_date=latest.date,
        close=latest.close,
        source=source,
        change_rate=change_rate,
    )


def calculate_price_reaction(
    event_id: str,
    stock_code: str,
    event_date: str,
    stock_prices: Iterable[PriceRow | dict],
    market_prices: Iterable[PriceRow | dict] | None = None,
) -> PriceReaction:
    reaction, _series = calculate_price_reaction_with_series(
        event_id,
        stock_code,
        event_date,
        stock_prices,
        market_prices,
    )
    return reaction


def calculate_price_reaction_with_series(
    event_id: str,
    stock_code: str,
    event_date: str,
    stock_prices: Iterable[PriceRow | dict],
    market_prices: Iterable[PriceRow | dict] | None = None,
) -> tuple[PriceReaction, ReactionSeries | None]:
    """Calculate the reaction snapshot and its daily return series in one pass.

    Both outputs share the same t0 definition (first trading day after the
    event date) and the same fetched price rows. The series is None when no
    post-event price data exists (the reaction is then "missing").
    """
    prices = sorted([coerce_price_row(row) for row in stock_prices], key=lambda row: row.date)
    event_date_norm = normalize_date(event_date) or event_date
    start_index = next((index for index, row in enumerate(prices) if row.date > event_date_norm), None)
    if start_index is None:
        return missing_reaction(event_id, stock_code, event_date_norm), None

    market_rows = (
        sorted([coerce_price_row(row) for row in market_prices], key=lambda row: row.date)
        if market_prices is not None
        else None
    )
    base = prices[start_index]

    def ret(offset: int) -> float | None:
        target_index = start_index + offset
        if target_index >= len(prices):
            return None
        return prices[target_index].close / base.close - 1

    return_1d = ret(1)
    return_5d = ret(5)
    return_20d = ret(20)
    return_60d = ret(60)
    max_drawdown_20d = max_drawdown(prices[start_index : start_index + 21], base.close)
    max_drawdown_60d = max_drawdown(prices[start_index : start_index + 61], base.close)
    market_return_5d = calculate_market_return(market_rows, event_date_norm, 5)
    market_return_20d = calculate_market_return(market_rows, event_date_norm, 20)
    market_return_60d = calculate_market_return(market_rows, event_date_norm, 60)
    volume_change_20d = volume_change(prices, start_index, 20)
    quality = price_data_quality(
        close_t0=base.close,
        return_1d=return_1d,
        return_5d=return_5d,
        return_20d=return_20d,
        return_60d=return_60d,
        max_drawdown_20d=max_drawdown_20d,
        max_drawdown_60d=max_drawdown_60d,
        volume_change_20d=volume_change_20d,
    )

    reaction = PriceReaction(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date_norm,
        close_t0=base.close,
        return_1d=return_1d,
        return_5d=return_5d,
        return_20d=return_20d,
        return_60d=return_60d,
        max_drawdown_20d=max_drawdown_20d,
        max_drawdown_60d=max_drawdown_60d,
        market_return_5d=market_return_5d,
        abnormal_return_5d=return_5d - market_return_5d
        if return_5d is not None and market_return_5d is not None
        else None,
        market_return_20d=market_return_20d,
        abnormal_return_20d=return_20d - market_return_20d
        if return_20d is not None and market_return_20d is not None
        else None,
        market_return_60d=market_return_60d,
        abnormal_return_60d=return_60d - market_return_60d
        if return_60d is not None and market_return_60d is not None
        else None,
        volume_change_20d=volume_change_20d,
        data_quality=quality,  # type: ignore[arg-type]
    )
    series = build_reaction_series(event_id, stock_code, event_date_norm, prices, start_index, market_rows)
    return reaction, series


def build_reaction_series(
    event_id: str,
    stock_code: str,
    event_date: str,
    prices: list[PriceRow],
    start_index: int,
    market_rows: list[PriceRow] | None,
    window: int = REACTION_SERIES_WINDOW,
) -> ReactionSeries:
    """Build the t+1..t+window daily return series from already-sorted rows.

    daily_return[k] = close(t+k+1) / close(t+k) - 1 (per trading day, not
    versus the t0 close). daily_abnormal subtracts the daily index return at
    the same trading-day offset from the index's own t0 (the same positional
    alignment used by the abnormal_return_Nd snapshot fields); entries are
    None wherever the index row is unavailable.
    """
    raw_daily: list[float] = []
    for offset in range(1, window + 1):
        target_index = start_index + offset
        if target_index >= len(prices):
            break
        raw_daily.append(prices[target_index].close / prices[target_index - 1].close - 1)
    raw_market_daily = market_daily_returns(market_rows, event_date, len(raw_daily))
    daily_return = [round(value, SERIES_DECIMALS) for value in raw_daily]
    daily_abnormal = [
        round(raw_daily[index] - market_value, SERIES_DECIMALS) if market_value is not None else None
        for index, market_value in enumerate(raw_market_daily)
    ]
    return ReactionSeries(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date,
        t0_date=prices[start_index].date,
        daily_return=daily_return,
        daily_abnormal=daily_abnormal,
        data_quality="complete" if len(daily_return) >= window else "partial",
    )


def market_daily_returns(
    market_rows: list[PriceRow] | None,
    event_date: str,
    length: int,
) -> list[float | None]:
    if not market_rows or length == 0:
        return [None] * length
    start_index = next((index for index, row in enumerate(market_rows) if row.date > event_date), None)
    if start_index is None:
        return [None] * length
    returns: list[float | None] = []
    for offset in range(1, length + 1):
        target_index = start_index + offset
        if target_index >= len(market_rows):
            returns.append(None)
        else:
            returns.append(market_rows[target_index].close / market_rows[target_index - 1].close - 1)
    return returns


def price_data_quality(
    *,
    close_t0: float | None,
    return_1d: float | None,
    return_5d: float | None,
    return_20d: float | None,
    return_60d: float | None,
    max_drawdown_20d: float | None,
    max_drawdown_60d: float | None,
    volume_change_20d: float | None,
) -> str:
    if return_60d is not None:
        return "complete"
    if any(
        value is not None
        for value in [
            close_t0,
            return_1d,
            return_5d,
            return_20d,
            max_drawdown_20d,
            max_drawdown_60d,
            volume_change_20d,
        ]
    ):
        return "partial"
    return "missing"


def coerce_price_row(row: PriceRow | dict) -> PriceRow:
    if isinstance(row, PriceRow):
        return row
    row_date = normalize_date(
        row.get("date")
        or row.get("basDd")
        or row.get("TRD_DD")
        or row.get("stck_bsop_date")
        or row.get("datetime")
    )
    close = parse_number(
        row.get("close")
        or row.get("clpr")
        or row.get("CLSPRC")
        or row.get("stck_clpr")
        or row.get("bstp_nmix_prpr")
        or row.get("current_price")
    )
    volume = parse_number(
        row.get("volume")
        or row.get("trqu")
        or row.get("ACC_TRDVOL")
        or row.get("acml_vol")
        or row.get("cntg_vol")
    )
    if row_date is None or close is None:
        raise ValueError(f"invalid price row: {row}")
    return PriceRow(row_date, float(close), float(volume) if volume is not None else None)


def calculate_market_return(
    market_prices: Iterable[PriceRow | dict] | None,
    event_date: str,
    offset: int,
) -> float | None:
    if market_prices is None:
        return None
    rows = sorted([coerce_price_row(row) for row in market_prices], key=lambda row: row.date)
    start_index = next((index for index, row in enumerate(rows) if row.date > event_date), None)
    if start_index is None or start_index + offset >= len(rows):
        return None
    return rows[start_index + offset].close / rows[start_index].close - 1


def price_window(events: list[BuybackEvent]) -> tuple[date, date]:
    dates = [parse_iso_date(event.disclosure_date) for event in events]
    start_date = min(dates) - timedelta(days=10)
    end_date = min(max(dates) + timedelta(days=140), kst_today())  # Korean trading dates, so "today" is KST.
    return start_date, end_date


def parse_iso_date(value: str) -> date:
    normalized = normalize_date(value) or value
    return datetime.strptime(normalized, "%Y-%m-%d").date()


def kis_proxy_index_market(market: str) -> str:
    return "kosdaq" if str(market).upper() == "KOSDAQ" else "kospi"


def max_drawdown(rows: list[PriceRow], base_close: float) -> float | None:
    if len(rows) < 2:
        return None
    peak = base_close
    worst = 0.0
    for row in rows:
        peak = max(peak, row.close)
        worst = min(worst, row.close / peak - 1)
    return worst


def volume_change(rows: list[PriceRow], start_index: int, window: int) -> float | None:
    before = [row.volume for row in rows[max(0, start_index - window) : start_index] if row.volume is not None]
    after = [row.volume for row in rows[start_index : start_index + window] if row.volume is not None]
    if not before or not after:
        return None
    before_avg = sum(before) / len(before)
    after_avg = sum(after) / len(after)
    return after_avg / before_avg - 1 if before_avg else None


def missing_reaction(event_id: str, stock_code: str, event_date: str) -> PriceReaction:
    return PriceReaction(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date,
        close_t0=None,
        return_1d=None,
        return_5d=None,
        return_20d=None,
        return_60d=None,
        max_drawdown_20d=None,
        max_drawdown_60d=None,
        market_return_5d=None,
        abnormal_return_5d=None,
        market_return_20d=None,
        abnormal_return_20d=None,
        market_return_60d=None,
        abnormal_return_60d=None,
        volume_change_20d=None,
        data_quality="missing",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("data/fixtures/buybacks/price_reactions.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/buybacks/price_reactions.json"))
    args = parser.parse_args()
    if not os.environ.get("KIS_PROXY_URL"):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(args.fixtures.read_text(encoding="utf-8"), encoding="utf-8")
        LOGGER.info("KIS_PROXY_URL not set; copied fixture price reactions")
        return
    LOGGER.info("Use build_buybacks_dataset.py to calculate event-specific reactions from kis_proxy.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(args.fixtures.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    main()
