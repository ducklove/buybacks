import { describe, expect, it } from "vitest";
import { buildScreenerRows } from "./screener";
import type {
  BuybackExecution,
  Company,
  EnrichedEvent,
  EventType,
  LatestPriceSnapshot,
  TreasuryHoldingSnapshot
} from "../types/buybacks";

const NOW = new Date("2026-07-03T00:00:00.000Z");

function makeCompany(overrides: Partial<Company> = {}): Company {
  return {
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    market: "KOSPI",
    sector: "전기전자",
    last_updated: "2026-07-01",
    ...overrides
  };
}

function makeHolding(overrides: Partial<TreasuryHoldingSnapshot> = {}): TreasuryHoldingSnapshot {
  return {
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    as_of_date: "2026-06-30",
    report_year: 2026,
    report_code: "11012",
    stock_kind: "보통주",
    beginning_qty: null,
    acquired_qty: null,
    disposed_qty: null,
    retired_qty: null,
    ending_qty: 160000000,
    issued_shares: 5969782550,
    treasury_ratio: 0.0269,
    floating_shares: null,
    source_rcept_no: null,
    ...overrides
  };
}

function makeLatestPrice(overrides: Partial<LatestPriceSnapshot> = {}): LatestPriceSnapshot {
  return {
    stock_code: "005930",
    price_date: "2026-07-01",
    close: 80000,
    source: "KRX",
    change_rate: null,
    issued_shares: null,
    market_cap_krw: null,
    change_code: null,
    ...overrides
  };
}

function makeExecution(overrides: Partial<BuybackExecution> = {}): BuybackExecution {
  return {
    execution_id: "exec-1",
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    execution_type: "acquisition_result",
    disclosure_date: "2026-06-25",
    origin_report_date: "2026-05-22",
    period_start: "2026-05-23",
    period_end: "2026-06-22",
    ordered_shares: 1000,
    actual_shares: 800,
    actual_amount_krw: 800000,
    avg_price_krw: 1000,
    planned_amount_krw: 1000000,
    planned_shares: null,
    shortfall: false,
    shortfall_reason: null,
    holding_after_qty: null,
    holding_after_ratio: null,
    trust_contract_amount_krw: null,
    trust_progress_ratio: null,
    as_of_date: "2026-06-25",
    linked_event_id: "event-1",
    link_method: "report_date",
    source: "DART",
    rcept_no: null,
    source_url: null,
    raw_report_name: null,
    ...overrides
  };
}

function makeEvent(overrides: Partial<EnrichedEvent> = {}): EnrichedEvent {
  const eventType: EventType = overrides.event_type ?? "direct_acquisition";
  return {
    event_id: "event-1",
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    event_type: eventType,
    disclosure_date: "2026-06-01",
    decision_date: "2026-06-01",
    period_start: null,
    period_end: null,
    planned_shares_common: null,
    planned_shares_other: null,
    planned_amount_krw: 1000000,
    actual_shares: null,
    actual_amount_krw: null,
    method: null,
    purpose: null,
    broker: null,
    holding_before_common: null,
    holding_before_ratio_common: null,
    source: "DART",
    rcept_no: null,
    source_url: null,
    raw_report_name: null,
    ...overrides
  };
}

describe("buildScreenerRows", () => {
  it("returns an empty array when there are no events", () => {
    expect(buildScreenerRows([], NOW)).toEqual([]);
  });

  it("groups events by stock_code and counts by event type", () => {
    const events: EnrichedEvent[] = [
      makeEvent({ event_id: "e1", event_type: "direct_acquisition", stock_code: "005930" }),
      makeEvent({ event_id: "e2", event_type: "trust_contract_start", stock_code: "005930" }),
      makeEvent({ event_id: "e3", event_type: "direct_disposition", stock_code: "005930" }),
      makeEvent({ event_id: "e4", event_type: "retirement", stock_code: "005930" }),
      makeEvent({ event_id: "e5", event_type: "direct_acquisition", stock_code: "000660" })
    ];

    const rows = buildScreenerRows(events, NOW);
    expect(rows).toHaveLength(2);

    const samsung = rows.find((row) => row.stockCode === "005930");
    expect(samsung?.eventCount).toBe(4);
    expect(samsung?.acquisitionEventCount).toBe(2);
    expect(samsung?.dispositionEventCount).toBe(1);
    expect(samsung?.retirementEventCount).toBe(1);

    const skHynix = rows.find((row) => row.stockCode === "000660");
    expect(skHynix?.eventCount).toBe(1);
    expect(skHynix?.acquisitionEventCount).toBe(1);
  });

  it("sums planned_amount_krw for acquisition-series events within the last 12 months", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "recent-1",
        event_type: "direct_acquisition",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 1_000_000_000
      }),
      makeEvent({
        event_id: "recent-2",
        event_type: "trust_contract_start",
        disclosure_date: "2026-01-01",
        planned_amount_krw: 500_000_000
      }),
      makeEvent({
        event_id: "old",
        event_type: "direct_acquisition",
        disclosure_date: "2024-01-01",
        planned_amount_krw: 9_000_000_000
      }),
      makeEvent({
        event_id: "disposition",
        event_type: "direct_disposition",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 2_000_000_000
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.recentPlannedAcquisitionAmountKrw).toBe(1_500_000_000);
  });

  it("returns null recent planned amount when there are no recent acquisition-series events", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "old",
        event_type: "direct_acquisition",
        disclosure_date: "2020-01-01",
        planned_amount_krw: 9_000_000_000
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.recentPlannedAcquisitionAmountKrw).toBeNull();
  });

  it("computes acquisition intensity as recent planned amount divided by latest market cap", () => {
    const company = makeCompany();
    const holding = makeHolding({ issued_shares: 1_000_000 });
    const latestPrice = makeLatestPrice({ close: 1000, issued_shares: null, market_cap_krw: null });

    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "e1",
        event_type: "direct_acquisition",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 100_000_000,
        company,
        holding,
        latestPrice
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    // market cap = close(1000) * issuedShares(1,000,000) = 1,000,000,000
    expect(row.marketCapKrw).toBe(1_000_000_000);
    expect(row.acquisitionIntensity).toBeCloseTo(100_000_000 / 1_000_000_000);
  });

  it("returns null acquisition intensity when market cap is unavailable", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "e1",
        event_type: "direct_acquisition",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 100_000_000
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.marketCapKrw).toBeNull();
    expect(row.acquisitionIntensity).toBeNull();
  });

  it("computes retirement share as retirement plan amount over total acquisition plan amount", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "acq-1",
        event_type: "direct_acquisition",
        disclosure_date: "2026-01-01",
        planned_amount_krw: 1_000_000_000
      }),
      makeEvent({
        event_id: "retire-1",
        event_type: "retirement",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 250_000_000
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.retirementShare).toBeCloseTo(0.25);
  });

  it("returns null retirement share when there is no acquisition-series plan amount", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "retire-1",
        event_type: "retirement",
        disclosure_date: "2026-06-01",
        planned_amount_krw: 250_000_000
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.retirementShare).toBeNull();
  });

  it("averages completionRate across linked executions and ignores events without one", () => {
    const eventWithExecution = makeEvent({
      event_id: "e1",
      planned_shares_common: 100,
      execution: makeExecution({
        linked_event_id: "e1",
        actual_shares: 50,
        actual_amount_krw: null
      })
    });
    const eventWithoutExecution = makeEvent({ event_id: "e2", execution: undefined });

    const [row] = buildScreenerRows([eventWithExecution, eventWithoutExecution], NOW);
    expect(row.averageCompletionRate).toBeCloseTo(0.5);
  });

  it("returns null averageCompletionRate when no events have executions", () => {
    const events: EnrichedEvent[] = [makeEvent({ event_id: "e1", execution: undefined })];
    const [row] = buildScreenerRows(events, NOW);
    expect(row.averageCompletionRate).toBeNull();
  });

  it("uses the latest event's holding treasury_ratio and disclosure_date", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "e1",
        disclosure_date: "2026-01-01",
        holding: makeHolding({ treasury_ratio: 0.01 })
      }),
      makeEvent({
        event_id: "e2",
        disclosure_date: "2026-06-15",
        holding: makeHolding({ treasury_ratio: 0.05 })
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.holdingRatio).toBe(0.05);
    expect(row.lastEventDate).toBe("2026-06-15");
  });

  it("returns null holdingRatio when no holding snapshot is linked", () => {
    const events: EnrichedEvent[] = [makeEvent({ event_id: "e1", holding: undefined })];
    const [row] = buildScreenerRows(events, NOW);
    expect(row.holdingRatio).toBeNull();
  });

  it("stays crash-free and null-filled when executions, holdings, and latest prices are all empty", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "e1",
        company: undefined,
        holding: undefined,
        priceReaction: undefined,
        latestPrice: undefined,
        execution: undefined
      })
    ];

    const [row] = buildScreenerRows(events, NOW);
    expect(row.marketCapKrw).toBeNull();
    expect(row.acquisitionIntensity).toBeNull();
    expect(row.averageCompletionRate).toBeNull();
    expect(row.holdingRatio).toBeNull();
    expect(row.market).toBeNull();
  });

  it("falls back to the event's corp_name and derives market from the company when present", () => {
    const events: EnrichedEvent[] = [
      makeEvent({
        event_id: "e1",
        corp_name: "테스트기업",
        company: makeCompany({ market: "KOSDAQ" })
      })
    ];
    const [row] = buildScreenerRows(events, NOW);
    expect(row.corpName).toBe("삼성전자");
    expect(row.market).toBe("KOSDAQ");
  });
});
