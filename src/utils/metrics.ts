import type {
  BuybacksDataset,
  EnrichedEvent,
  EventType,
  Filters,
  Market,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";

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
  search: "",
  minHoldingRatio: 0,
  maxHoldingRatio: 0.3
};

export function enrichEvents(dataset: BuybacksDataset): EnrichedEvent[] {
  const companyByStock = new Map(dataset.companies.map((company) => [company.stock_code, company]));
  const latestHoldingByStock = latestHoldingMap(dataset.holdingSnapshots);
  const reactionByEvent = new Map(dataset.priceReactions.map((reaction) => [reaction.event_id, reaction]));

  return dataset.events.map((event) => ({
    ...event,
    company: companyByStock.get(event.stock_code),
    holding: latestHoldingByStock.get(event.stock_code),
    priceReaction: reactionByEvent.get(event.event_id)
  }));
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
      (previous.as_of_date === snapshot.as_of_date && holdingKindPriority(snapshot) > holdingKindPriority(previous))
    ) {
      byStock.set(snapshot.stock_code, snapshot);
    }
  });
  return byStock;
}

function holdingKindPriority(snapshot: TreasuryHoldingSnapshot) {
  const stockKind = snapshot.stock_kind.toLowerCase();
  if (stockKind.includes("\uBCF4\uD1B5") || stockKind.includes("common")) return 3;
  if (stockKind.includes("\uC6B0\uC120") || stockKind.includes("preferred")) return 2;
  return 1;
}

export function filterEvents(events: EnrichedEvent[], filters: Filters): EnrichedEvent[] {
  const search = filters.search.trim().toLowerCase();
  return events.filter((event) => {
    const marketMatch = filters.market === "ALL" || event.company?.market === filters.market;
    const typeMatch =
      filters.eventTypes.length === 0 || filters.eventTypes.includes(event.event_type);
    const yearMatch = filters.year === "ALL" || event.disclosure_date.startsWith(filters.year);
    const ratio = event.holding?.treasury_ratio ?? event.holding_before_ratio_common ?? null;
    const ratioMatch =
      ratio === null || (ratio >= filters.minHoldingRatio && ratio <= filters.maxHoldingRatio);
    const searchMatch =
      search.length === 0 ||
      event.corp_name.toLowerCase().includes(search) ||
      event.stock_code.includes(search);
    return marketMatch && typeMatch && yearMatch && ratioMatch && searchMatch;
  });
}

export function availableYears(events: EnrichedEvent[]): string[] {
  return Array.from(new Set(events.map((event) => event.disclosure_date.slice(0, 4)))).sort().reverse();
}

export function buildKpis(events: EnrichedEvent[], holdings: TreasuryHoldingSnapshot[]): KpiMetric[] {
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - 1);
  const recent = events.filter((event) => new Date(event.disclosure_date) >= cutoff);
  const acquisitions = recent.filter((event) => acquisitionTypes.has(event.event_type)).length;
  const dispositions = recent.filter((event) => event.event_type === "direct_disposition").length;
  const retirements = recent.filter((event) => event.event_type === "retirement").length;
  const topHolding = [...holdings]
    .filter((holding) => holding.treasury_ratio !== null)
    .sort((a, b) => (b.treasury_ratio ?? 0) - (a.treasury_ratio ?? 0))[0];
  const averageReturn20d = average(
    events
      .map((event) => event.priceReaction?.return_20d ?? null)
      .filter((value): value is number => value !== null)
  );

  return [
    {
      label: "최근 12개월 취득 결정",
      value: `${acquisitions}건`,
      detail: "직접취득 및 신탁체결 포함",
      tone: "teal"
    },
    {
      label: "최근 12개월 처분 결정",
      value: `${dispositions}건`,
      detail: "직접처분 공시 기준",
      tone: "amber"
    },
    {
      label: "최근 12개월 소각 이벤트",
      value: `${retirements}건`,
      detail: "소각 또는 소각결정 기준",
      tone: "green"
    },
    {
      label: "최고 보유비율",
      value: topHolding ? `${((topHolding.treasury_ratio ?? 0) * 100).toFixed(2)}%` : "-",
      detail: topHolding ? `${topHolding.corp_name} · ${topHolding.as_of_date}` : "데이터 없음",
      tone: "neutral"
    },
    {
      label: "평균 +20D 수익률",
      value: averageReturn20d === null ? "-" : `${averageReturn20d > 0 ? "+" : ""}${(averageReturn20d * 100).toFixed(2)}%`,
      detail: "가격 데이터가 있는 이벤트 평균",
      tone: "teal"
    }
  ];
}

export function yearlyEventCounts(events: EnrichedEvent[]): ChartDatum[] {
  const counts = new Map<string, number>();
  events.forEach((event) => {
    const year = event.disclosure_date.slice(0, 4);
    counts.set(year, (counts.get(year) ?? 0) + 1);
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
    .filter((holding) => holding.treasury_ratio !== null)
    .sort((a, b) => (b.treasury_ratio ?? 0) - (a.treasury_ratio ?? 0))
    .slice(0, limit)
    .map((holding) => ({
      label: `${holding.corp_name} ${holding.stock_code}`,
      value: holding.treasury_ratio ?? 0
    }));
}

export function returnDistribution(reactions: PriceReaction[]): ChartDatum[] {
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
    value: reactions.filter(
      (reaction) =>
        reaction.return_20d !== null &&
        reaction.return_20d >= bucket.min &&
        reaction.return_20d < bucket.max
    ).length
  }));
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

const acquisitionTypes = new Set<EventType>(["direct_acquisition", "trust_contract_start"]);

export function marketOptions(): Array<Market | "ALL"> {
  return ["ALL", "KOSPI", "KOSDAQ", "KONEX", "OTHER"];
}
