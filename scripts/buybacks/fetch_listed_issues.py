from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.models import Market
else:
    from .models import Market

NAVER_MARKET_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}"
STOCK_CODE_RE = re.compile(r"^[0-9A-Z]{6}$")


@dataclass(frozen=True, slots=True)
class ListedIssue:
    stock_code: str
    issue_name: str
    market: Market
    is_trading: bool
    source: str = "naver_mobile_market_value"
    # Price fields carried by the same listing response (no extra requests).
    # They feed latest_prices.json; None when the row did not provide them.
    close_price: float | None = None
    change_rate: float | None = None
    market_cap_krw: int | None = None
    traded_date: str | None = None


def fetch_naver_listed_issues(
    markets: Iterable[str] = ("KOSPI", "KOSDAQ"),
    page_size: int = 100,
    pause_seconds: float = 0.05,
    timeout: float = 15.0,
    output: Path | None = None,
) -> list[ListedIssue]:
    issues: list[ListedIssue] = []
    for market in markets:
        page = 1
        while True:
            payload = request_naver_market_page(market, page, page_size, timeout)
            rows = payload.get("stocks") or []
            issues.extend(parse_naver_listed_issues(payload, market))
            total_count = int(payload.get("totalCount") or 0)
            if page * page_size >= total_count or not rows:
                break
            page += 1
            if pause_seconds:
                time.sleep(pause_seconds)
    deduped = dedupe_issues(issues)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([asdict(issue) for issue in deduped], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return deduped


def request_naver_market_page(market: str, page: int, page_size: int, timeout: float) -> dict:
    params = urlencode({"page": str(page), "pageSize": str(page_size)})
    request = Request(
        f"{NAVER_MARKET_URL.format(market=market)}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "value-invest-buybacks/0.1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_naver_listed_issues(payload: dict, fallback_market: str) -> list[ListedIssue]:
    issues: list[ListedIssue] = []
    for row in payload.get("stocks") or []:
        if row.get("stockType") != "domestic" or row.get("stockEndType") != "stock":
            continue
        stock_code = str(row.get("itemCode") or row.get("reutersCode") or "").strip().upper()
        if not STOCK_CODE_RE.fullmatch(stock_code):
            continue
        market = market_from_naver_row(row, fallback_market)
        if market not in {"KOSPI", "KOSDAQ"}:
            continue
        issue_name = str(row.get("stockName") or "").strip()
        if not issue_name:
            continue
        issues.append(
            ListedIssue(
                stock_code=stock_code,
                issue_name=issue_name,
                market=market,  # type: ignore[arg-type]
                is_trading=is_trading_issue(row),
                close_price=listing_close_price(row),
                change_rate=listing_change_rate(row),
                market_cap_krw=listing_market_cap(row),
                traded_date=listing_traded_date(row),
            )
        )
    return issues


def _listing_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text or text in {"-", "N/A"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def listing_close_price(row: dict) -> float | None:
    """Close (or last) price in KRW from closePriceRaw, falling back to closePrice."""
    close = _listing_number(row.get("closePriceRaw"))
    if close is None:
        close = _listing_number(row.get("closePrice"))
    return close if close is not None and close > 0 else None


def listing_change_rate(row: dict) -> float | None:
    """Day change as a fraction (Naver reports percent, e.g. "-1.23")."""
    ratio = _listing_number(row.get("fluctuationsRatioRaw"))
    if ratio is None:
        ratio = _listing_number(row.get("fluctuationsRatio"))
    return round(ratio / 100, 6) if ratio is not None else None


def listing_market_cap(row: dict) -> int | None:
    """Issue market cap in KRW from marketValueRaw (marketValue is in 억원)."""
    raw = _listing_number(row.get("marketValueRaw"))
    if raw is not None and raw > 0:
        return int(raw)
    eok = _listing_number(row.get("marketValue"))
    return int(eok * 100_000_000) if eok is not None and eok > 0 else None


def listing_traded_date(row: dict) -> str | None:
    """KST trade date (YYYY-MM-DD) when the row carries a trade timestamp."""
    for key in ("localTradedAt", "tradedAt", "localTradedDate"):
        match = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})", str(row.get(key) or "").strip())
        if match:
            return "-".join(match.groups())
    return None


def market_from_naver_row(row: dict, fallback_market: str) -> str:
    exchange = row.get("stockExchangeType") or {}
    name = str(exchange.get("nameEng") or exchange.get("name") or fallback_market).upper()
    if name == "KOSDAQ":
        return "KOSDAQ"
    if name == "KOSPI":
        return "KOSPI"
    return "OTHER"


def is_trading_issue(row: dict) -> bool:
    trade_stop = row.get("tradeStopType") or {}
    return str(trade_stop.get("name") or "").upper() == "TRADING" or str(trade_stop.get("code") or "") == "1"


def dedupe_issues(issues: Iterable[ListedIssue]) -> list[ListedIssue]:
    by_code: dict[str, ListedIssue] = {}
    for issue in issues:
        previous = by_code.get(issue.stock_code)
        if previous is None or (issue.is_trading and not previous.is_trading):
            by_code[issue.stock_code] = issue
    return sorted(by_code.values(), key=lambda issue: (issue.market, issue.issue_name, issue.stock_code))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw/buybacks/listed_issues_naver.json"))
    args = parser.parse_args()
    issues = fetch_naver_listed_issues(output=args.output)
    print(f"wrote {len(issues)} listed KOSPI/KOSDAQ stock issues to {args.output}")


if __name__ == "__main__":
    main()
