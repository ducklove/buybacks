import type { EnrichedEvent, EventType, Market } from "../types/buybacks";
import { completionRate } from "./executions";
import { KPI_LOOKBACK_MONTHS } from "../constants";
import { marketCapFrom } from "./marketCap";

export interface ScreenerRow {
  stockCode: string;
  corpName: string;
  market: Market | null;
  eventCount: number;
  acquisitionEventCount: number;
  dispositionEventCount: number;
  retirementEventCount: number;
  recentPlannedAcquisitionAmountKrw: number | null;
  marketCapKrw: number | null;
  acquisitionIntensity: number | null;
  retirementShare: number | null;
  averageCompletionRate: number | null;
  holdingRatio: number | null;
  /** 최신 사업연도 현금배당금총액 / 시가총액. 배당 또는 시총 없으면 null */
  dividendYield: number | null;
  /** (현금배당금총액 + 최근 12M 취득계획금액) / 시가총액. 배당 또는 시총 없으면 null */
  totalShareholderReturn: number | null;
  lastEventDate: string | null;
}

const acquisitionPlanTypes = new Set<EventType>(["direct_acquisition", "trust_contract_start"]);
const dispositionTypes = new Set<EventType>(["direct_disposition"]);
const retirementTypes = new Set<EventType>(["retirement"]);

/**
 * EnrichedEvent[]를 종목(stock_code) 기준으로 집계해 기업 스크리너 행을 생성한다.
 * events가 비어 있으면 빈 배열을 반환한다. executions/holdings/latest_prices/dividends가 비어
 * 있어도 (EnrichedEvent의 execution/holding/latestPrice/dividend가 undefined인 경우) 크래시
 * 없이 null로 처리한다.
 */
export function buildScreenerRows(events: EnrichedEvent[], now: Date = new Date()): ScreenerRow[] {
  const byStock = new Map<string, EnrichedEvent[]>();
  events.forEach((event) => {
    const bucket = byStock.get(event.stock_code);
    if (bucket) {
      bucket.push(event);
    } else {
      byStock.set(event.stock_code, [event]);
    }
  });

  const cutoff = new Date(now);
  cutoff.setMonth(cutoff.getMonth() - KPI_LOOKBACK_MONTHS);

  return Array.from(byStock.entries()).map(([stockCode, stockEvents]) =>
    buildRowForStock(stockCode, stockEvents, cutoff)
  );
}

function buildRowForStock(
  stockCode: string,
  stockEvents: EnrichedEvent[],
  recentCutoff: Date
): ScreenerRow {
  const representative = pickRepresentativeCompanyInfo(stockEvents);

  const acquisitionEventCount = stockEvents.filter((event) =>
    acquisitionPlanTypes.has(event.event_type)
  ).length;
  const dispositionEventCount = stockEvents.filter((event) =>
    dispositionTypes.has(event.event_type)
  ).length;
  const retirementEventCount = stockEvents.filter((event) =>
    retirementTypes.has(event.event_type)
  ).length;

  const recentAcquisitionEvents = stockEvents.filter(
    (event) =>
      acquisitionPlanTypes.has(event.event_type) && new Date(event.disclosure_date) >= recentCutoff
  );
  const recentPlannedAcquisitionAmountKrw = sumPlannedAmount(recentAcquisitionEvents);

  const latestEvent = latestByDisclosureDate(stockEvents);
  const marketCapSnapshot = latestEvent
    ? marketCapFrom(latestEvent.latestPrice ?? latestEvent.priceReaction, latestEvent.holding)
    : { amount: null };
  const marketCapKrw = marketCapSnapshot.amount;

  const acquisitionIntensity = divideOrNull(recentPlannedAcquisitionAmountKrw, marketCapKrw);

  const totalAcquisitionPlanAmount = sumPlannedAmount(
    stockEvents.filter((event) => acquisitionPlanTypes.has(event.event_type))
  );
  const totalRetirementPlanAmount = sumPlannedAmount(
    stockEvents.filter((event) => retirementTypes.has(event.event_type))
  );
  const retirementShare = divideOrNull(totalRetirementPlanAmount, totalAcquisitionPlanAmount);

  const averageCompletionRate = averageOrNull(
    stockEvents
      .map((event) => completionRate(event, event.execution))
      .filter((value): value is number => value !== null)
  );

  const holdingRatio = latestEvent?.holding?.treasury_ratio ?? null;
  const lastEventDate = latestEvent?.disclosure_date ?? null;

  // enrichEvents가 종목별 최신 배당 레코드를 모든 이벤트에 동일하게 붙이므로
  // 대표 이벤트 하나에서 읽으면 충분하다.
  const cashDividendTotalKrw = latestEvent?.dividend?.cash_dividend_total_krw ?? null;
  const dividendYield = divideOrNull(cashDividendTotalKrw, marketCapKrw);
  // 취득계획이 없는(null) 종목은 배당만으로 총환원율을 계산한다.
  const totalShareholderReturn =
    cashDividendTotalKrw === null
      ? null
      : divideOrNull(cashDividendTotalKrw + (recentPlannedAcquisitionAmountKrw ?? 0), marketCapKrw);

  return {
    stockCode,
    corpName: representative.corpName,
    market: representative.market,
    eventCount: stockEvents.length,
    acquisitionEventCount,
    dispositionEventCount,
    retirementEventCount,
    recentPlannedAcquisitionAmountKrw,
    marketCapKrw,
    acquisitionIntensity,
    retirementShare,
    averageCompletionRate,
    holdingRatio,
    dividendYield,
    totalShareholderReturn,
    lastEventDate
  };
}

function pickRepresentativeCompanyInfo(events: EnrichedEvent[]): {
  corpName: string;
  market: Market | null;
} {
  const latest = latestByDisclosureDate(events);
  return {
    corpName: latest?.company?.corp_name ?? latest?.corp_name ?? "",
    market: latest?.company?.market ?? null
  };
}

function latestByDisclosureDate(events: EnrichedEvent[]): EnrichedEvent | undefined {
  return [...events].sort((a, b) => b.disclosure_date.localeCompare(a.disclosure_date))[0];
}

/**
 * 이벤트가 하나도 없거나, 있어도 planned_amount_krw를 하나도 알 수 없으면 null을 반환한다.
 * (금액이 실제로 0인 것과 데이터가 없어 알 수 없는 것을 구분한다.)
 */
function sumPlannedAmount(events: EnrichedEvent[]): number | null {
  const amounts = events
    .map((event) => event.planned_amount_krw)
    .filter((value): value is number => value !== null);
  if (amounts.length === 0) {
    return null;
  }
  return amounts.reduce((sum, value) => sum + value, 0);
}

function averageOrNull(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function divideOrNull(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator <= 0) {
    return null;
  }
  return numerator / denominator;
}
