import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  buildKpis,
  dedupeHoldingTimeline,
  filterEvents,
  latestHoldingSnapshots,
  latestPriceMap,
  marketOptions,
  monthlyAcquisitionCounts,
  returnDistribution,
  topHoldings
} from "./metrics";
import type { EnrichedEvent, EventType, PriceReaction, TreasuryHoldingSnapshot } from "../types/buybacks";

const priceReaction = (
  event_id: string,
  return_20d: number | null,
  abnormal_return_20d: number | null,
  abnormal_return_5d: number | null = null,
  abnormal_return_60d: number | null = null
): PriceReaction => ({
  event_id,
  stock_code: "005930",
  event_date: "2026-05-22",
  close_t0: 100,
  return_1d: null,
  return_5d: abnormal_return_5d,
  return_20d,
  return_60d: abnormal_return_60d,
  max_drawdown_20d: null,
  max_drawdown_60d: null,
  market_return_5d: abnormal_return_5d !== null ? 0 : null,
  abnormal_return_5d,
  market_return_20d: return_20d !== null && abnormal_return_20d !== null ? return_20d - abnormal_return_20d : null,
  abnormal_return_20d,
  market_return_60d: abnormal_return_60d !== null ? 0 : null,
  abnormal_return_60d,
  volume_change_20d: null,
  data_quality: "partial"
});

const event = (
  event_id: string,
  event_type: EventType,
  reaction?: PriceReaction
): EnrichedEvent => ({
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
  },
  priceReaction: reaction
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
    expect(topHoldings(latest, 2).map((item) => item.label)).toEqual(["Mirae Asset Securities"]);
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

describe("event count charts", () => {
  it("counts only direct acquisitions and trust starts by disclosure month", () => {
    expect(
      monthlyAcquisitionCounts([
        event("direct-1", "direct_acquisition"),
        {
          ...event("trust-1", "trust_contract_start"),
          disclosure_date: "2026-05-29"
        },
        {
          ...event("direct-2", "direct_acquisition"),
          disclosure_date: "2026-06-03"
        },
        {
          ...event("disposition-1", "direct_disposition"),
          disclosure_date: "2026-06-04"
        }
      ])
    ).toEqual([
      { label: "2026-05", value: 2 },
      { label: "2026-06", value: 1 }
    ]);
  });
});

describe("latest prices", () => {
  it("keeps the newest close for each stock", () => {
    const prices = latestPriceMap([
      { stock_code: "003540", price_date: "2026-06-18", close: 17450, source: "kis_proxy" },
      { stock_code: "003540", price_date: "2026-06-19", close: 17800, source: "kis_proxy" },
      { stock_code: "005930", price_date: "2026-06-19", close: 71200, source: "kis_proxy" }
    ]);

    expect(prices.get("003540")?.close).toBe(17800);
    expect(prices.get("005930")?.close).toBe(71200);
  });
});

describe("return metrics", () => {
  it("uses index-relative returns for KPI averages and distribution buckets", () => {
    const reactions = [
      priceReaction("positive-simple-negative-relative", 0.2, -0.06, 0.04, -0.12),
      priceReaction("negative-simple-positive-relative", -0.2, 0.07, -0.02, 0.11)
    ];
    const kpis = buildKpis(
      [
        event("positive-simple-negative-relative", "direct_acquisition", reactions[0]),
        event("negative-simple-positive-relative", "direct_acquisition", reactions[1])
      ],
      []
    );

    expect(kpis[kpis.length - 1]).toMatchObject({
      label: "평균 +20D 지수대비",
      value: "+0.50%"
    });
    expect(returnDistribution(reactions)).toEqual([
      { label: "< -10%", value: 0 },
      { label: "-10~-5%", value: 1 },
      { label: "-5~0%", value: 0 },
      { label: "0~5%", value: 0 },
      { label: "5~10%", value: 1 },
      { label: "> 10%", value: 0 }
    ]);
    expect(returnDistribution(reactions, 5)).toEqual([
      { label: "< -10%", value: 0 },
      { label: "-10~-5%", value: 0 },
      { label: "-5~0%", value: 1 },
      { label: "0~5%", value: 1 },
      { label: "5~10%", value: 0 },
      { label: "> 10%", value: 0 }
    ]);
    expect(returnDistribution(reactions, 60)).toEqual([
      { label: "< -10%", value: 1 },
      { label: "-10~-5%", value: 0 },
      { label: "-5~0%", value: 0 },
      { label: "0~5%", value: 0 },
      { label: "5~10%", value: 0 },
      { label: "> 10%", value: 1 }
    ]);
  });

  it("offers only KOSPI and KOSDAQ market filters", () => {
    expect(marketOptions()).toEqual(["ALL", "KOSPI", "KOSDAQ"]);
  });
});
