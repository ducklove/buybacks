from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.fetch_corp_codes import fetch_corp_codes
    from scripts.buybacks.fetch_dart_buybacks import collect_dart_dataset, fetch_buyback_disclosures
    from scripts.buybacks.fetch_krx_prices import missing_reaction
    from scripts.buybacks.models import Company, to_jsonable
    from scripts.buybacks.parsers import market_from_corp_cls, normalize_date
else:
    from .fetch_corp_codes import fetch_corp_codes
    from .fetch_dart_buybacks import collect_dart_dataset, fetch_buyback_disclosures
    from .fetch_krx_prices import missing_reaction
    from .models import Company, to_jsonable
    from .parsers import market_from_corp_cls, normalize_date

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
    warnings: list[str] = []
    raw_dir = Path(args.raw_dir)
    stock_codes = parse_stock_codes(args.stock_codes)

    disclosure_start = args.start or rolling_start_yyyymmdd(args.end, 89)
    if days_between(disclosure_start, args.end) > 92:
        capped_start = rolling_start_yyyymmdd(args.end, 89)
        warnings.append(
            f"OpenDART list.json without corp_code is limited to about 3 months; "
            f"disclosure discovery start capped from {disclosure_start} to {capped_start}."
        )
        disclosure_start = capped_start

    disclosures, disclosure_warnings = fetch_buyback_disclosures(
        api_key=api_key,
        bgn_de=disclosure_start,
        end_de=args.end,
        raw_dir=raw_dir,
        page_limit=args.discovery_page_limit,
    )
    print(
        f"discovered {len(disclosures)} buyback disclosure rows from {disclosure_start} to {args.end}",
        flush=True,
    )
    warnings.extend(disclosure_warnings)

    if stock_codes is not None:
        print("fetching OpenDART corp code master for seed stock codes...", flush=True)
        all_companies = fetch_corp_codes(api_key, raw_dir / "corp_codes.json")
        company_by_corp = {company.corp_code: company for company in all_companies}
        company_by_stock = {company.stock_code: company for company in all_companies}
        for item in disclosures:
            company = company_by_corp.get(str(item.get("corp_code") or ""))
            if company:
                market = market_from_corp_cls(item.get("corp_cls"))
                if market != "OTHER":
                    company.market = market
        candidate_corps = {str(item.get("corp_code") or "") for item in disclosures}
        candidate_companies = [company_by_corp[corp_code] for corp_code in candidate_corps if corp_code in company_by_corp]
        candidate_companies.extend(company_by_stock[code] for code in stock_codes if code in company_by_stock)
    else:
        candidate_companies = companies_from_disclosures(disclosures)

    companies = dedupe_companies(candidate_companies)
    if args.max_companies and len(companies) > args.max_companies:
        warnings.append(f"Candidate company list truncated from {len(companies)} to {args.max_companies}.")
        companies = companies[: args.max_companies]

    if not companies:
        warnings.append("No listed buyback candidates found in OpenDART disclosure search; fixture data kept.")
        return copy_fixture_dataset(fixture_dir, output_dir)

    years = [int(part) for part in args.years.split(",") if part]
    print(
        f"collecting structured OpenDART rows for {len(companies)} companies, "
        f"years={','.join(str(year) for year in years)}, report_codes={args.report_codes}",
        flush=True,
    )
    live_companies, events, holdings, collection_warnings = collect_dart_dataset(
        api_key=api_key,
        companies=companies,
        bgn_de=disclosure_start,
        end_de=args.end,
        years=years,
        raw_dir=raw_dir,
        disclosure_items=disclosures,
        report_codes=parse_report_codes(args.report_codes),
    )
    warnings.extend(collection_warnings)
    if not events and not holdings:
        warnings.append("OpenDART returned no live buyback rows for candidate companies; fixture data kept.")
        return copy_fixture_dataset(fixture_dir, output_dir)

    price_reactions = [missing_reaction(event.event_id, event.stock_code, event.disclosure_date) for event in events]
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
            f"OpenDART disclosure discovery window: {disclosure_start} to {args.end}.",
            "KRX treasury execution details remain fixture/adapter data until official API IDs are confirmed.",
        ],
    }
    write_json(output_dir / "companies.json", to_jsonable(live_companies))
    write_json(output_dir / "events.json", to_jsonable(events))
    write_json(output_dir / "holding_snapshots.json", to_jsonable(holdings))
    write_json(output_dir / "price_reactions.json", to_jsonable(price_reactions))
    write_json(output_dir / "data_status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/data/buybacks")
    parser.add_argument("--fixture-dir", default="data/fixtures/buybacks")
    parser.add_argument("--raw-dir", default="data/raw/buybacks")
    parser.add_argument("--live-if-available", action="store_true")
    parser.add_argument(
        "--stock-codes",
        default="005930,000660,035420,051910,005380,035900",
        help="Comma-separated seed stock codes. Use ALL to include only disclosure-discovered companies.",
    )
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--years", default=default_report_years())
    parser.add_argument("--report-codes", default="11011")
    parser.add_argument("--max-companies", type=int, default=12)
    parser.add_argument("--discovery-page-limit", type=int, default=3)
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


def parse_stock_codes(value: str) -> set[str] | None:
    if value.strip().upper() == "ALL":
        return None
    return {part.strip() for part in value.split(",") if part.strip()}


def companies_from_disclosures(disclosures: list[dict]) -> list[Company]:
    companies: list[Company] = []
    for item in disclosures:
        stock_code = str(item.get("stock_code") or "").strip()
        corp_code = str(item.get("corp_code") or "").strip()
        if len(stock_code) != 6 or not corp_code:
            continue
        companies.append(
            Company(
                corp_code=corp_code,
                stock_code=stock_code,
                corp_name=str(item.get("corp_name") or "").strip(),
                market=market_from_corp_cls(item.get("corp_cls")),
                sector=None,
                last_updated=normalize_date(item.get("rcept_dt")) or str(item.get("rcept_dt") or ""),
            )
        )
    return dedupe_companies(companies)


def dedupe_companies(companies: list[Company]) -> list[Company]:
    seen: set[str] = set()
    output: list[Company] = []
    for company in sorted(companies, key=lambda item: (item.market, item.corp_name, item.stock_code)):
        if company.stock_code in seen:
            continue
        seen.add(company.stock_code)
        output.append(company)
    return output


def default_report_years() -> str:
    now = datetime.now()
    return str(now.year - 1)


def parse_report_codes(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def rolling_start_yyyymmdd(end_yyyymmdd: str, days: int) -> str:
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    return (end - timedelta(days=days)).strftime("%Y%m%d")


def days_between(start_yyyymmdd: str, end_yyyymmdd: str) -> int:
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    return (end - start).days


if __name__ == "__main__":
    main()
