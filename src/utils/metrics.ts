import type {
  BuybacksDataset,
  EnrichedEvent,
  EventType,
  Filters,
  LatestPriceSnapshot,
  Market,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";
import { KPI_LOOKBACK_MONTHS } from "../constants";
import { holdingKindKey, holdingKindPriority, isCommonHoldingKind } from "./holdings";
import { relativeReturn, type ReturnWindow } from "./priceReactions";

export interface KpiMetric {
  label: string;
  value: string;
  detail: string;
  tone: "teal" | "amber" | "green" | "neutral";
}

export interface ChartDatum {
  label: string;
  value: number;
  secondary?: number;
}

export const DEFAULT_FILTERS: Filters = {
  market: "ALL",
  eventTypes: [],
  year: "ALL",
  search: ""
};

export function enrichEvents(dataset: BuybacksDataset): EnrichedEvent[] {
  const companyByStock = new Map(dataset.companies.map((company) => [company.stock_code, company]));
  const latestHoldingByStock = latestHoldingMap(dataset.holdingSnapshots);
  const reactionByEvent = new Map(
    dataset.priceReactions.map((reaction) => [reaction.event_id, reaction])
  );
  const latestPriceByStock = latestPriceMap(dataset.latestPrices);

  return dataset.events.map((event) => ({
    ...event,
    company: companyByStock.get(event.stock_code),
    holding: latestHoldingByStock.get(event.stock_code),
    priceReaction: reactionByEvent.get(event.event_id),
    latestPrice: latestPriceByStock.get(event.stock_code)
  }));
}

export function latestPriceMap(prices: LatestPriceSnapshot[]): Map<string, LatestPriceSnapshot> {
  const byStock = new Map<string, LatestPriceSnapshot>();
  prices.forEach((price) => {
    const previous = byStock.get(price.stock_code);
    if (!previous || price.price_date > previous.price_date) {
      byStock.set(price.stock_code, price);
    }
  });
  return byStock;
}

export function latestHoldingMap(
  snapshots: TreasuryHoldingSnapshot[]
): Map<string, TreasuryHoldingSnapshot> {
  const byStock = new Map<string, TreasuryHoldingSnapshot>();
  snapshots.forEach((snapshot) => {
    const previous = byStock.get(snapshot.stock_code);
    if (
      !previous ||
      previous.as_of_date < snapshot.as_of_date ||
      (previous.as_of_date === snapshot.as_of_date &&
        holdingKindPriority(snapshot) > holdingKindPriority(previous))
    ) {
      byStock.set(snapshot.stock_code, snapshot);
    }
  });
  return byStock;
}

export function latestHoldingSnapshots(
  snapshots: TreasuryHoldingSnapshot[]
): TreasuryHoldingSnapshot[] {
  const byStockKind = new Map<string, TreasuryHoldingSnapshot>();
  snapshots.forEach((snapshot) => {
    const key = `${snapshot.stock_code}:${holdingKindKey(snapshot)}`;
    const previous = byStockKind.get(key);
    if (!previous || isBetterHoldingSnapshot(snapshot, previous)) {
      byStockKind.set(key, snapshot);
    }
  });
  return Array.from(byStockKind.values());
}

export function dedupeHoldingTimeline(
  snapshots: TreasuryHoldingSnapshot[]
): TreasuryHoldingSnapshot[] {
  const byDateKind = new Map<string, TreasuryHoldingSnapshot>();
  snapshots.forEach((snapshot) => {
    const key = `${snapshot.stock_code}:${snapshot.as_of_date}:${holdingKindKey(snapshot)}`;
    const previous = byDateKind.get(key);
    if (!previous || holdingCompletenessScore(snapshot) > holdingCompletenessScore(previous)) {
      byDateKind.set(key, snapshot);
    }
  });
  return Array.from(byDateKind.values());
}

function isBetterHoldingSnapshot(
  candidate: TreasuryHoldingSnapshot,
  previous: TreasuryHoldingSnapshot
) {
  if (candidate.as_of_date !== previous.as_of_date) {
    return candidate.as_of_date > previous.as_of_date;
  }
  const candidateScore = holdingCompletenessScore(candidate);
  const previousScore = holdingCompletenessScore(previous);
  if (candidateScore !== previousScore) {
    return candidateScore > previousScore;
  }
  return candidate.report_code.localeCompare(previous.report_code) > 0;
}

function holdingCompletenessScore(snapshot: TreasuryHoldingSnapshot) {
  return [
    snapshot.treasury_ratio,
    snapshot.ending_qty,
    snapshot.issued_shares,
    snapshot.floating_shares
  ].filter((value) => value !== null).length;
}

export function filterEvents(events: EnrichedEvent[], filters: Filters): EnrichedEvent[] {
  const search = filters.search.trim().toLowerCase();
  return events.filter((event) => {
    const marketMatch = filters.market === "ALL" || event.company?.market === filters.market;
    const typeMatch =
      filters.eventTypes.length === 0 || filters.eventTypes.includes(event.event_type);
    const yearMatch = filters.year === "ALL" || event.disclosure_date.startsWith(filters.year);
    const searchMatch =
      search.length === 0 ||
      event.corp_name.toLowerCase().includes(search) ||
      event.stock_code.includes(search);
    return marketMatch && typeMatch && yearMatch && searchMatch;
  });
}

export function availableYears(events: EnrichedEvent[]): string[] {
  return Array.from(new Set(events.map((event) => event.disclosure_date.slice(0, 4))))
    .sort()
    .reverse();
}

export function buildKpis(
  events: EnrichedEvent[],
  holdings: TreasuryHoldingSnapshot[]
): KpiMetric[] {
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - KPI_LOOKBACK_MONTHS);
  const recent = events.filter((event) => new Date(event.disclosure_date) >= cutoff);
  const acquisitions = recent.filter((event) => acquisitionTypes.has(event.event_type)).length;
  const dispositions = recent.filter((event) => event.event_type === "direct_disposition").length;
  const retirements = recent.filter((event) => event.event_type === "retirement").length;
  const topHolding = [...holdings]
    .filter((holding) => holding.treasury_ratio !== null && isCommonHoldingKind(holding))
    .sort((a, b) => (b.treasury_ratio ?? 0) - (a.treasury_ratio ?? 0))[0];
  const averageAbnormalReturn20d = average(
    events
      .map((event) => event.priceReaction?.abnormal_return_20d ?? null)
      .filter((value): value is number => value !== null)
  );

  return [
    {
      label: `최근 ${KPI_LOOKBACK_MONTHS}개월 취득 결정`,
      value: `${acquisitions}건`,
      detail: "직접취득 및 신탁체결 포함",
      tone: "teal"
    },
    {
      label: `최근 ${KPI_LOOKBACK_MONTHS}개월 처분 결정`,
      value: `${dispositions}건`,
      detail: "직접처분 공시 기준",
      tone: "amber"
    },
    {
      label: `최근 ${KPI_LOOKBACK_MONTHS}개월 소각 이벤트`,
      value: `${retirements}건`,
      detail: "소각 또는 소각결정 기준",
      tone: "green"
    },
    {
      label: "최고 보유비율",
      value: topHolding ? `${((topHolding.treasury_ratio ?? 0) * 100).toFixed(2)}%` : "-",
      detail: topHolding ? holdingSummary(topHolding) : "데이터 없음",
      tone: "neutral"
    },
    {
      label: "평균 +20D 지수대비",
      value:
        averageAbnormalReturn20d === null
          ? "-"
          : `${averageAbnormalReturn20d > 0 ? "+" : ""}${(averageAbnormalReturn20d * 100).toFixed(2)}%`,
      detail: "시장지수 대비 초과수익률 평균",
      tone: "teal"
    }
  ];
}

export function monthlyEventCounts(events: EnrichedEvent[]): ChartDatum[] {
  const counts = new Map<string, number>();
  events.forEach((event) => {
    const month = event.disclosure_date.slice(0, 7);
    counts.set(month, (counts.get(month) ?? 0) + 1);
  });
  return Array.from(counts, ([label, value]) => ({ label, value })).sort((a, b) =>
    a.label.localeCompare(b.label)
  );
}

export function eventTypeCounts(events: EnrichedEvent[]): ChartDatum[] {
  const counts = new Map<EventType, number>();
  events.forEach((event) => {
    counts.set(event.event_type, (counts.get(event.event_type) ?? 0) + 1);
  });
  return Array.from(counts, ([label, value]) => ({ label, value }));
}

export function topHoldings(holdings: TreasuryHoldingSnapshot[], limit = 10): ChartDatum[] {
  return [...holdings]
    .filter((holding) => holding.treasury_ratio !== null && isCommonHoldingKind(holding))
    .sort((a, b) => (b.treasury_ratio ?? 0) - (a.treasury_ratio ?? 0))
    .slice(0, limit)
    .map((holding) => ({
      label: holding.corp_name,
      value: holding.treasury_ratio ?? 0
    }));
}

function holdingSummary(holding: TreasuryHoldingSnapshot) {
  return [holding.corp_name, holding.stock_code, holding.stock_kind, holding.as_of_date]
    .filter(Boolean)
    .join(" ");
}

export function returnDistribution(
  reactions: PriceReaction[],
  window: ReturnWindow = 20
): ChartDatum[] {
  const buckets = [
    { label: "< -10%", min: -Infinity, max: -0.1 },
    { label: "-10~-5%", min: -0.1, max: -0.05 },
    { label: "-5~0%", min: -0.05, max: 0 },
    { label: "0~5%", min: 0, max: 0.05 },
    { label: "5~10%", min: 0.05, max: 0.1 },
    { label: "> 10%", min: 0.1, max: Infinity }
  ];
  return buckets.map((bucket) => ({
    label: bucket.label,
    value: reactions.filter((reaction) => {
      const value = relativeReturn(reaction, window);
      return value !== null && value >= bucket.min && value < bucket.max;
    }).length
  }));
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

const acquisitionTypes = new Set<EventType>(["direct_acquisition", "trust_contract_start"]);

export function marketOptions(): Array<Market | "ALL"> {
  return ["ALL", "KOSPI", "KOSDAQ"];
}
