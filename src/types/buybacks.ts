export const MARKETS = ["KOSPI", "KOSDAQ", "KONEX", "OTHER"] as const;
export const EVENT_TYPES = [
  "direct_acquisition",
  "direct_disposition",
  "trust_contract_start",
  "trust_contract_end",
  "retirement",
  "periodic_holding_update",
  "unknown"
] as const;
export const DATA_QUALITIES = ["complete", "partial", "missing"] as const;
export const SOURCES = ["DART", "KRX", "MANUAL", "DERIVED"] as const;

export type Market = (typeof MARKETS)[number];
export type EventType = (typeof EVENT_TYPES)[number];
export type DataQuality = (typeof DATA_QUALITIES)[number];
export type Source = (typeof SOURCES)[number];

export interface Company {
  corp_code: string;
  stock_code: string;
  corp_name: string;
  market: Market;
  sector: string | null;
  last_updated: string;
}

export interface BuybackEvent {
  event_id: string;
  corp_code: string;
  stock_code: string;
  corp_name: string;
  event_type: EventType;
  disclosure_date: string;
  decision_date: string | null;
  period_start: string | null;
  period_end: string | null;
  planned_shares_common: number | null;
  planned_shares_other: number | null;
  planned_amount_krw: number | null;
  planned_amount_common_krw?: number | null;
  planned_amount_other_krw?: number | null;
  actual_shares: number | null;
  actual_amount_krw: number | null;
  method: string | null;
  purpose: string | null;
  broker: string | null;
  holding_before_common: number | null;
  holding_before_ratio_common: number | null;
  source: Source;
  rcept_no: string | null;
  source_url: string | null;
  raw_report_name: string | null;
}

export interface TreasuryHoldingSnapshot {
  corp_code: string;
  stock_code: string;
  corp_name: string;
  as_of_date: string;
  report_year: number;
  report_code: string;
  stock_kind: string;
  beginning_qty: number | null;
  acquired_qty: number | null;
  disposed_qty: number | null;
  retired_qty: number | null;
  ending_qty: number | null;
  issued_shares: number | null;
  treasury_ratio: number | null;
  floating_shares: number | null;
  source_rcept_no: string | null;
}

export interface PriceReaction {
  event_id: string;
  stock_code: string;
  event_date: string;
  close_t0: number | null;
  return_1d: number | null;
  return_5d: number | null;
  return_20d: number | null;
  return_60d: number | null;
  max_drawdown_20d: number | null;
  max_drawdown_60d: number | null;
  market_return_5d?: number | null;
  abnormal_return_5d?: number | null;
  market_return_20d: number | null;
  abnormal_return_20d: number | null;
  market_return_60d?: number | null;
  abnormal_return_60d?: number | null;
  volume_change_20d: number | null;
  data_quality: DataQuality;
}

export interface LatestPriceSnapshot {
  stock_code: string;
  price_date: string;
  close: number;
  source: string;
  change_rate?: number | null;
  issued_shares?: number | null;
  market_cap_krw?: number | null;
  change_code?: string | null;
}

export interface DataStatus {
  generated_at: string;
  dart_available: boolean;
  krx_available: boolean;
  price_source?: string;
  latest_price_source?: string;
  companies_count: number;
  events_count: number;
  holdings_count: number;
  price_reactions_count: number;
  latest_prices_count?: number;
  warnings: string[];
}

export interface BuybacksDataset {
  companies: Company[];
  events: BuybackEvent[];
  holdingSnapshots: TreasuryHoldingSnapshot[];
  priceReactions: PriceReaction[];
  latestPrices: LatestPriceSnapshot[];
  status: DataStatus;
}

export interface Filters {
  market: Market | "ALL";
  eventTypes: EventType[];
  year: string;
  search: string;
}

export interface EnrichedEvent extends BuybackEvent {
  company?: Company;
  holding?: TreasuryHoldingSnapshot;
  priceReaction?: PriceReaction;
  latestPrice?: LatestPriceSnapshot;
}
