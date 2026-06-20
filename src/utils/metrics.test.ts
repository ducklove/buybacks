import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  dedupeHoldingTimeline,
  filterEvents,
  latestHoldingSnapshots,
  topHoldings
} from "./metrics";
import type { EnrichedEvent, EventType, TreasuryHoldingSnapshot } from "../types/buybacks";

const event = (event_id: string, event_type: EventType): EnrichedEvent => ({
  event_id,
  event_type,
  corp_code: "00126380",
  stock_code: "005930",
  corp_name: "삼성전자",
  disclosure_date: "2026-05-22",
  decision_date: "2026-05-22",
  period_start: null,
  period_end: null,
  planned_shares_common: null,
  planned_shares_other: null,
  planned_amount_krw: null,
  actual_shares: null,
  actual_amount_krw: null,
  method: null,
  purpose: null,
  broker: null,
  holding_before_common: null,
  holding_before_ratio_common: null,
  source: "MANUAL",
  rcept_no: null,
  source_url: null,
  raw_report_name: null,
  company: {
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    market: "KOSPI",
    sector: null,
    last_updated: "2026-06-20"
  }
});

const holding = (
  stock_kind: string,
  treasury_ratio: number | null,
  overrides: Partial<TreasuryHoldingSnapshot> = {}
): TreasuryHoldingSnapshot => ({
  corp_code: "00111722",
  stock_code: "006800",
  corp_name: "Mirae Asset Securities",
  as_of_date: "2025-12-31",
  report_year: 2025,
  report_code: "11011",
  stock_kind,
  beginning_qty: null,
  acquired_qty: null,
  disposed_qty: null,
  retired_qty: null,
  ending_qty: 100,
  issued_shares: 1000,
  treasury_ratio,
  floating_shares: 900,
  source_rcept_no: null,
  ...overrides
});

describe("filterEvents", () => {
  const events = [
    event("acquisition", "direct_acquisition"),
    event("disposition", "direct_disposition"),
    event("retirement", "retirement")
  ];

  it("keeps every event type when no type filter is selected", () => {
    expect(filterEvents(events, DEFAULT_FILTERS).map((item) => item.event_id)).toEqual([
      "acquisition",
      "disposition",
      "retirement"
    ]);
  });

  it("matches any selected event type", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      eventTypes: ["direct_acquisition", "retirement"] satisfies EventType[]
    };

    expect(filterEvents(events, filters).map((item) => item.event_id)).toEqual([
      "acquisition",
      "retirement"
    ]);
  });
});

describe("holding snapshots", () => {
  it("keeps the latest common and preferred holdings separately", () => {
    const snapshots = [
      holding("\uBCF4\uD1B5\uC8FC", 0.12, { as_of_date: "2024-12-31" }),
      holding("\uBCF4\uD1B5\uC8FC", 0.23),
      holding("1\uC6B0\uC120\uC8FC", 0.3)
    ];

    const latest = latestHoldingSnapshots(snapshots);

    expect(latest).toHaveLength(2);
    expect(topHoldings(latest, 2).map((item) => item.label)).toEqual([
      "Mirae Asset Securities 006800 1\uC6B0\uC120\uC8FC 2025-12-31",
      "Mirae Asset Securities 006800 \uBCF4\uD1B5\uC8FC 2025-12-31"
    ]);
  });

  it("deduplicates same-date timeline rows by stock kind and keeps richer rows", () => {
    const sparse = holding("\uBCF4\uD1B5\uC8FC", null, {
      ending_qty: null,
      issued_shares: 1000,
      floating_shares: 1000,
      report_code: "11014"
    });
    const complete = holding("\uBCF4\uD1B5\uC8FC", 0.23, {
      ending_qty: 230,
      issued_shares: 1000,
      floating_shares: 770,
      report_code: "11011"
    });

    expect(dedupeHoldingTimeline([sparse, complete])).toEqual([complete]);
  });
});
