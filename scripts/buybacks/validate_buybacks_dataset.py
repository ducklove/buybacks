from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARKETS = {"KOSPI", "KOSDAQ", "KONEX", "OTHER"}
EVENT_TYPES = {
    "direct_acquisition",
    "direct_disposition",
    "trust_contract_start",
    "trust_contract_end",
    "retirement",
    "periodic_holding_update",
    "unknown",
}
SOURCES = {"DART", "KRX", "MANUAL", "DERIVED"}
QUALITIES = {"complete", "partial", "missing"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dataset(data_dir: Path) -> list[str]:
    errors: list[str] = []
    companies = load(data_dir / "companies.json")
    events = load(data_dir / "events.json")
    holdings = load(data_dir / "holding_snapshots.json")
    reactions = load(data_dir / "price_reactions.json")
    status = load(data_dir / "data_status.json")

    stocks = set()
    event_ids = set()
    for index, company in enumerate(companies):
        if company.get("market") not in MARKETS:
            errors.append(f"companies[{index}] invalid market")
        stock_code = company.get("stock_code")
        if not re.fullmatch(r"\d{6}", str(stock_code or "")):
            errors.append(f"companies[{index}] invalid stock_code")
        if stock_code in stocks:
            errors.append(f"companies[{index}] duplicate stock_code {stock_code}")
        stocks.add(stock_code)

    for index, event in enumerate(events):
        event_id = event.get("event_id")
        if event_id in event_ids:
            errors.append(f"events[{index}] duplicate event_id {event_id}")
        event_ids.add(event_id)
        if event.get("stock_code") not in stocks:
            errors.append(f"events[{index}] unknown stock_code {event.get('stock_code')}")
        if event.get("event_type") not in EVENT_TYPES:
            errors.append(f"events[{index}] invalid event_type")
        if event.get("source") not in SOURCES:
            errors.append(f"events[{index}] invalid source")
        if not ISO_DATE.match(str(event.get("disclosure_date", ""))):
            errors.append(f"events[{index}] invalid disclosure_date")

    for index, snapshot in enumerate(holdings):
        if snapshot.get("stock_code") not in stocks:
            errors.append(f"holding_snapshots[{index}] unknown stock_code")
        ratio = snapshot.get("treasury_ratio")
        if ratio is not None and not 0 <= ratio <= 1:
            errors.append(f"holding_snapshots[{index}] invalid treasury_ratio")

    for index, reaction in enumerate(reactions):
        if reaction.get("event_id") not in event_ids:
            errors.append(f"price_reactions[{index}] unknown event_id")
        if reaction.get("data_quality") not in QUALITIES:
            errors.append(f"price_reactions[{index}] invalid data_quality")

    expected_counts = {
        "companies_count": len(companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(reactions),
    }
    for key, expected in expected_counts.items():
        if status.get(key) != expected:
            errors.append(f"data_status.{key}={status.get(key)} expected {expected}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path, nargs="?", default=Path("public/data/buybacks"))
    args = parser.parse_args()
    errors = validate_dataset(args.data_dir)
    if errors:
        print("Dataset validation failed:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)
    print(f"Dataset validation passed for {args.data_dir}")


if __name__ == "__main__":
    main()

