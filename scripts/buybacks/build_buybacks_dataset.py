from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.fetch_dart_buybacks import collect_dart_dataset
    from scripts.buybacks.models import Company, to_jsonable
else:
    from .fetch_dart_buybacks import collect_dart_dataset
    from .models import Company, to_jsonable

DATA_FILES = [
    "companies.json",
    "events.json",
    "holding_snapshots.json",
    "price_reactions.json",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_fixture_dataset(fixture_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in DATA_FILES:
        shutil.copyfile(fixture_dir / file_name, output_dir / file_name)
    status = load_json(fixture_dir / "data_status.json")
    status["generated_at"] = datetime.now(timezone.utc).isoformat()
    status["dart_available"] = False
    status["krx_available"] = False
    write_json(output_dir / "data_status.json", status)
    return status


def build_live_dataset(args: argparse.Namespace, api_key: str, output_dir: Path) -> dict:
    fixture_dir = Path(args.fixture_dir)
    companies_payload = load_json(fixture_dir / "companies.json")
    stock_codes = {code.strip() for code in args.stock_codes.split(",") if code.strip()}
    companies = [Company(**item) for item in companies_payload if item["stock_code"] in stock_codes]
    years = [int(part) for part in args.years.split(",") if part]
    live_companies, events, holdings, warnings = collect_dart_dataset(
        api_key=api_key,
        companies=companies,
        bgn_de=args.start,
        end_de=args.end,
        years=years,
        raw_dir=Path(args.raw_dir),
    )
    if not events and not holdings:
        warnings.append("OpenDART returned no live buyback rows for selected sample companies; fixture data kept.")
        return copy_fixture_dataset(fixture_dir, output_dir)

    price_reactions = load_json(fixture_dir / "price_reactions.json")
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dart_available": True,
        "krx_available": bool(os.environ.get("KRX_AUTH_KEY")),
        "companies_count": len(live_companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(price_reactions),
        "warnings": [
            *warnings,
            "KRX treasury execution details remain fixture/adapter data until official API IDs are confirmed.",
        ],
    }
    write_json(output_dir / "companies.json", to_jsonable(live_companies))
    write_json(output_dir / "events.json", to_jsonable(events))
    write_json(output_dir / "holding_snapshots.json", to_jsonable(holdings))
    write_json(output_dir / "price_reactions.json", price_reactions)
    write_json(output_dir / "data_status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/data/buybacks")
    parser.add_argument("--fixture-dir", default="data/fixtures/buybacks")
    parser.add_argument("--raw-dir", default="data/raw/buybacks")
    parser.add_argument("--live-if-available", action="store_true")
    parser.add_argument("--stock-codes", default="005930,000660,035420,051910,005380,035900")
    parser.add_argument("--start", default="20250101")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--years", default="2025")
    args = parser.parse_args()

    output_dir = Path(args.output)
    api_key = os.environ.get("DART_API_KEY")
    if args.live_if_available and api_key:
        status = build_live_dataset(args, api_key, output_dir)
    else:
        status = copy_fixture_dataset(Path(args.fixture_dir), output_dir)
    print(
        "generated buybacks dataset: "
        f"{status['companies_count']} companies, {status['events_count']} events, "
        f"{status['holdings_count']} holdings"
    )


if __name__ == "__main__":
    main()
