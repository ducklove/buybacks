from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.models import PriceReaction
    from scripts.buybacks.parsers import normalize_date, parse_number
else:
    from .models import PriceReaction
    from .parsers import normalize_date, parse_number


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


def calculate_price_reaction(
    event_id: str,
    stock_code: str,
    event_date: str,
    stock_prices: Iterable[PriceRow | dict],
    market_prices: Iterable[PriceRow | dict] | None = None,
) -> PriceReaction:
    prices = sorted([coerce_price_row(row) for row in stock_prices], key=lambda row: row.date)
    event_date_norm = normalize_date(event_date) or event_date
    start_index = next((index for index, row in enumerate(prices) if row.date > event_date_norm), None)
    if start_index is None:
        return missing_reaction(event_id, stock_code, event_date_norm)

    base = prices[start_index]

    def ret(offset: int) -> float | None:
        target_index = start_index + offset
        if target_index >= len(prices):
            return None
        return prices[target_index].close / base.close - 1

    return_20d = ret(20)
    market_return_20d = calculate_market_return(market_prices, event_date_norm, 20)
    quality = "complete" if ret(60) is not None else "partial"
    if return_20d is None:
        quality = "missing"

    return PriceReaction(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date_norm,
        close_t0=base.close,
        return_1d=ret(1),
        return_5d=ret(5),
        return_20d=return_20d,
        return_60d=ret(60),
        max_drawdown_20d=max_drawdown(prices[start_index : start_index + 21], base.close),
        max_drawdown_60d=max_drawdown(prices[start_index : start_index + 61], base.close),
        market_return_20d=market_return_20d,
        abnormal_return_20d=return_20d - market_return_20d
        if return_20d is not None and market_return_20d is not None
        else None,
        volume_change_20d=volume_change(prices, start_index, 20),
        data_quality=quality,  # type: ignore[arg-type]
    )


def coerce_price_row(row: PriceRow | dict) -> PriceRow:
    if isinstance(row, PriceRow):
        return row
    row_date = normalize_date(row.get("date") or row.get("basDd") or row.get("TRD_DD"))
    close = parse_number(row.get("close") or row.get("clpr") or row.get("CLSPRC"))
    volume = parse_number(row.get("volume") or row.get("trqu") or row.get("ACC_TRDVOL"))
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
        market_return_20d=None,
        abnormal_return_20d=None,
        volume_change_20d=None,
        data_quality="missing",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("data/fixtures/buybacks/price_reactions.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/buybacks/price_reactions.json"))
    args = parser.parse_args()
    if not os.environ.get("KRX_AUTH_KEY"):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(args.fixtures.read_text(encoding="utf-8"), encoding="utf-8")
        print("KRX_AUTH_KEY not set; copied fixture price reactions")
        return
    print("KRX_AUTH_KEY is set, but treasury execution mapping is adapter-only until official API IDs are confirmed.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(args.fixtures.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()
