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
SeriesDataQuality = Literal["complete", "partial"]
ExecutionType = Literal[
    "acquisition_result",  # 자기주식취득결과보고서
    "disposition_result",  # 자기주식처분결과보고서
    "trust_status",  # 신탁계약에의한취득상황보고서
]
ExecutionLinkMethod = Literal["report_date", "period_overlap", "unlinked"]


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
    planned_share_ratio_common: float | None
    planned_share_ratio_other: float | None
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
class BuybackExecution:
    """One row per execution result report (자기주식 이행 결과/상황 공시).

    Result reports are independent disclosures with their own rcept_no, so they
    live in executions.json instead of mutating BuybackEvent rows. Linkage to
    the originating decision event is derived data and recomputed on every
    build (see link_executions).
    """

    execution_id: str  # f"dart-{rcept_no}-{execution_type}"
    corp_code: str
    stock_code: str
    corp_name: str
    execution_type: ExecutionType
    disclosure_date: str  # 결과보고서 접수일
    origin_report_date: str | None  # 본문 기재 "주요사항보고서 제출일" (연결 키)
    period_start: str | None  # 실제 취득/처분 기간 (신탁: 계약기간)
    period_end: str | None
    ordered_shares: int | None  # 주문수량 계
    actual_shares: int | None  # 취득/처분수량 계 (신탁: 누적)
    actual_amount_krw: int | float | None  # 취득/처분가액 총액 (신탁: 누적)
    avg_price_krw: int | float | None
    planned_amount_krw: int | float | None  # 일치여부 표의 예정금액(보고서 자체 기재)
    planned_shares: int | None  # 처분: 처분예정주식
    shortfall: bool | None  # "미달"/"불일치" -> True, "일치"/"-" -> False
    shortfall_reason: str | None
    holding_after_qty: int | None  # 취득/처분후 보유상황 계(A+B) 수량
    holding_after_ratio: float | None
    trust_contract_amount_krw: int | float | None  # 신탁 전용: 계약금액
    trust_progress_ratio: float | None  # 신탁 전용: 취득금액/계약금액
    as_of_date: str | None  # 보유상황/신탁 보고 기준일
    linked_event_id: str | None  # 연결된 BuybackEvent.event_id
    link_method: ExecutionLinkMethod
    source: Source
    rcept_no: str
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
class ReactionSeries:
    """Daily post-event return series for CAR curves and frontend backtests.

    daily_return[k] is the simple return between trading days t+k and t+k+1
    after t0 (the first trading day after the event date) — not cumulative
    versus the t0 close. daily_abnormal has the same length and subtracts the
    matching daily index return (same index selection as PriceReaction
    abnormal fields); entries are null when the index data is unavailable.
    Records are omitted entirely when no price data exists for the event.
    """

    event_id: str
    stock_code: str
    event_date: str
    t0_date: str
    daily_return: list[float]
    daily_abnormal: list[float | None]
    data_quality: SeriesDataQuality


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
