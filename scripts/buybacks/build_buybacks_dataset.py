from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.fetch_corp_codes import fetch_corp_codes
    from scripts.buybacks.fetch_dart_buybacks import (
        collect_dart_dataset,
        collect_dart_holding_snapshots,
        dedupe_events,
        dedupe_holdings,
        fetch_buyback_disclosures,
    )
    from scripts.buybacks.fetch_krx_prices import (
        calculate_kis_proxy_latest_prices,
        calculate_kis_proxy_price_reactions,
        missing_reaction,
    )
    from scripts.buybacks.fetch_listed_issues import ListedIssue, fetch_naver_listed_issues
    from scripts.buybacks.models import (
        BuybackEvent,
        Company,
        LatestPriceSnapshot,
        PriceReaction,
        TreasuryHoldingSnapshot,
        to_jsonable,
    )
    from scripts.buybacks.parsers import kst_today, market_from_corp_cls, normalize_date
else:
    from .fetch_corp_codes import fetch_corp_codes
    from .fetch_dart_buybacks import (
        collect_dart_dataset,
        collect_dart_holding_snapshots,
        dedupe_events,
        dedupe_holdings,
        fetch_buyback_disclosures,
    )
    from .fetch_krx_prices import (
        calculate_kis_proxy_latest_prices,
        calculate_kis_proxy_price_reactions,
        missing_reaction,
    )
    from .fetch_listed_issues import ListedIssue, fetch_naver_listed_issues
    from .models import BuybackEvent, Company, LatestPriceSnapshot, PriceReaction, TreasuryHoldingSnapshot, to_jsonable
    from .parsers import kst_today, market_from_corp_cls, normalize_date

LOGGER = logging.getLogger(__name__)

DATA_FILES = [
    "companies.json",
    "events.json",
    "holding_snapshots.json",
    "price_reactions.json",
    "latest_prices.json",
]
CORE_DATA_FILES = [
    "companies.json",
    "events.json",
    "holding_snapshots.json",
    "price_reactions.json",
]
SUPPORTED_MARKETS = {"KOSPI", "KOSDAQ"}
STOCK_CODE_PATTERN = re.compile(r"^[0-9A-Z]{6}$")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_fixture_dataset(fixture_dir: Path, output_dir: Path, extra_warnings: list[str] | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    companies, events, holdings, reactions = filter_json_dataset_to_supported_markets(
        load_json(fixture_dir / "companies.json"),
        load_json(fixture_dir / "events.json"),
        load_json(fixture_dir / "holding_snapshots.json"),
        load_json(fixture_dir / "price_reactions.json"),
    )
    latest_prices = load_fixture_latest_prices(fixture_dir, reactions)
    latest_prices = filter_latest_prices_to_companies(latest_prices, companies)
    write_json(output_dir / "companies.json", companies)
    write_json(output_dir / "events.json", events)
    write_json(output_dir / "holding_snapshots.json", holdings)
    write_json(output_dir / "price_reactions.json", reactions)
    write_json(output_dir / "latest_prices.json", latest_prices)
    status = load_json(fixture_dir / "data_status.json")
    # generated_at is intentionally UTC; business dates elsewhere use KST (Asia/Seoul).
    status["generated_at"] = datetime.now(timezone.utc).isoformat()
    # Keep the frontend-compatible "warnings": string[] shape and carry over any
    # warnings collected before falling back to fixture data.
    status["warnings"] = [*status.get("warnings", []), *(extra_warnings or [])]
    status["dart_available"] = False
    status["krx_available"] = False
    status["price_source"] = "fixture"
    status["companies_count"] = len(companies)
    status["events_count"] = len(events)
    status["holdings_count"] = len(holdings)
    status["price_reactions_count"] = len(reactions)
    status["latest_prices_count"] = len(latest_prices)
    write_json(output_dir / "data_status.json", status)
    return status


def build_live_dataset(args: argparse.Namespace, api_key: str, output_dir: Path) -> dict:
    fixture_dir = Path(args.fixture_dir)
    warnings: list[str] = []
    raw_dir = Path(args.raw_dir)
    stock_codes = parse_stock_codes(args.stock_codes)
    holding_stock_codes = parse_holding_stock_codes(args.holding_stock_codes)
    listed_issues = fetch_listed_issues_for_build(args, raw_dir, warnings)

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
    LOGGER.info(
        "discovered %d buyback disclosure rows from %s to %s",
        len(disclosures),
        disclosure_start,
        args.end,
    )
    warnings.extend(disclosure_warnings)

    all_companies: list[Company] | None = None
    company_by_corp: dict[str, Company] = {}
    company_by_stock: dict[str, Company] = {}
    needs_corp_master = stock_codes is not None or holding_stock_codes != "EVENTS"
    if needs_corp_master:
        LOGGER.info("fetching OpenDART corp code master...")
        all_companies = fetch_corp_codes(api_key, raw_dir / "corp_codes.json")
        company_by_corp = {company.corp_code: company for company in all_companies}
        company_by_stock = {company.stock_code: company for company in all_companies}
        for item in disclosures:
            company = company_by_corp.get(str(item.get("corp_code") or ""))
            if company:
                market = market_from_corp_cls(item.get("corp_cls"))
                if market != "OTHER":
                    company.market = market

    if stock_codes is not None:
        candidate_corps = {str(item.get("corp_code") or "") for item in disclosures}
        candidate_companies = [company_by_corp[corp_code] for corp_code in candidate_corps if corp_code in company_by_corp]
        candidate_companies.extend(company_by_stock[code] for code in stock_codes if code in company_by_stock)
    else:
        candidate_companies = companies_from_disclosures(disclosures)

    event_companies = dedupe_companies(candidate_companies, sort_by_name=stock_codes is not None)
    if args.max_companies and len(event_companies) > args.max_companies:
        warnings.append(f"Candidate company list truncated from {len(event_companies)} to {args.max_companies}.")
        event_companies = event_companies[: args.max_companies]

    if not event_companies:
        warnings.append("No listed buyback candidates found in OpenDART disclosure search; event table may be empty.")

    years = [int(part) for part in args.years.split(",") if part]
    report_codes = parse_report_codes(args.report_codes)
    LOGGER.info(
        "collecting structured OpenDART rows for %d event companies, years=%s, report_codes=%s",
        len(event_companies),
        ",".join(str(year) for year in years),
        args.report_codes,
    )
    live_event_companies, events, _, collection_warnings = collect_dart_dataset(
        api_key=api_key,
        companies=event_companies,
        bgn_de=disclosure_start,
        end_de=args.end,
        years=years,
        raw_dir=raw_dir,
        disclosure_items=disclosures,
        report_codes=report_codes,
        include_holdings=False,
    )
    warnings.extend(collection_warnings)

    holding_companies = select_holding_companies(
        holding_stock_codes,
        all_companies,
        live_event_companies,
        company_by_stock,
    )
    if args.max_holding_companies and len(holding_companies) > args.max_holding_companies:
        warnings.append(
            f"Holding company list truncated from {len(holding_companies)} to {args.max_holding_companies}."
        )
        holding_companies = holding_companies[: args.max_holding_companies]

    LOGGER.info(
        "collecting OpenDART holding snapshots for %d companies, years=%s, report_codes=%s",
        len(holding_companies),
        ",".join(str(year) for year in years),
        args.report_codes,
    )
    holdings, holding_warnings = collect_dart_holding_snapshots(
        api_key=api_key,
        companies=holding_companies,
        years=years,
        raw_dir=raw_dir,
        report_codes=report_codes,
        include_treasury_tables=args.holding_source == "treasury_tables",
    )
    warnings.extend(holding_warnings)

    live_companies = dedupe_companies([*holding_companies, *live_event_companies], sort_by_name=True)
    if not events and not holdings:
        warnings.append("OpenDART returned no live buyback rows for candidate companies; fixture data kept.")
        # Pass accumulated warnings along so they still reach data_status.json.
        return copy_fixture_dataset(fixture_dir, output_dir, extra_warnings=warnings)

    live_companies, events, holdings = filter_live_dataset_to_supported_markets(
        live_companies,
        events,
        holdings,
        listed_issues,
    )
    warnings.append(
        "Output universe restricted to currently trading KOSPI/KOSDAQ listed stock issues with event or holding rows."
    )

    price_reactions, price_warnings, price_source = build_price_reactions(args, events, live_companies)
    warnings.extend(price_warnings)
    latest_prices, latest_price_warnings, latest_price_source = build_latest_prices(
        args,
        [company.stock_code for company in live_companies],
    )
    warnings.extend(latest_price_warnings)
    status = {
        # generated_at is intentionally UTC; business dates elsewhere use KST (Asia/Seoul).
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dart_available": True,
        "krx_available": False,
        "price_source": price_source,
        "latest_price_source": latest_price_source,
        "companies_count": len(live_companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(price_reactions),
        "latest_prices_count": len(latest_prices),
        "warnings": [
            *warnings,
            f"OpenDART disclosure discovery window: {disclosure_start} to {args.end}.",
            f"OpenDART holding scan scope: {len(holding_companies)} companies.",
            f"OpenDART holding scan source: {args.holding_source}.",
            f"Listed issue master source: {args.listed_issue_source}.",
            "Price reactions use kis_proxy when configured; otherwise they remain missing.",
            "Latest prices use kis_proxy when configured; otherwise market caps remain missing.",
        ],
    }
    write_json(output_dir / "companies.json", to_jsonable(live_companies))
    write_json(output_dir / "events.json", to_jsonable(events))
    write_json(output_dir / "holding_snapshots.json", to_jsonable(holdings))
    write_json(output_dir / "price_reactions.json", to_jsonable(price_reactions))
    write_json(output_dir / "latest_prices.json", to_jsonable(latest_prices))
    write_json(output_dir / "data_status.json", status)
    return status


def build_incremental_dataset(args: argparse.Namespace, api_key: str, output_dir: Path) -> dict:
    if not existing_dataset_available(output_dir):
        LOGGER.info("existing dataset is missing; running a full live build before incremental updates")
        return build_live_dataset(args, api_key, output_dir)

    existing_companies = load_companies(output_dir / "companies.json")
    existing_events = load_events(output_dir / "events.json")
    existing_holdings = load_holdings(output_dir / "holding_snapshots.json")
    existing_reactions = load_reactions(output_dir / "price_reactions.json")
    existing_latest_prices = load_latest_prices(output_dir / "latest_prices.json")
    existing_status = load_json(output_dir / "data_status.json")
    raw_dir = Path(args.raw_dir)
    warnings: list[str] = []
    listed_issues = fetch_listed_issues_for_build(args, raw_dir, warnings)

    disclosure_start = args.start or incremental_start_yyyymmdd(
        existing_events,
        args.end,
        args.incremental_lookback_days,
    )
    if days_between(disclosure_start, args.end) > 92:
        capped_start = rolling_start_yyyymmdd(args.end, 89)
        warnings.append(
            f"OpenDART list.json without corp_code is limited to about 3 months; "
            f"incremental start capped from {disclosure_start} to {capped_start}."
        )
        disclosure_start = capped_start

    disclosures, disclosure_warnings = fetch_buyback_disclosures(
        api_key=api_key,
        bgn_de=disclosure_start,
        end_de=args.end,
        raw_dir=raw_dir,
        page_limit=args.discovery_page_limit,
    )
    LOGGER.info(
        "discovered %d incremental buyback disclosure rows from %s to %s",
        len(disclosures),
        disclosure_start,
        args.end,
    )
    warnings.extend(disclosure_warnings)

    event_companies = companies_from_disclosures(disclosures)
    years = [int(part) for part in args.years.split(",") if part]
    report_codes = parse_report_codes(args.report_codes)
    holding_stock_codes = parse_holding_stock_codes(args.holding_stock_codes)
    live_event_companies: list[Company] = []
    new_events: list[BuybackEvent] = []
    refreshed_holdings: list[TreasuryHoldingSnapshot] = []

    if event_companies:
        LOGGER.info(
            "collecting incremental structured OpenDART rows for %d event companies",
            len(event_companies),
        )
        live_event_companies, new_events, _, collection_warnings = collect_dart_dataset(
            api_key=api_key,
            companies=event_companies,
            bgn_de=disclosure_start,
            end_de=args.end,
            years=years,
            raw_dir=raw_dir,
            disclosure_items=disclosures,
            report_codes=report_codes,
            include_holdings=False,
        )
        warnings.extend(collection_warnings)

    holding_companies = select_incremental_holding_companies(
        args,
        api_key,
        holding_stock_codes,
        live_event_companies,
        raw_dir,
        warnings,
    )
    if holding_companies:
        LOGGER.info(
            "refreshing holding snapshots for %d companies (holding scope: %s)",
            len(holding_companies),
            args.holding_stock_codes,
        )
        refreshed_holdings, holding_warnings = collect_dart_holding_snapshots(
            api_key=api_key,
            companies=holding_companies,
            years=years,
            raw_dir=raw_dir,
            report_codes=report_codes,
            include_treasury_tables=args.holding_source == "treasury_tables",
        )
        warnings.extend(holding_warnings)

    # Scanned holding companies join the merge (lowest precedence) so all-market
    # scans can introduce holding-only companies; events stay incrementally merged.
    combined_companies = merge_companies(
        merge_companies(holding_companies, existing_companies),
        live_event_companies or event_companies,
    )
    combined_events = merge_events(existing_events, new_events)
    combined_holdings = merge_holdings(existing_holdings, refreshed_holdings)
    live_companies, events, holdings = filter_live_dataset_to_supported_markets(
        combined_companies,
        combined_events,
        combined_holdings,
        listed_issues,
    )

    new_event_ids = {event.event_id for event in new_events}
    price_refresh_events = select_price_reaction_events(
        events,
        existing_reactions,
        new_event_ids,
        args.incremental_price_lookback_days,
        args.end,
    )
    refreshed_reactions: list[PriceReaction] = []
    price_source = str(existing_status.get("price_source") or "missing")
    if price_refresh_events:
        LOGGER.info("refreshing price reactions for %d incremental/recent events", len(price_refresh_events))
        refreshed_reactions, price_warnings, price_source = build_price_reactions(
            args,
            price_refresh_events,
            live_companies,
        )
        warnings.extend(price_warnings)
    price_reactions = merge_price_reactions(existing_reactions, refreshed_reactions, events)
    latest_price_stock_codes = select_latest_price_stock_codes(
        events,
        existing_latest_prices,
        price_refresh_events,
    )
    refreshed_latest_prices, latest_price_warnings, latest_price_source = build_latest_prices(
        args,
        latest_price_stock_codes,
    )
    warnings.extend(latest_price_warnings)
    latest_prices = merge_latest_prices(existing_latest_prices, refreshed_latest_prices, live_companies)

    status = {
        # generated_at is intentionally UTC; business dates elsewhere use KST (Asia/Seoul).
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dart_available": True,
        "krx_available": False,
        "price_source": price_source,
        "latest_price_source": latest_price_source
        if refreshed_latest_prices or not existing_latest_prices
        else existing_status.get("latest_price_source", "missing"),
        "update_mode": "incremental",
        "previous_generated_at": existing_status.get("generated_at"),
        "companies_count": len(live_companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(price_reactions),
        "latest_prices_count": len(latest_prices),
        "warnings": [
            "Incremental update merged with the committed dataset instead of rebuilding the full universe.",
            incremental_holding_scope_note(holding_stock_codes, args.holding_stock_codes),
            *warnings,
            f"OpenDART incremental disclosure window: {disclosure_start} to {args.end}.",
            f"OpenDART incremental event company scope: {len(event_companies)} companies.",
            f"OpenDART incremental holding scan scope: {len(holding_companies)} companies.",
            f"OpenDART holding scan source: {args.holding_source}.",
            f"Listed issue master source: {args.listed_issue_source}.",
            "Price reactions use kis_proxy when configured; otherwise they remain missing.",
            "Latest prices use kis_proxy when configured; otherwise market caps remain missing.",
        ],
    }
    write_json(output_dir / "companies.json", to_jsonable(live_companies))
    write_json(output_dir / "events.json", to_jsonable(events))
    write_json(output_dir / "holding_snapshots.json", to_jsonable(holdings))
    write_json(output_dir / "price_reactions.json", to_jsonable(price_reactions))
    write_json(output_dir / "latest_prices.json", to_jsonable(latest_prices))
    write_json(output_dir / "data_status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/data/buybacks")
    parser.add_argument("--fixture-dir", default="data/fixtures/buybacks")
    parser.add_argument("--raw-dir", default="data/raw/buybacks")
    parser.add_argument("--live-if-available", action="store_true")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Merge recent live rows into the existing output dataset instead of rebuilding the full universe.",
    )
    parser.add_argument(
        "--stock-codes",
        default="005930,000660,035420,051910,005380,035900",
        help="Comma-separated seed stock codes for event enrichment. Use ALL for disclosure-discovered event companies.",
    )
    parser.add_argument(
        "--holding-stock-codes",
        default="ALL",
        help="Holding scan scope: ALL, EVENTS, or comma-separated stock codes.",
    )
    parser.add_argument(
        "--holding-source",
        choices=["stock_totals", "treasury_tables"],
        default="stock_totals",
        help="stock_totals stores total and treasury share counts with fewer DART requests.",
    )
    parser.add_argument("--start", default="")
    # Disclosure windows follow Korean market dates, so the default end is KST today.
    parser.add_argument("--end", default=kst_today().strftime("%Y%m%d"))
    parser.add_argument("--years", default=default_report_years())
    parser.add_argument("--report-codes", default="11011")
    parser.add_argument("--max-companies", type=int, default=12)
    parser.add_argument("--max-holding-companies", type=int, default=0)
    parser.add_argument("--discovery-page-limit", type=int, default=50)
    parser.add_argument(
        "--incremental-lookback-days",
        type=int,
        default=7,
        help="Overlap window before the latest existing disclosure date when --incremental is used.",
    )
    parser.add_argument(
        "--incremental-price-lookback-days",
        type=int,
        default=75,
        help="Recent event window for refreshing incomplete kis_proxy price reactions.",
    )
    parser.add_argument(
        "--price-source",
        choices=["auto", "kis_proxy", "missing"],
        default="auto",
        help="Price reaction source. auto uses KIS_PROXY_URL when present, otherwise missing.",
    )
    parser.add_argument(
        "--latest-price-lookback-days",
        type=int,
        default=10,
        help="Recent calendar days to request from kis_proxy when collecting latest closes for market caps.",
    )
    parser.add_argument(
        "--listed-issue-source",
        choices=["naver", "none"],
        default="naver",
        help="Current listed issue master used to keep tradable KOSPI/KOSDAQ stock issues.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity for pipeline progress output (stdout).",
    )
    args = parser.parse_args()
    configure_logging(args.log_level)

    output_dir = Path(args.output)
    api_key = os.environ.get("DART_API_KEY")
    if args.incremental and not api_key:
        raise SystemExit("DART_API_KEY is required for --incremental updates")
    if args.live_if_available and api_key:
        if args.incremental:
            status = build_incremental_dataset(args, api_key, output_dir)
        else:
            status = build_live_dataset(args, api_key, output_dir)
    else:
        status = copy_fixture_dataset(Path(args.fixture_dir), output_dir)
    LOGGER.info(
        "generated buybacks dataset: %d companies, %d events, %d holdings",
        status["companies_count"],
        status["events_count"],
        status["holdings_count"],
    )


def configure_logging(level_name: str = "INFO") -> None:
    """Route pipeline progress output through logging on stdout.

    The message format stays bare so GitHub Actions logs keep the exact
    human-readable lines that print() used to emit.
    """
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(message)s",
    )


def parse_stock_codes(value: str) -> set[str] | None:
    if value.strip().upper() == "ALL":
        return None
    return {part.strip().upper() for part in value.split(",") if part.strip()}


def parse_holding_stock_codes(value: str) -> set[str] | None | str:
    normalized = value.strip().upper()
    if normalized == "ALL":
        return None
    if normalized == "EVENTS":
        return "EVENTS"
    return {part.strip().upper() for part in value.split(",") if part.strip()}


def select_holding_companies(
    holding_stock_codes: set[str] | None | str,
    all_companies: list[Company] | None,
    event_companies: list[Company],
    company_by_stock: dict[str, Company],
) -> list[Company]:
    if holding_stock_codes == "EVENTS":
        return dedupe_companies_by_corp(event_companies)
    if holding_stock_codes is None:
        return dedupe_companies_by_corp(all_companies or event_companies)
    return dedupe_companies_by_corp(
        [company_by_stock[code] for code in holding_stock_codes if code in company_by_stock]
    )


def select_incremental_holding_companies(
    args: argparse.Namespace,
    api_key: str,
    holding_stock_codes: set[str] | None | str,
    live_event_companies: list[Company],
    raw_dir: Path,
    warnings: list[str],
) -> list[Company]:
    """Resolve the incremental holding-scan scope from --holding-stock-codes.

    EVENTS keeps the historical incremental behavior (only companies with fresh
    event disclosures). ALL or explicit stock codes fetch the corp code master
    so full-universe holding refreshes can run without abandoning the
    incremental (merge-based) event path.
    """
    if holding_stock_codes == "EVENTS":
        holding_companies = select_holding_companies("EVENTS", None, live_event_companies, {})
    else:
        LOGGER.info("fetching OpenDART corp code master for the incremental holding scan...")
        all_companies = fetch_corp_codes(api_key, raw_dir / "corp_codes.json")
        company_by_stock = {company.stock_code: company for company in all_companies}
        holding_companies = select_holding_companies(
            holding_stock_codes,
            all_companies,
            live_event_companies,
            company_by_stock,
        )
    if args.max_holding_companies and len(holding_companies) > args.max_holding_companies:
        warnings.append(
            f"Holding company list truncated from {len(holding_companies)} to {args.max_holding_companies}."
        )
        holding_companies = holding_companies[: args.max_holding_companies]
    return holding_companies


def incremental_holding_scope_note(holding_stock_codes: set[str] | None | str, raw_value: str) -> str:
    if holding_stock_codes == "EVENTS":
        return (
            "Holding snapshots are refreshed only for companies with incremental event disclosures; "
            "existing all-market snapshots are preserved."
        )
    return (
        f"Holding snapshots are refreshed for the {raw_value.strip().upper()} holding scope and merged "
        "with existing snapshots; events remain incrementally merged."
    )


def companies_from_disclosures(disclosures: list[dict]) -> list[Company]:
    companies: list[Company] = []
    for item in disclosures:
        stock_code = str(item.get("stock_code") or "").strip()
        corp_code = str(item.get("corp_code") or "").strip()
        if not STOCK_CODE_PATTERN.fullmatch(stock_code.upper()) or not corp_code:
            continue
        stock_code = stock_code.upper()
        market = market_from_corp_cls(item.get("corp_cls"))
        if market not in SUPPORTED_MARKETS:
            continue
        companies.append(
            Company(
                corp_code=corp_code,
                stock_code=stock_code,
                corp_name=str(item.get("corp_name") or "").strip(),
                market=market,
                sector=None,
                last_updated=normalize_date(item.get("rcept_dt")) or str(item.get("rcept_dt") or ""),
            )
        )
    return dedupe_companies(companies, sort_by_name=False)


def build_price_reactions(
    args: argparse.Namespace,
    events: list[BuybackEvent],
    companies: list[Company],
) -> tuple[list[PriceReaction], list[str], str]:
    if args.price_source == "missing":
        return missing_price_reactions(events), [], "missing"

    kis_proxy_url = os.environ.get("KIS_PROXY_URL", "").strip()
    if kis_proxy_url:
        LOGGER.info("collecting price reactions from kis_proxy...")
        reactions, warnings = calculate_kis_proxy_price_reactions(
            events,
            companies,
            base_url=kis_proxy_url,
            token=os.environ.get("KIS_PROXY_TOKEN", "").strip(),
        )
        return reactions, warnings, "kis_proxy"

    warnings = ["KIS_PROXY_URL is not set; price reactions marked missing."]
    if args.price_source == "kis_proxy":
        warnings.append("Requested --price-source kis_proxy but no proxy URL was configured.")
    return missing_price_reactions(events), warnings, "missing"


def build_latest_prices(
    args: argparse.Namespace,
    stock_codes: list[str] | set[str],
) -> tuple[list[LatestPriceSnapshot], list[str], str]:
    codes = sorted({code for code in stock_codes if code})
    if not codes:
        return [], [], "missing"
    if args.price_source == "missing":
        return [], [], "missing"

    kis_proxy_url = os.environ.get("KIS_PROXY_URL", "").strip()
    if kis_proxy_url:
        LOGGER.info("collecting latest prices from kis_proxy for %d stocks...", len(codes))
        snapshots, warnings = calculate_kis_proxy_latest_prices(
            codes,
            base_url=kis_proxy_url,
            token=os.environ.get("KIS_PROXY_TOKEN", "").strip(),
            lookback_days=args.latest_price_lookback_days,
        )
        return snapshots, warnings, "kis_proxy"

    warnings = ["KIS_PROXY_URL is not set; latest prices marked missing."]
    if args.price_source == "kis_proxy":
        warnings.append("Requested --price-source kis_proxy but no proxy URL was configured.")
    return [], warnings, "missing"


def missing_price_reactions(events: list[BuybackEvent]) -> list[PriceReaction]:
    return [missing_reaction(event.event_id, event.stock_code, event.disclosure_date) for event in events]


def existing_dataset_available(output_dir: Path) -> bool:
    return all((output_dir / name).exists() for name in [*CORE_DATA_FILES, "data_status.json"])


def load_companies(path: Path) -> list[Company]:
    return [Company(**item) for item in load_json(path)]


def load_events(path: Path) -> list[BuybackEvent]:
    return [BuybackEvent(**event_payload(item)) for item in load_json(path)]


def load_holdings(path: Path) -> list[TreasuryHoldingSnapshot]:
    return [TreasuryHoldingSnapshot(**item) for item in load_json(path)]


def load_reactions(path: Path) -> list[PriceReaction]:
    return [PriceReaction(**reaction_payload(item)) for item in load_json(path)]


def load_latest_prices(path: Path) -> list[LatestPriceSnapshot]:
    if not path.exists():
        return []
    return [LatestPriceSnapshot(**item) for item in load_json(path)]


def event_payload(item: dict) -> dict:
    payload = dict(item)
    payload.setdefault("planned_amount_common_krw", None)
    payload.setdefault("planned_amount_other_krw", None)
    payload.setdefault("planned_share_ratio_common", None)
    payload.setdefault("planned_share_ratio_other", None)
    return payload


def reaction_payload(item: dict) -> dict:
    payload = dict(item)
    payload.setdefault("market_return_5d", None)
    payload.setdefault("abnormal_return_5d", None)
    payload.setdefault("market_return_60d", None)
    payload.setdefault("abnormal_return_60d", None)
    return payload


def merge_companies(existing: list[Company], incoming: list[Company]) -> list[Company]:
    by_stock: dict[str, Company] = {}
    for company in [*existing, *incoming]:
        by_stock[company.stock_code] = company
    return dedupe_companies(list(by_stock.values()), sort_by_name=True)


def merge_events(existing: list[BuybackEvent], incoming: list[BuybackEvent]) -> list[BuybackEvent]:
    return dedupe_events([*existing, *incoming])


def merge_holdings(
    existing: list[TreasuryHoldingSnapshot],
    incoming: list[TreasuryHoldingSnapshot],
) -> list[TreasuryHoldingSnapshot]:
    # Incoming (freshly scanned) snapshots go first: dedupe_holdings keeps the
    # first record among identical dedupe keys (stock, date, year, report, kind),
    # so a refresh can correct values on rows that already exist.
    return dedupe_holdings([*incoming, *existing])


def merge_price_reactions(
    existing: list[PriceReaction],
    refreshed: list[PriceReaction],
    events: list[BuybackEvent],
) -> list[PriceReaction]:
    event_ids = {event.event_id for event in events}
    by_event = {reaction.event_id: reaction for reaction in existing if reaction.event_id in event_ids}
    for reaction in refreshed:
        if reaction.event_id in event_ids:
            by_event[reaction.event_id] = reaction
    for event in events:
        if event.event_id not in by_event:
            by_event[event.event_id] = missing_reaction(event.event_id, event.stock_code, event.disclosure_date)
    return [
        by_event[event.event_id]
        for event in sorted(events, key=lambda item: (item.disclosure_date, item.event_id), reverse=True)
    ]


def select_latest_price_stock_codes(
    events: list[BuybackEvent],
    existing_prices: list[LatestPriceSnapshot],
    price_refresh_events: list[BuybackEvent],
) -> set[str]:
    event_stock_codes = {event.stock_code for event in events}
    return event_stock_codes


def merge_latest_prices(
    existing: list[LatestPriceSnapshot],
    refreshed: list[LatestPriceSnapshot],
    companies: list[Company],
) -> list[LatestPriceSnapshot]:
    supported_stock_codes = {company.stock_code for company in companies}
    by_stock: dict[str, LatestPriceSnapshot] = {}
    for snapshot in [*existing, *refreshed]:
        if snapshot.stock_code not in supported_stock_codes:
            continue
        previous = by_stock.get(snapshot.stock_code)
        if previous is None or snapshot.price_date >= previous.price_date:
            by_stock[snapshot.stock_code] = snapshot
    return [by_stock[stock_code] for stock_code in sorted(by_stock)]


def select_price_reaction_events(
    events: list[BuybackEvent],
    existing_reactions: list[PriceReaction],
    new_event_ids: set[str],
    lookback_days: int,
    end_yyyymmdd: str,
) -> list[BuybackEvent]:
    existing_by_event = {reaction.event_id: reaction for reaction in existing_reactions}
    cutoff = datetime.strptime(end_yyyymmdd, "%Y%m%d").date() - timedelta(days=lookback_days)
    selected: list[BuybackEvent] = []
    for event in events:
        reaction = existing_by_event.get(event.event_id)
        disclosure_date = datetime.strptime(event.disclosure_date, "%Y-%m-%d").date()
        if event.event_id in new_event_ids or reaction is None:
            selected.append(event)
        elif disclosure_date >= cutoff and (
            reaction.data_quality != "complete" or has_missing_relative_window(reaction)
        ):
            selected.append(event)
    return selected


def has_missing_relative_window(reaction: PriceReaction) -> bool:
    return (
        reaction.abnormal_return_5d is None
        or reaction.abnormal_return_20d is None
        or reaction.abnormal_return_60d is None
    )


def incremental_start_yyyymmdd(events: list[BuybackEvent], end_yyyymmdd: str, lookback_days: int) -> str:
    if not events:
        return rolling_start_yyyymmdd(end_yyyymmdd, min(lookback_days, 89))
    latest = max(datetime.strptime(event.disclosure_date, "%Y-%m-%d").date() for event in events)
    return (latest - timedelta(days=lookback_days)).strftime("%Y%m%d")


def fetch_listed_issues_for_build(
    args: argparse.Namespace,
    raw_dir: Path,
    warnings: list[str],
) -> list[ListedIssue]:
    if args.listed_issue_source == "none":
        warnings.append("Listed issue master disabled; falling back to OpenDART market classification.")
        return []
    LOGGER.info("fetching current KOSPI/KOSDAQ listed issue master...")
    issues = fetch_naver_listed_issues(output=raw_dir / "listed_issues_naver.json")
    tradable = [issue for issue in issues if issue.is_trading and issue.market in SUPPORTED_MARKETS]
    LOGGER.info("fetched %d currently trading listed issues", len(tradable))
    return tradable


def filter_live_dataset_to_supported_markets(
    companies: list[Company],
    events: list[BuybackEvent],
    holdings: list[TreasuryHoldingSnapshot],
    listed_issues: list[ListedIssue] | None = None,
) -> tuple[list[Company], list[BuybackEvent], list[TreasuryHoldingSnapshot]]:
    if listed_issues:
        return filter_live_dataset_to_listed_issues(companies, events, holdings, listed_issues)

    supported_stocks = {
        company.stock_code
        for company in companies
        if company.market in SUPPORTED_MARKETS
    }
    filtered_events = [event for event in events if event.stock_code in supported_stocks]
    filtered_holdings = [holding for holding in holdings if holding.stock_code in supported_stocks]
    data_stocks = {event.stock_code for event in filtered_events} | {
        holding.stock_code for holding in filtered_holdings
    }
    filtered_companies = [
        company
        for company in companies
        if company.market in SUPPORTED_MARKETS and company.stock_code in data_stocks
    ]
    return filtered_companies, filtered_events, filtered_holdings


def filter_live_dataset_to_listed_issues(
    companies: list[Company],
    events: list[BuybackEvent],
    holdings: list[TreasuryHoldingSnapshot],
    listed_issues: list[ListedIssue],
) -> tuple[list[Company], list[BuybackEvent], list[TreasuryHoldingSnapshot]]:
    issue_by_code = {
        issue.stock_code: issue
        for issue in listed_issues
        if issue.is_trading and issue.market in SUPPORTED_MARKETS
    }
    issues = list(issue_by_code.values())
    company_by_stock = {company.stock_code: company for company in companies}
    company_by_corp: dict[str, Company] = {}
    for company in companies:
        company_by_corp.setdefault(company.corp_code, company)

    filtered_events = [event for event in events if event.stock_code in issue_by_code]
    derived_companies: dict[str, Company] = {}
    filtered_holdings: list[TreasuryHoldingSnapshot] = []

    for holding in holdings:
        source_company = company_by_stock.get(holding.stock_code) or company_by_corp.get(holding.corp_code)
        primary_company = company_by_corp.get(holding.corp_code)
        issue = issue_by_code.get(holding.stock_code) if is_already_mapped_issue(holding, primary_company, issue_by_code) else None
        if issue is None:
            issue = resolve_holding_issue(holding, source_company, issue_by_code, issues)
        if issue is None:
            continue
        filtered_holdings.append(
            replace(
                holding,
                stock_code=issue.stock_code,
                corp_name=issue.issue_name,
            )
        )
        if issue.stock_code not in company_by_stock:
            derived_companies[issue.stock_code] = Company(
                corp_code=holding.corp_code,
                stock_code=issue.stock_code,
                corp_name=issue.issue_name,
                market=issue.market,
                sector=source_company.sector if source_company else None,
                last_updated=holding.as_of_date,
            )

    data_stocks = {event.stock_code for event in filtered_events} | {
        holding.stock_code for holding in filtered_holdings
    }
    filtered_companies: list[Company] = []
    seen: set[str] = set()
    for company in companies:
        issue = issue_by_code.get(company.stock_code)
        if issue is None or company.stock_code not in data_stocks or company.stock_code in seen:
            continue
        filtered_companies.append(
            replace(company, market=issue.market, corp_name=issue.issue_name or company.corp_name)
        )
        seen.add(company.stock_code)
    for stock_code, company in sorted(derived_companies.items(), key=lambda item: item[1].corp_name):
        if stock_code in data_stocks and stock_code not in seen:
            filtered_companies.append(company)
            seen.add(stock_code)

    return filtered_companies, filtered_events, filtered_holdings


def is_already_mapped_issue(
    holding: TreasuryHoldingSnapshot,
    primary_company: Company | None,
    issue_by_code: dict[str, ListedIssue],
) -> bool:
    if holding.stock_code not in issue_by_code:
        return False
    if primary_company is None:
        return not is_common_holding_kind(holding.stock_kind)
    return holding.stock_code != primary_company.stock_code


def resolve_holding_issue(
    holding: TreasuryHoldingSnapshot,
    company: Company | None,
    issue_by_code: dict[str, ListedIssue],
    issues: list[ListedIssue],
) -> ListedIssue | None:
    base_issue = issue_by_code.get(holding.stock_code)
    if is_common_holding_kind(holding.stock_kind):
        return base_issue
    if not is_preferred_or_nonvoting_holding_kind(holding.stock_kind):
        return None
    if base_issue is not None and (company is None or holding.stock_code != company.stock_code):
        return base_issue

    company_name = normalized_issue_name((company.corp_name if company else "") or holding.corp_name)
    if not company_name:
        return None
    candidates = [
        issue
        for issue in issues
        if issue.stock_code != holding.stock_code
        and is_preferred_issue_for_company(issue.issue_name, company_name)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    scored = sorted(
        ((preferred_issue_match_score(holding.stock_kind, issue.issue_name), issue) for issue in candidates),
        key=lambda item: (item[0], item[1].issue_name),
        reverse=True,
    )
    if scored[0][0] <= 0 or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


def is_common_holding_kind(stock_kind: str) -> bool:
    normalized = normalized_issue_name(stock_kind)
    return "보통" in normalized or "common" in normalized


def is_preferred_or_nonvoting_holding_kind(stock_kind: str) -> bool:
    normalized = normalized_issue_name(stock_kind)
    return any(keyword in normalized for keyword in ["우선", "preferred", "의결권"])


def is_preferred_issue_for_company(issue_name: str, normalized_company_name: str) -> bool:
    normalized = normalized_issue_name(issue_name)
    if not normalized.startswith(normalized_company_name):
        return False
    suffix = normalized.removeprefix(normalized_company_name)
    return suffix.startswith("우") or bool(re.match(r"^\d+우", suffix))


def preferred_issue_match_score(stock_kind: str, issue_name: str) -> int:
    kind = normalized_issue_name(stock_kind)
    issue = normalized_issue_name(issue_name)
    score = 0
    for marker in ["1", "2", "3", "4", "5"]:
        if marker in kind and f"{marker}우" in issue:
            score += 5
    if "전환" in kind and "전환" in issue:
        score += 2
    if "b" in kind and "b" in issue:
        score += 1
    if "우선" in kind and "우" in issue:
        score += 1
    if "의결권" in kind and "우" in issue:
        score += 1
    return score


def normalized_issue_name(value: object) -> str:
    return str(value or "").strip().replace(" ", "").lower()


def filter_json_dataset_to_supported_markets(
    companies: list[dict],
    events: list[dict],
    holdings: list[dict],
    reactions: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    supported_stocks = {
        str(company.get("stock_code") or "")
        for company in companies
        if company.get("market") in SUPPORTED_MARKETS
    }
    filtered_events = [
        event for event in events if str(event.get("stock_code") or "") in supported_stocks
    ]
    filtered_holdings = [
        holding for holding in holdings if str(holding.get("stock_code") or "") in supported_stocks
    ]
    event_ids = {event.get("event_id") for event in filtered_events}
    filtered_reactions = [reaction for reaction in reactions if reaction.get("event_id") in event_ids]
    data_stocks = {str(event.get("stock_code") or "") for event in filtered_events} | {
        str(holding.get("stock_code") or "") for holding in filtered_holdings
    }
    filtered_companies = [
        company
        for company in companies
        if company.get("market") in SUPPORTED_MARKETS
        and str(company.get("stock_code") or "") in data_stocks
    ]
    return filtered_companies, filtered_events, filtered_holdings, filtered_reactions


def load_fixture_latest_prices(fixture_dir: Path, reactions: list[dict]) -> list[dict]:
    latest_path = fixture_dir / "latest_prices.json"
    if latest_path.exists():
        return load_json(latest_path)
    return latest_prices_from_reactions(reactions)


def latest_prices_from_reactions(reactions: list[dict]) -> list[dict]:
    by_stock: dict[str, dict] = {}
    for reaction in reactions:
        stock_code = str(reaction.get("stock_code") or "")
        close = reaction.get("close_t0")
        price_date = reaction.get("event_date")
        if not stock_code or close is None or not price_date:
            continue
        previous = by_stock.get(stock_code)
        if previous is None or str(price_date) >= str(previous.get("price_date") or ""):
            by_stock[stock_code] = {
                "stock_code": stock_code,
                "price_date": price_date,
                "close": close,
                "source": "fixture",
            }
    return [by_stock[stock_code] for stock_code in sorted(by_stock)]


def filter_latest_prices_to_companies(latest_prices: list[dict], companies: list[dict]) -> list[dict]:
    company_stock_codes = {str(company.get("stock_code") or "") for company in companies}
    return [
        price
        for price in latest_prices
        if str(price.get("stock_code") or "") in company_stock_codes
    ]


def dedupe_companies(companies: list[Company], sort_by_name: bool = True) -> list[Company]:
    seen: set[str] = set()
    output: list[Company] = []
    source = (
        sorted(companies, key=lambda item: (item.market, item.corp_name, item.stock_code))
        if sort_by_name
        else companies
    )
    for company in source:
        if company.stock_code in seen:
            continue
        seen.add(company.stock_code)
        output.append(company)
    return output


def dedupe_companies_by_corp(companies: list[Company]) -> list[Company]:
    seen: set[str] = set()
    output: list[Company] = []
    for company in companies:
        if company.corp_code in seen:
            continue
        seen.add(company.corp_code)
        output.append(company)
    return output


def default_report_years() -> str:
    # Report years follow the Korean disclosure calendar.
    return str(kst_today().year - 1)


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
