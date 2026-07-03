import { describe, expect, it } from "vitest";
import {
  DISTRIBUTION_BUCKET_COUNT,
  availableBacktestYears,
  buildBacktestItems,
  cumulativeAbnormalReturn,
  cumulativeSimpleReturn,
  runBacktest,
  type BacktestItem
} from "./backtest";
import type { BuybackEvent, Company, EventType, Market, ReactionSeries } from "../types/buybacks";

function makeSeries(overrides: Partial<ReactionSeries> = {}): ReactionSeries {
  return {
    event_id: "event-1",
    stock_code: "005930",
    event_date: "2026-05-22",
    t0_date: "2026-05-25",
    daily_return: [0.01, 0.02, -0.01, 0.005, 0.003],
    daily_abnormal: [0.008, 0.015, -0.012, 0.004, 0.002],
    data_quality: "partial",
    ...overrides
  };
}

function makeItem(
  overrides: Partial<ReactionSeries> = {},
  eventType: EventType | null = "direct_acquisition",
  market: Market | null = "KOSPI"
): BacktestItem {
  return { series: makeSeries(overrides), eventType, market };
}

describe("cumulativeSimpleReturn", () => {
  it("compounds daily simple returns over the holding period", () => {
    expect(cumulativeSimpleReturn([0.1, 0.1], 2)).toBeCloseTo(0.21, 10);
    expect(cumulativeSimpleReturn([0.01, -0.02, 0.03], 1)).toBeCloseTo(0.01, 10);
  });

  it("excludes events whose series is shorter than the holding period", () => {
    expect(cumulativeSimpleReturn([0.01, 0.02], 3)).toBeNull();
    expect(cumulativeSimpleReturn([], 1)).toBeNull();
    expect(cumulativeSimpleReturn([0.01], 0)).toBeNull();
  });
});

describe("cumulativeAbnormalReturn", () => {
  it("sums abnormal returns over the holding period (CAR definition)", () => {
    expect(cumulativeAbnormalReturn([0.01, 0.02, -0.005], 3)).toBeCloseTo(0.025, 10);
  });

  it("excludes the event when a null appears within the window", () => {
    expect(cumulativeAbnormalReturn([0.01, null, 0.02], 3)).toBeNull();
    // null 이 보유기간 밖에 있으면 포함된다
    expect(cumulativeAbnormalReturn([0.01, 0.02, null], 2)).toBeCloseTo(0.03, 10);
  });

  it("excludes events whose series is shorter than the holding period", () => {
    expect(cumulativeAbnormalReturn([0.01], 2)).toBeNull();
  });
});

describe("buildBacktestItems", () => {
  it("joins event types and markets onto reaction series", () => {
    const events = [
      { event_id: "event-1", stock_code: "005930", event_type: "retirement" }
    ] as BuybackEvent[];
    const companies = [{ stock_code: "005930", market: "KOSPI" }] as Company[];
    const series = [makeSeries(), makeSeries({ event_id: "event-2", stock_code: "999999" })];

    const items = buildBacktestItems(series, events, companies);
    expect(items[0].eventType).toBe("retirement");
    expect(items[0].market).toBe("KOSPI");
    expect(items[1].eventType).toBeNull();
    expect(items[1].market).toBeNull();
  });
});

describe("availableBacktestYears", () => {
  it("returns unique years sorted descending", () => {
    const series = [
      makeSeries({ event_date: "2024-03-02" }),
      makeSeries({ event_id: "e2", event_date: "2026-01-15" }),
      makeSeries({ event_id: "e3", event_date: "2024-11-30" })
    ];
    expect(availableBacktestYears(series)).toEqual(["2026", "2024"]);
  });
});

describe("runBacktest", () => {
  const baseOptions = {
    eventTypes: [] as EventType[],
    market: "ALL" as const,
    year: "ALL",
    holdDays: 2,
    basis: "simple" as const
  };

  it("computes mean, median, win rate, best, and worst", () => {
    const items = [
      makeItem({ event_id: "e1", daily_return: [0.1, 0.1] }), // 0.21
      makeItem({ event_id: "e2", daily_return: [-0.1, -0.1] }), // -0.19
      makeItem({ event_id: "e3", daily_return: [0.05, 0.0] }) // 0.05
    ];
    const result = runBacktest(items, baseOptions);
    expect(result.n).toBe(3);
    expect(result.mean).toBeCloseTo((0.21 - 0.19 + 0.05) / 3, 10);
    expect(result.median).toBeCloseTo(0.05, 10);
    expect(result.winRate).toBeCloseTo(2 / 3, 10);
    expect(result.best).toBeCloseTo(0.21, 10);
    expect(result.worst).toBeCloseTo(-0.19, 10);
  });

  it("averages the two middle values for an even sample count", () => {
    const items = [
      makeItem({ event_id: "e1", daily_return: [0.1] }),
      makeItem({ event_id: "e2", daily_return: [0.2] }),
      makeItem({ event_id: "e3", daily_return: [0.3] }),
      makeItem({ event_id: "e4", daily_return: [0.4] })
    ];
    const result = runBacktest(items, { ...baseOptions, holdDays: 1 });
    expect(result.median).toBeCloseTo(0.25, 10);
  });

  it("applies event type, market, and year filters", () => {
    const items = [
      makeItem({ event_id: "e1" }, "direct_acquisition", "KOSPI"),
      makeItem({ event_id: "e2" }, "retirement", "KOSDAQ"),
      makeItem({ event_id: "e3", event_date: "2025-02-01" }, "direct_acquisition", "KOSPI"),
      makeItem({ event_id: "e4" }, null, null)
    ];

    expect(runBacktest(items, { ...baseOptions, eventTypes: ["retirement"] }).n).toBe(1);
    expect(runBacktest(items, { ...baseOptions, market: "KOSDAQ" }).n).toBe(1);
    expect(runBacktest(items, { ...baseOptions, year: "2025" }).n).toBe(1);
    // 유형이 지정되면 조인 실패(null 유형) 이벤트는 제외된다
    expect(
      runBacktest(items, { ...baseOptions, eventTypes: ["direct_acquisition", "retirement"] }).n
    ).toBe(3);
    // 빈 유형 배열은 전체를 포함한다
    expect(runBacktest(items, baseOptions).n).toBe(4);
  });

  it("excludes events without enough data for the holding period", () => {
    const items = [
      makeItem({ event_id: "e1", daily_return: [0.01, 0.02, 0.03] }),
      makeItem({ event_id: "e2", daily_return: [0.01] })
    ];
    const result = runBacktest(items, { ...baseOptions, holdDays: 3 });
    expect(result.n).toBe(1);
  });

  it("excludes abnormal-basis events with null inside the window", () => {
    const items = [
      makeItem({ event_id: "e1", daily_abnormal: [0.01, null, 0.02] }),
      makeItem({ event_id: "e2", daily_abnormal: [0.01, 0.02, 0.03] })
    ];
    const result = runBacktest(items, { ...baseOptions, holdDays: 3, basis: "abnormal" });
    expect(result.n).toBe(1);
    expect(result.mean).toBeCloseTo(0.06, 10);
  });

  it("returns an empty result when nothing matches", () => {
    const result = runBacktest([], baseOptions);
    expect(result).toEqual({
      n: 0,
      mean: null,
      median: null,
      winRate: null,
      best: null,
      worst: null,
      distribution: []
    });
  });

  it("builds a 10-bucket distribution covering all samples", () => {
    const items = Array.from({ length: 21 }, (_, index) =>
      makeItem({ event_id: `e${index}`, daily_return: [(index - 10) * 0.01] })
    );
    const result = runBacktest(items, { ...baseOptions, holdDays: 1 });
    expect(result.distribution).toHaveLength(DISTRIBUTION_BUCKET_COUNT);
    expect(result.distribution.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(21);
    // 최댓값은 마지막 버킷에 포함된다
    expect(result.distribution[DISTRIBUTION_BUCKET_COUNT - 1].count).toBeGreaterThan(0);
    expect(result.distribution[0].from).toBeCloseTo(-0.1, 10);
    expect(result.distribution[DISTRIBUTION_BUCKET_COUNT - 1].to).toBeCloseTo(0.1, 10);
  });

  it("keeps all identical returns in a single bucket", () => {
    const items = [
      makeItem({ event_id: "e1", daily_return: [0.05] }),
      makeItem({ event_id: "e2", daily_return: [0.05] })
    ];
    const result = runBacktest(items, { ...baseOptions, holdDays: 1 });
    expect(result.distribution[0].count).toBe(2);
    expect(result.distribution.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(2);
  });
});
