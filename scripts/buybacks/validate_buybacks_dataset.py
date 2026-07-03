from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
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
SERIES_QUALITIES = {"complete", "partial"}
CAR_MARKETS = {"ALL", "KOSPI", "KOSDAQ"}
HOLDING_FLOW_FIELDS = ("beginning_qty", "acquired_qty", "disposed_qty", "retired_qty", "ending_qty")
# Completion above this level (actual vs planned or trust progress) is almost
# always a parsing/unit error or a plan revision; report it, never fail on it.
COMPLETION_RATE_WARNING_THRESHOLD = 1.2
# reaction_series stores at most t+1..t+60 trading days per event.
REACTION_SERIES_MAX_LENGTH = 60
# A daily move beyond +-50% is usually a corporate action the adjusted price
# feed missed (or a feed bug); report it, never fail on it.
DAILY_RETURN_WARNING_THRESHOLD = 0.5
# Dividend business years must fall inside a sane disclosure range. The upper
# bound allows the year in progress plus one for timezone/new-year edges.
DIVIDEND_YEAR_MIN = 1990
# A payout ratio above 500% is almost always a unit or parsing error in the
# DART source row; report it, never fail on it.
DIVIDEND_PAYOUT_RATIO_WARNING_MAX = 5.0
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
    # reaction_series.json and car_curves.json are optional derived series
    # data: datasets built before series tracking must keep validating cleanly.
    reaction_series = load_optional(data_dir / "reaction_series.json", None)
    car_curves = load_optional(data_dir / "car_curves.json", None)
    # dividends.json is optional: datasets built before dividend tracking
    # (including the committed public data) must keep validating cleanly.
    dividends = load_optional(data_dir / "dividends.json", None)
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
    if reaction_series is not None:
        errors.extend(reaction_series_errors(reaction_series, event_ids))
    if car_curves is not None:
        errors.extend(car_curves_errors(car_curves))
    if dividends is not None:
        errors.extend(dividend_errors(dividends))

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
    if reaction_series is not None and "reaction_series_count" in status:
        expected_counts["reaction_series_count"] = len(reaction_series)
    if car_curves is not None and "car_groups_count" in status:
        expected_counts["car_groups_count"] = len(car_curves.get("groups") or [])
    if dividends is not None and "dividends_count" in status:
        expected_counts["dividends_count"] = len(dividends)
    for key, expected in expected_counts.items():
        if status.get(key) != expected:
            errors.append(f"data_status.{key}={status.get(key)} expected {expected}")

    warnings = holding_flow_warnings(holdings)
    if executions is not None:
        warnings.extend(execution_completion_warnings(executions, events))
    if reaction_series is not None:
        warnings.extend(reaction_series_return_warnings(reaction_series))
    if dividends is not None:
        warnings.extend(dividend_ratio_warnings(dividends))
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


def reaction_series_errors(series: list[dict], event_ids: set) -> list[str]:
    """Structural checks for reaction_series.json rows (only when the file exists)."""
    errors: list[str] = []
    seen: set = set()
    for index, record in enumerate(series):
        event_id = record.get("event_id")
        if event_id in seen:
            errors.append(f"reaction_series[{index}] duplicate event_id {event_id}")
        seen.add(event_id)
        if event_id not in event_ids:
            errors.append(f"reaction_series[{index}] unknown event_id {event_id}")
        if record.get("data_quality") not in SERIES_QUALITIES:
            errors.append(f"reaction_series[{index}] invalid data_quality")
        daily_return = record.get("daily_return")
        daily_abnormal = record.get("daily_abnormal")
        if not isinstance(daily_return, list) or not isinstance(daily_abnormal, list):
            errors.append(f"reaction_series[{index}] daily_return/daily_abnormal must be arrays")
            continue
        if len(daily_return) > REACTION_SERIES_MAX_LENGTH:
            errors.append(
                f"reaction_series[{index}] daily_return length {len(daily_return)} "
                f"exceeds {REACTION_SERIES_MAX_LENGTH}"
            )
        if len(daily_return) != len(daily_abnormal):
            errors.append(
                f"reaction_series[{index}] daily_return length {len(daily_return)} "
                f"!= daily_abnormal length {len(daily_abnormal)}"
            )
        # daily_return entries must be numbers; daily_abnormal entries may be
        # null where the index data was unavailable that day.
        if any(not is_finite_number(value) for value in daily_return):
            errors.append(f"reaction_series[{index}] daily_return has non-numeric entries")
        if any(value is not None and not is_finite_number(value) for value in daily_abnormal):
            errors.append(f"reaction_series[{index}] daily_abnormal has non-numeric entries")
    return errors


def reaction_series_return_warnings(series: list[dict]) -> list[str]:
    """Report daily moves beyond +-DAILY_RETURN_WARNING_THRESHOLD (warning only)."""
    warnings: list[str] = []
    for index, record in enumerate(series):
        values = [
            *(record.get("daily_return") if isinstance(record.get("daily_return"), list) else []),
            *(record.get("daily_abnormal") if isinstance(record.get("daily_abnormal"), list) else []),
        ]
        outliers = sum(
            1 for value in values if is_finite_number(value) and abs(value) > DAILY_RETURN_WARNING_THRESHOLD
        )
        if outliers:
            warnings.append(
                f"reaction_series[{index}] {record.get('stock_code')} {record.get('event_id')} has "
                f"{outliers} daily return value(s) beyond +-{DAILY_RETURN_WARNING_THRESHOLD}"
            )
    return warnings


def car_curves_errors(car_curves: dict) -> list[str]:
    """Structural checks for car_curves.json (only when the file exists)."""
    errors: list[str] = []
    window = car_curves.get("window")
    min_events = car_curves.get("min_events")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        errors.append("car_curves.window must be a positive integer")
    if not isinstance(min_events, int) or isinstance(min_events, bool) or min_events < 1:
        errors.append("car_curves.min_events must be a positive integer")
    groups = car_curves.get("groups")
    if not isinstance(groups, list):
        errors.append("car_curves.groups must be an array")
        return errors
    for index, group in enumerate(groups):
        if group.get("event_type") not in EVENT_TYPES:
            errors.append(f"car_curves.groups[{index}] invalid event_type")
        if group.get("market") not in CAR_MARKETS:
            errors.append(f"car_curves.groups[{index}] invalid market")
        n = group.get("n")
        if not isinstance(n, int) or isinstance(n, bool):
            errors.append(f"car_curves.groups[{index}] invalid n")
        elif isinstance(min_events, int) and not isinstance(min_events, bool) and n < min_events:
            errors.append(f"car_curves.groups[{index}] n={n} below min_events {min_events}")
        mean_car = group.get("mean_car")
        if not isinstance(mean_car, list) or (
            isinstance(window, int) and not isinstance(window, bool) and len(mean_car) != window
        ):
            errors.append(f"car_curves.groups[{index}] mean_car length must equal window")
    return errors


def dividend_errors(dividends: list[dict]) -> list[str]:
    """Structural checks for dividends.json rows (only when the file exists)."""
    errors: list[str] = []
    seen: set[tuple[str, object]] = set()
    max_year = date.today().year + 1
    for index, record in enumerate(dividends):
        corp_code = str(record.get("corp_code") or "")
        if not corp_code:
            errors.append(f"dividends[{index}] missing corp_code")
        if not STOCK_CODE.fullmatch(str(record.get("stock_code") or "")):
            errors.append(f"dividends[{index}] invalid stock_code")
        bsns_year = record.get("bsns_year")
        if not isinstance(bsns_year, int) or isinstance(bsns_year, bool):
            errors.append(f"dividends[{index}] bsns_year must be an integer")
        elif not DIVIDEND_YEAR_MIN <= bsns_year <= max_year:
            errors.append(
                f"dividends[{index}] bsns_year {bsns_year} outside {DIVIDEND_YEAR_MIN}..{max_year}"
            )
        key = (corp_code, bsns_year)
        if key in seen:
            errors.append(f"dividends[{index}] duplicate corp_code/bsns_year {corp_code}/{bsns_year}")
        seen.add(key)
        for field in ["dps_common_krw", "cash_dividend_total_krw", "payout_ratio", "net_income_krw"]:
            value = record.get(field)
            if value is not None and not is_finite_number(value):
                errors.append(f"dividends[{index}] {field} must be numeric or null")
    return errors


def dividend_ratio_warnings(dividends: list[dict]) -> list[str]:
    """Report payout ratios outside 0..DIVIDEND_PAYOUT_RATIO_WARNING_MAX (warning only).

    Negative payout ratios (loss years) and extreme values usually mean a unit
    or parsing problem in the DART source row; they never fail validation.
    """
    warnings: list[str] = []
    for index, record in enumerate(dividends):
        ratio = record.get("payout_ratio")
        if not is_finite_number(ratio):
            continue
        if ratio < 0 or ratio > DIVIDEND_PAYOUT_RATIO_WARNING_MAX:
            warnings.append(
                f"dividends[{index}] {record.get('stock_code')} {record.get('bsns_year')} "
                f"payout_ratio {ratio:.2f} outside 0..{DIVIDEND_PAYOUT_RATIO_WARNING_MAX}"
            )
    return warnings


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
