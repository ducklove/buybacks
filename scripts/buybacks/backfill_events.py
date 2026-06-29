from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.build_buybacks_dataset import (
        filter_live_dataset_to_supported_markets,
        load_companies,
        load_events,
        load_json,
        load_latest_prices,
        load_reactions,
        merge_companies,
        merge_events,
        merge_latest_prices,
        merge_price_reactions,
        parse_report_codes,
        write_json,
        companies_from_disclosures as build_companies_from_disclosures,
    )
    from scripts.buybacks.fetch_dart_buybacks import collect_dart_dataset, dedupe_events, fetch_buyback_disclosures
    from scripts.buybacks.fetch_krx_prices import missing_reaction
    from scripts.buybacks.fetch_listed_issues import fetch_naver_listed_issues
    from scripts.buybacks.models import BuybackEvent, Company, PriceReaction, to_jsonable
else:
    from .build_buybacks_dataset import (
        filter_live_dataset_to_supported_markets,
        load_companies,
        load_events,
        load_json,
        load_latest_prices,
        load_reactions,
        merge_companies,
        merge_events,
        merge_latest_prices,
        merge_price_reactions,
        parse_report_codes,
        write_json,
        companies_from_disclosures as build_companies_from_disclosures,
    )
    from .fetch_dart_buybacks import collect_dart_dataset, dedupe_events, fetch_buyback_disclosures
    from .fetch_krx_prices import missing_reaction
    from .fetch_listed_issues import fetch_naver_listed_issues
    from .models import BuybackEvent, Company, PriceReaction, to_jsonable


BACKFILL_VERSION = 1
DATE_FORMAT = "%Y%m%d"


@dataclass(slots=True)
class DateChunk:
    start: str
    end: str


def collect_backfill(args: argparse.Namespace) -> dict[str, Any]:
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DART_API_KEY is required for event backfill collection")

    start_date = parse_date(args.start)
    end_date = parse_date(args.end)
    if start_date > end_date:
        raise SystemExit("--start must be earlier than or equal to --end")

    run_id = args.run_id or default_run_id(args.start, args.end)
    run_dir = Path(args.backfill_dir) / run_id
    raw_dir = Path(args.raw_dir) if args.raw_dir else run_dir / "raw"
    status_path = run_dir / "status.json"
    started = time.monotonic()
    warnings: list[str] = []
    chunks = date_chunks(args.start, args.end, args.chunk_days)
    all_companies: list[Company] = []
    all_events: list[BuybackEvent] = []
    all_disclosures: list[dict] = []

    write_status(
        status_path,
        run_status(
            args,
            run_id,
            state="running",
            progress_percent=0,
            total_chunks=len(chunks),
            completed_chunks=0,
            started_at=utc_now(),
        ),
    )

    try:
        listed_issues = fetch_naver_listed_issues(output=raw_dir / "listed_issues_naver.json")
        report_codes = parse_report_codes(args.report_codes)

        for index, chunk in enumerate(chunks, start=1):
            print(f"collecting backfill chunk {index}/{len(chunks)}: {chunk.start}..{chunk.end}", flush=True)
            disclosures, disclosure_warnings = fetch_buyback_disclosures(
                api_key=api_key,
                bgn_de=chunk.start,
                end_de=chunk.end,
                raw_dir=raw_dir,
                page_limit=args.page_limit,
            )
            warnings.extend(disclosure_warnings)
            all_disclosures.extend(disclosures)

            chunk_companies = companies_from_disclosures(disclosures)
            if chunk_companies:
                years = years_for_range(chunk.start, chunk.end)
                companies, events, _, collection_warnings = collect_dart_dataset(
                    api_key=api_key,
                    companies=chunk_companies,
                    bgn_de=chunk.start,
                    end_de=chunk.end,
                    years=years,
                    raw_dir=raw_dir,
                    disclosure_items=disclosures,
                    report_codes=report_codes,
                    include_holdings=False,
                )
                warnings.extend(collection_warnings)
                companies, events, _ = filter_live_dataset_to_supported_markets(
                    companies,
                    events,
                    [],
                    listed_issues,
                )
                all_companies.extend(companies)
                all_events.extend(events)

            progress = round(index / len(chunks) * 100, 2)
            print(f"backfill progress {progress:.2f}%", flush=True)
            write_status(
                status_path,
                run_status(
                    args,
                    run_id,
                    state="running",
                    progress_percent=progress,
                    total_chunks=len(chunks),
                    completed_chunks=index,
                    started_at=status_started_at(status_path),
                    warnings=warnings,
                    companies_count=len(dedupe_companies_for_run(all_companies)),
                    events_count=len(dedupe_events(all_events)),
                    updated_at=utc_now(),
                ),
            )

        companies = dedupe_companies_for_run(all_companies)
        events = dedupe_events(all_events)
        duplicate_count, new_count = compare_backfill_events(load_events(Path(args.data_dir) / "events.json"), events)
        duration_seconds = round(time.monotonic() - started, 2)
        status = run_status(
            args,
            run_id,
            state="succeeded",
            progress_percent=100,
            total_chunks=len(chunks),
            completed_chunks=len(chunks),
            started_at=status_started_at(status_path),
            finished_at=utc_now(),
            duration_seconds=duration_seconds,
            warnings=warnings,
            companies_count=len(companies),
            events_count=len(events),
            duplicate_events_count=duplicate_count,
            new_events_count=new_count,
        )
        write_json(run_dir / "companies.json", to_jsonable(companies))
        write_json(run_dir / "events.json", to_jsonable(events))
        write_json(run_dir / "disclosures.json", all_disclosures)
        write_status(status_path, status)
        print(
            f"backfill completed in {duration_seconds}s: "
            f"{len(events)} collected, {new_count} new, {duplicate_count} duplicate",
            flush=True,
        )
        return status
    except Exception as exc:  # noqa: BLE001 - status file must capture collector failure.
        status = run_status(
            args,
            run_id,
            state="failed",
            progress_percent=progress_from_status(status_path),
            total_chunks=len(chunks),
            completed_chunks=completed_chunks_from_status(status_path),
            started_at=status_started_at(status_path),
            finished_at=utc_now(),
            duration_seconds=round(time.monotonic() - started, 2),
            warnings=warnings,
            error=str(exc),
        )
        write_status(status_path, status)
        raise


def merge_backfill(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.backfill_dir) / args.run_id
    status_path = run_dir / "status.json"
    status = load_json(status_path)
    if status.get("state") != "succeeded":
        raise SystemExit(f"Backfill run {args.run_id} is not mergeable: state={status.get('state')}")

    data_dir = Path(args.data_dir)
    existing_companies = load_companies(data_dir / "companies.json")
    existing_events = load_events(data_dir / "events.json")
    existing_reactions = load_reactions(data_dir / "price_reactions.json")
    existing_latest_prices = load_latest_prices(data_dir / "latest_prices.json")
    existing_status = load_json(data_dir / "data_status.json")
    backfill_companies = [Company(**item) for item in load_json(run_dir / "companies.json")]
    backfill_events = [BuybackEvent(**event_payload(item)) for item in load_json(run_dir / "events.json")]

    duplicate_count, new_count = compare_backfill_events(existing_events, backfill_events)
    merged_companies = merge_companies(existing_companies, backfill_companies)
    merged_events = merge_events(existing_events, backfill_events)
    existing_event_keys = {event_key(existing) for existing in existing_events}
    missing_reactions: list[PriceReaction] = [
        missing_reaction(event.event_id, event.stock_code, event.disclosure_date)
        for event in backfill_events
        if event_key(event) not in existing_event_keys
    ]
    merged_reactions = merge_price_reactions(existing_reactions, missing_reactions, merged_events)
    merged_latest_prices = merge_latest_prices(existing_latest_prices, [], merged_companies)

    updated_status = {
        **existing_status,
        "generated_at": utc_now(),
        "update_mode": "backfill_merge",
        "previous_generated_at": existing_status.get("generated_at"),
        "companies_count": len(merged_companies),
        "events_count": len(merged_events),
        "holdings_count": int(existing_status.get("holdings_count") or 0),
        "price_reactions_count": len(merged_reactions),
        "latest_prices_count": len(merged_latest_prices),
        "last_backfill_run_id": args.run_id,
        "last_backfill_new_events_count": new_count,
        "last_backfill_duplicate_events_count": duplicate_count,
        "warnings": [
            *existing_status.get("warnings", []),
            f"Backfill run {args.run_id} merged {new_count} new events and skipped {duplicate_count} duplicates.",
            "Backfilled historical price reactions are initialized as missing until price enrichment is run.",
        ],
    }

    write_json(data_dir / "companies.json", to_jsonable(merged_companies))
    write_json(data_dir / "events.json", to_jsonable(merged_events))
    write_json(data_dir / "price_reactions.json", to_jsonable(merged_reactions))
    write_json(data_dir / "latest_prices.json", to_jsonable(merged_latest_prices))
    write_json(data_dir / "data_status.json", updated_status)
    merged_run_status = {
        **status,
        "merge_state": "merged",
        "merged_at": utc_now(),
        "merge_new_events_count": new_count,
        "merge_duplicate_events_count": duplicate_count,
    }
    write_status(status_path, merged_run_status)
    print(f"merged backfill {args.run_id}: {new_count} new, {duplicate_count} duplicate", flush=True)
    return merged_run_status


def run_status(
    args: argparse.Namespace,
    run_id: str,
    state: str,
    progress_percent: float,
    total_chunks: int,
    completed_chunks: int,
    started_at: str,
    updated_at: str | None = None,
    finished_at: str | None = None,
    duration_seconds: float | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
    companies_count: int = 0,
    events_count: int = 0,
    duplicate_events_count: int = 0,
    new_events_count: int = 0,
) -> dict[str, Any]:
    return {
        "version": BACKFILL_VERSION,
        "run_id": run_id,
        "state": state,
        "start": args.start,
        "end": args.end,
        "progress_percent": progress_percent,
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "started_at": started_at,
        "updated_at": updated_at or utc_now(),
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "companies_count": companies_count,
        "events_count": events_count,
        "duplicate_events_count": duplicate_events_count,
        "new_events_count": new_events_count,
        "warnings": warnings or [],
        "error": error,
    }


def date_chunks(start: str, end: str, chunk_days: int) -> list[DateChunk]:
    if chunk_days < 1 or chunk_days > 92:
        raise SystemExit("--chunk-days must be between 1 and 92")
    current = parse_date(start)
    final = parse_date(end)
    chunks: list[DateChunk] = []
    while current <= final:
        chunk_end = min(current + timedelta(days=chunk_days - 1), final)
        chunks.append(DateChunk(current.strftime(DATE_FORMAT), chunk_end.strftime(DATE_FORMAT)))
        current = chunk_end + timedelta(days=1)
    return chunks


def years_for_range(start: str, end: str) -> list[int]:
    start_year = parse_date(start).year
    end_year = parse_date(end).year
    return list(range(start_year, end_year + 1))


def compare_backfill_events(
    existing_events: list[BuybackEvent],
    backfill_events: list[BuybackEvent],
) -> tuple[int, int]:
    existing_keys = {event_key(event) for event in existing_events}
    duplicate_count = sum(1 for event in backfill_events if event_key(event) in existing_keys)
    return duplicate_count, len(backfill_events) - duplicate_count


def event_key(event: BuybackEvent) -> str:
    return event.rcept_no or event.event_id


def dedupe_companies_for_run(companies: list[Company]) -> list[Company]:
    by_stock: dict[str, Company] = {}
    for company in companies:
        by_stock[company.stock_code] = company
    return sorted(by_stock.values(), key=lambda item: (item.corp_name, item.stock_code))


def companies_from_disclosures(disclosures: list[dict]) -> list[Company]:
    return build_companies_from_disclosures(disclosures)


def event_payload(item: dict) -> dict:
    payload = dict(item)
    payload.setdefault("planned_amount_common_krw", None)
    payload.setdefault("planned_amount_other_krw", None)
    payload.setdefault("planned_share_ratio_common", None)
    payload.setdefault("planned_share_ratio_other", None)
    return payload


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, DATE_FORMAT)


def default_run_id(start: str, end: str) -> str:
    return f"{start}-{end}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(path: Path, status: dict[str, Any]) -> None:
    write_json(path, status)


def status_started_at(path: Path) -> str:
    if not path.exists():
        return utc_now()
    return str(load_json(path).get("started_at") or utc_now())


def progress_from_status(path: Path) -> float:
    if not path.exists():
        return 0
    return float(load_json(path).get("progress_percent") or 0)


def completed_chunks_from_status(path: Path) -> int:
    if not path.exists():
        return 0
    return int(load_json(path).get("completed_chunks") or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and merge historical buyback event backfills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--start", required=True, help="Backfill start date in YYYYMMDD.")
    collect_parser.add_argument("--end", required=True, help="Backfill end date in YYYYMMDD.")
    collect_parser.add_argument("--run-id", default="")
    collect_parser.add_argument("--backfill-dir", default="data/backfills")
    collect_parser.add_argument("--data-dir", default="public/data/buybacks")
    collect_parser.add_argument("--raw-dir", default="")
    collect_parser.add_argument("--chunk-days", type=int, default=14)
    collect_parser.add_argument("--page-limit", type=int, default=50)
    collect_parser.add_argument("--report-codes", default="11011")
    collect_parser.set_defaults(func=collect_backfill)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--run-id", required=True)
    merge_parser.add_argument("--backfill-dir", default="data/backfills")
    merge_parser.add_argument("--data-dir", default="public/data/buybacks")
    merge_parser.set_defaults(func=merge_backfill)

    args = parser.parse_args()
    status = args.func(args)
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
