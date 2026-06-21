from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Market = Literal["KOSPI", "KOSDAQ", "KONEX", "OTHER"]
EventType = Literal[
    "direct_acquisition",
    "direct_disposition",
    "trust_contract_start",
    "trust_contract_end",
    "retirement",
    "periodic_holding_update",
    "unknown",
]
Source = Literal["DART", "KRX", "MANUAL", "DERIVED"]
DataQuality = Literal["complete", "partial", "missing"]


@dataclass(slots=True)
class Company:
    corp_code: str
    stock_code: str
    corp_name: str
    market: Market
    sector: str | None
    last_updated: str


@dataclass(slots=True)
class BuybackEvent:
    event_id: str
    corp_code: str
    stock_code: str
    corp_name: str
    event_type: EventType
    disclosure_date: str
    decision_date: str | None
    period_start: str | None
    period_end: str | None
    planned_shares_common: int | float | None
    planned_shares_other: int | float | None
    planned_amount_krw: int | float | None
    planned_amount_common_krw: int | float | None
    planned_amount_other_krw: int | float | None
    actual_shares: int | float | None
    actual_amount_krw: int | float | None
    method: str | None
    purpose: str | None
    broker: str | None
    holding_before_common: int | float | None
    holding_before_ratio_common: float | None
    source: Source
    rcept_no: str | None
    source_url: str | None
    raw_report_name: str | None


@dataclass(slots=True)
class TreasuryHoldingSnapshot:
    corp_code: str
    stock_code: str
    corp_name: str
    as_of_date: str
    report_year: int
    report_code: str
    stock_kind: str
    beginning_qty: int | None
    acquired_qty: int | None
    disposed_qty: int | None
    retired_qty: int | None
    ending_qty: int | None
    issued_shares: int | None
    treasury_ratio: float | None
    floating_shares: int | None
    source_rcept_no: str | None


@dataclass(slots=True)
class PriceReaction:
    event_id: str
    stock_code: str
    event_date: str
    close_t0: float | None
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    max_drawdown_20d: float | None
    max_drawdown_60d: float | None
    market_return_5d: float | None
    abnormal_return_5d: float | None
    market_return_20d: float | None
    abnormal_return_20d: float | None
    market_return_60d: float | None
    abnormal_return_60d: float | None
    volume_change_20d: float | None
    data_quality: DataQuality


@dataclass(slots=True)
class LatestPriceSnapshot:
    stock_code: str
    price_date: str
    close: float
    source: str
    change_rate: float | None = None
    issued_shares: int | float | None = None
    market_cap_krw: int | float | None = None
    change_code: str | None = None


def to_jsonable(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
