"""Cumulative abnormal return (CAR) curve aggregation.

car_curves.json is a pure derivative of reaction_series.json + events.json:
it is re-aggregated from scratch on every build and must never be merged with
a previously stored aggregate. All inputs are plain JSON-shaped dicts so the
same code path serves live builds, incremental merges, and fixture builds.
"""

from __future__ import annotations

# t+1..t+60 trading days, matching REACTION_SERIES_WINDOW.
CAR_WINDOW = 60
# Groups with fewer contributing events are dropped from the output.
CAR_MIN_EVENTS = 5
# Stored mean CAR values are rounded like the stored series values.
CAR_DECIMALS = 6
MARKET_GROUPS = ("ALL", "KOSPI", "KOSDAQ")


def aggregate_car_curves(
    series: list[dict],
    events: list[dict],
    companies: list[dict],
    window: int = CAR_WINDOW,
    min_events: int = CAR_MIN_EVENTS,
) -> dict:
    """Aggregate mean CAR curves per event_type x {ALL, KOSPI, KOSDAQ}.

    Per event, CAR_k is the cumulative sum of daily_abnormal up to t+k+1; the
    group mean at k averages only the events whose series still has data at k
    (shorter series drop out of deeper k buckets). A group's n counts events
    contributing at least one abnormal data point.
    """
    market_by_stock = {
        str(company.get("stock_code") or ""): company.get("market") for company in companies
    }
    event_by_id = {event.get("event_id"): event for event in events}
    cars_by_group: dict[tuple[str, str], list[list[float]]] = {}
    for record in series:
        event = event_by_id.get(record.get("event_id"))
        if event is None:
            continue
        car = cumulative_abnormal(record.get("daily_abnormal") or [])
        if not car:
            continue
        event_type = str(event.get("event_type") or "unknown")
        keys = [(event_type, "ALL")]
        market = market_by_stock.get(str(record.get("stock_code") or ""))
        if market in ("KOSPI", "KOSDAQ"):
            keys.append((event_type, market))
        for key in keys:
            cars_by_group.setdefault(key, []).append(car)

    groups: list[dict] = []
    ordered_keys = sorted(cars_by_group, key=lambda key: (key[0], MARKET_GROUPS.index(key[1])))
    for event_type, market in ordered_keys:
        cars = cars_by_group[(event_type, market)]
        if len(cars) < min_events:
            continue
        mean_car: list[float | None] = []
        for k in range(window):
            values = [car[k] for car in cars if len(car) > k]
            mean_car.append(round(sum(values) / len(values), CAR_DECIMALS) if values else None)
        groups.append(
            {
                "event_type": event_type,
                "market": market,
                "n": len(cars),
                "mean_car": mean_car,
            }
        )
    return {"window": window, "min_events": min_events, "groups": groups}


def cumulative_abnormal(daily_abnormal: list) -> list[float]:
    """Cumulative sums of the abnormal series up to its first null entry.

    A null entry means the index return was unavailable that day, so deeper
    cumulative values would be undefined; the event simply stops contributing
    to the aggregate from that point on.
    """
    cumulative: list[float] = []
    total = 0.0
    for value in daily_abnormal:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            break
        total += float(value)
        cumulative.append(total)
    return cumulative
