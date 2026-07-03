from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STOCK_CODE = re.compile(r"^[0-9A-Z]{6}$")
MARKETS = {"KOSPI", "KOSDAQ"}
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
EXECUTION_TYPES = {"acquisition_result", "disposition_result", "trust_status"}
EXECUTION_LINK_METHODS = {"report_date", "period_overlap", "unlinked"}
HOLDING_FLOW_FIELDS = ("beginning_qty", "acquired_qty", "disposed_qty", "retired_qty", "ending_qty")
# Completion above this level (actual vs planned or trust progress) is almost
# always a parsing/unit error or a plan revision; report it, never fail on it.
COMPLETION_RATE_WARNING_THRESHOLD = 1.2
MAX_PRINTED_WARNINGS = 50


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return load(path)


def validate_dataset(data_dir: Path) -> tuple[list[str], list[str]]:
    """Validate the built dataset.

    Returns (errors, warnings). Errors are structural problems that must fail
    CI. Warnings are data-quality findings (e.g. holding flow mismatches that
    exist in the DART source itself) and must not break the build.
    """
    errors: list[str] = []
    companies = load(data_dir / "companies.json")
    events = load(data_dir / "events.json")
    holdings = load(data_dir / "holding_snapshots.json")
    reactions = load(data_dir / "price_reactions.json")
    latest_prices = load_optional(data_dir / "latest_prices.json", [])
    # executions.json is optional: datasets built before execution tracking
    # (including the committed public data) must keep validating cleanly.
    executions = load_optional(data_dir / "executions.json", None)
    status = load(data_dir / "data_status.json")

    stocks = set()
    event_ids = set()
    for index, company in enumerate(companies):
        if company.get("market") not in MARKETS:
            errors.append(f"companies[{index}] invalid market")
        stock_code = company.get("stock_code")
        if not STOCK_CODE.fullmatch(str(stock_code or "")):
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

    for index, price in enumerate(latest_prices):
        if price.get("stock_code") not in stocks:
            errors.append(f"latest_prices[{index}] unknown stock_code")
        if not ISO_DATE.match(str(price.get("price_date", ""))):
            errors.append(f"latest_prices[{index}] invalid price_date")
        close = price.get("close")
        if not isinstance(close, (int, float)) or close <= 0:
            errors.append(f"latest_prices[{index}] invalid close")
        change_rate = price.get("change_rate")
        if change_rate is not None and not isinstance(change_rate, (int, float)):
            errors.append(f"latest_prices[{index}] invalid change_rate")

    if executions is not None:
        errors.extend(execution_errors(executions, event_ids))

    expected_counts = {
        "companies_count": len(companies),
        "events_count": len(events),
        "holdings_count": len(holdings),
        "price_reactions_count": len(reactions),
    }
    if "latest_prices_count" in status:
        expected_counts["latest_prices_count"] = len(latest_prices)
    if executions is not None and "executions_count" in status:
        expected_counts["executions_count"] = len(executions)
    for key, expected in expected_counts.items():
        if status.get(key) != expected:
            errors.append(f"data_status.{key}={status.get(key)} expected {expected}")

    warnings = holding_flow_warnings(holdings)
    if executions is not None:
        warnings.extend(execution_completion_warnings(executions, events))
    return errors, warnings


def execution_errors(executions: list[dict], event_ids: set) -> list[str]:
    """Structural checks for executions.json rows (only when the file exists)."""
    errors: list[str] = []
    execution_ids: set = set()
    for index, execution in enumerate(executions):
        execution_id = execution.get("execution_id")
        if execution_id in execution_ids:
            errors.append(f"executions[{index}] duplicate execution_id {execution_id}")
        execution_ids.add(execution_id)
        if execution.get("execution_type") not in EXECUTION_TYPES:
            errors.append(f"executions[{index}] invalid execution_type")
        if execution.get("link_method") not in EXECUTION_LINK_METHODS:
            errors.append(f"executions[{index}] invalid link_method")
        if execution.get("source") not in SOURCES:
            errors.append(f"executions[{index}] invalid source")
        if not ISO_DATE.match(str(execution.get("disclosure_date", ""))):
            errors.append(f"executions[{index}] invalid disclosure_date")
        if not str(execution.get("rcept_no") or ""):
            errors.append(f"executions[{index}] missing rcept_no")
        linked_event_id = execution.get("linked_event_id")
        if execution.get("link_method") == "unlinked":
            if linked_event_id is not None:
                errors.append(f"executions[{index}] unlinked row has linked_event_id")
        elif linked_event_id not in event_ids:
            errors.append(f"executions[{index}] unknown linked_event_id {linked_event_id}")
    return errors


def execution_completion_warnings(executions: list[dict], events: list[dict]) -> list[str]:
    """Report suspicious completion rates (> COMPLETION_RATE_WARNING_THRESHOLD).

    Rates are derived exactly like the frontend: actual vs the linked event's
    planned shares first, amount fallback, and trust progress for trust rows.
    Anomalies usually mean a unit-parsing bug or a revised plan; they are
    report-only and never fail validation.
    """
    warnings: list[str] = []
    event_by_id = {event.get("event_id"): event for event in events}
    for index, execution in enumerate(executions):
        rate = derived_completion_rate(execution, event_by_id.get(execution.get("linked_event_id")))
        if rate is not None and rate > COMPLETION_RATE_WARNING_THRESHOLD:
            warnings.append(
                f"executions[{index}] {execution.get('stock_code')} {execution.get('rcept_no')} "
                f"completion rate {rate:.2f} exceeds {COMPLETION_RATE_WARNING_THRESHOLD}"
            )
    return warnings


def derived_completion_rate(execution: dict, event: dict | None) -> float | None:
    if execution.get("execution_type") == "trust_status":
        ratio = execution.get("trust_progress_ratio")
        return float(ratio) if isinstance(ratio, (int, float)) and not isinstance(ratio, bool) else None
    actual_shares = execution.get("actual_shares")
    planned_shares = execution.get("planned_shares")
    if event is not None and event.get("planned_shares_common"):
        planned_shares = event.get("planned_shares_common")
    if is_positive_number(planned_shares) and is_positive_number(actual_shares):
        return float(actual_shares) / float(planned_shares)
    actual_amount = execution.get("actual_amount_krw")
    planned_amount = execution.get("planned_amount_krw")
    if event is not None and not is_positive_number(planned_amount):
        planned_amount = event.get("planned_amount_krw")
    if is_positive_number(planned_amount) and is_positive_number(actual_amount):
        return float(actual_amount) / float(planned_amount)
    return None


def is_positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def holding_flow_warnings(holdings: list[dict]) -> list[str]:
    """Report snapshots where beginning + acquired - disposed - retired != ending.

    Only snapshots with every flow field present and numeric are checked. The
    DART source data itself is occasionally inconsistent, so violations are
    reported as warnings and must never fail validation.
    """
    warnings: list[str] = []
    for index, snapshot in enumerate(holdings):
        values = [snapshot.get(field) for field in HOLDING_FLOW_FIELDS]
        if any(value is None or isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            continue
        beginning, acquired, disposed, retired, ending = values
        expected = beginning + acquired - disposed - retired
        if expected != ending:
            warnings.append(
                f"holding_snapshots[{index}] {snapshot.get('stock_code')} {snapshot.get('as_of_date')} "
                f"({snapshot.get('report_code')}, {snapshot.get('stock_kind') or 'unknown kind'}) flow mismatch: "
                f"beginning+acquired-disposed-retired={expected:,} but ending_qty={ending:,} "
                f"(diff {ending - expected:+,})"
            )
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path, nargs="?", default=Path("public/data/buybacks"))
    args = parser.parse_args()
    errors, warnings = validate_dataset(args.data_dir)
    if warnings:
        print(f"Dataset validation warnings ({len(warnings)}, non-blocking):")
        for warning in warnings[:MAX_PRINTED_WARNINGS]:
            print(f"- {warning}")
        if len(warnings) > MAX_PRINTED_WARNINGS:
            print(f"- ... and {len(warnings) - MAX_PRINTED_WARNINGS} more warnings")
    if errors:
        print("Dataset validation failed:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)
    print(f"Dataset validation passed for {args.data_dir} ({len(warnings)} warnings)")


if __name__ == "__main__":
    main()
