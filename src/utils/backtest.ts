import type { BuybackEvent, Company, EventType, Market, ReactionSeries } from "../types/buybacks";
import { formatSignedPercent } from "./format";

/** 백테스트 보유기간(거래일) 옵션 */
export const HOLDING_PERIODS = [5, 10, 20, 40, 60] as const;
export type HoldingPeriod = (typeof HOLDING_PERIODS)[number];

/** 수익률 기준: 단순수익률 또는 지수대비 초과수익률 */
export type ReturnBasis = "simple" | "abnormal";

/** 분포 히스토그램 버킷 수 */
export const DISTRIBUTION_BUCKET_COUNT = 10;

export interface BacktestItem {
  series: ReactionSeries;
  eventType: EventType | null;
  market: Market | null;
}

export interface BacktestOptions {
  /** 빈 배열이면 전체 유형 포함 */
  eventTypes: EventType[];
  market: Market | "ALL";
  /** "ALL" 또는 4자리 연도 (event_date 기준) */
  year: string;
  /** 보유 거래일 수 N */
  holdDays: number;
  basis: ReturnBasis;
}

export interface BacktestBucket {
  label: string;
  from: number;
  to: number;
  count: number;
}

export interface BacktestResult {
  n: number;
  mean: number | null;
  median: number | null;
  winRate: number | null;
  best: number | null;
  worst: number | null;
  distribution: BacktestBucket[];
}

/**
 * 단순수익률 기준 누적수익률: Π(1+daily_return[k]) − 1 (k=0..N-1).
 * 시계열이 N일보다 짧으면 해당 이벤트는 계산에서 제외(null)한다.
 */
export function cumulativeSimpleReturn(dailyReturns: number[], holdDays: number): number | null {
  if (holdDays <= 0 || dailyReturns.length < holdDays) return null;
  let compounded = 1;
  for (let index = 0; index < holdDays; index += 1) {
    const value = dailyReturns[index];
    if (typeof value !== "number" || Number.isNaN(value)) return null;
    compounded *= 1 + value;
  }
  return compounded - 1;
}

/**
 * 지수대비 초과수익률 기준 누적합 (CAR 정의와 일치).
 * 구간 내에 null 이 있으면 해당 이벤트는 그 N 에서 제외(null)한다.
 */
export function cumulativeAbnormalReturn(
  dailyAbnormal: Array<number | null>,
  holdDays: number
): number | null {
  if (holdDays <= 0 || dailyAbnormal.length < holdDays) return null;
  let total = 0;
  for (let index = 0; index < holdDays; index += 1) {
    const value = dailyAbnormal[index];
    if (typeof value !== "number" || Number.isNaN(value)) return null;
    total += value;
  }
  return total;
}

export function holdingReturn(
  series: ReactionSeries,
  holdDays: number,
  basis: ReturnBasis
): number | null {
  return basis === "simple"
    ? cumulativeSimpleReturn(series.daily_return, holdDays)
    : cumulativeAbnormalReturn(series.daily_abnormal, holdDays);
}

/** reaction_series 를 이벤트 유형(events)·시장(companies)과 조인해 백테스트 입력을 만든다. */
export function buildBacktestItems(
  reactionSeries: ReactionSeries[],
  events: BuybackEvent[],
  companies: Company[]
): BacktestItem[] {
  const eventById = new Map(events.map((event) => [event.event_id, event]));
  const marketByStock = new Map(companies.map((company) => [company.stock_code, company.market]));
  return reactionSeries.map((series) => ({
    series,
    eventType: eventById.get(series.event_id)?.event_type ?? null,
    market: marketByStock.get(series.stock_code) ?? null
  }));
}

/** event_date 기준 연도 목록 (내림차순) */
export function availableBacktestYears(reactionSeries: ReactionSeries[]): string[] {
  return Array.from(new Set(reactionSeries.map((series) => series.event_date.slice(0, 4))))
    .sort()
    .reverse();
}

export function runBacktest(items: BacktestItem[], options: BacktestOptions): BacktestResult {
  const returns: number[] = [];
  items.forEach((item) => {
    if (!matchesFilters(item, options)) return;
    const value = holdingReturn(item.series, options.holdDays, options.basis);
    if (value !== null) returns.push(value);
  });

  if (returns.length === 0) {
    return {
      n: 0,
      mean: null,
      median: null,
      winRate: null,
      best: null,
      worst: null,
      distribution: []
    };
  }

  const sorted = [...returns].sort((a, b) => a - b);
  const total = returns.reduce((sum, value) => sum + value, 0);
  const wins = returns.filter((value) => value > 0).length;

  return {
    n: returns.length,
    mean: total / returns.length,
    median: medianOfSorted(sorted),
    winRate: wins / returns.length,
    best: sorted[sorted.length - 1],
    worst: sorted[0],
    distribution: buildDistribution(sorted)
  };
}

function matchesFilters(item: BacktestItem, options: BacktestOptions): boolean {
  if (options.eventTypes.length > 0) {
    if (item.eventType === null || !options.eventTypes.includes(item.eventType)) return false;
  }
  if (options.market !== "ALL" && item.market !== options.market) return false;
  if (options.year !== "ALL" && !item.series.event_date.startsWith(options.year)) return false;
  return true;
}

function medianOfSorted(sorted: number[]): number {
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function buildDistribution(sorted: number[]): BacktestBucket[] {
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const span = max - min;
  const width =
    span === 0 ? Math.max(Math.abs(min) * 0.1, 0.001) : span / DISTRIBUTION_BUCKET_COUNT;

  const buckets: BacktestBucket[] = Array.from(
    { length: DISTRIBUTION_BUCKET_COUNT },
    (_, index) => {
      const from = min + width * index;
      const to = from + width;
      return {
        label: `${formatSignedPercent(from, 1)} ~ ${formatSignedPercent(to, 1)}`,
        from,
        to,
        count: 0
      };
    }
  );

  sorted.forEach((value) => {
    const index = span === 0 ? 0 : Math.floor((value - min) / width);
    buckets[Math.min(Math.max(index, 0), DISTRIBUTION_BUCKET_COUNT - 1)].count += 1;
  });

  return buckets;
}
