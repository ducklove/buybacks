import { describe, expect, it } from "vitest";
import { validateDataset } from "./schema";
import type { BuybacksDataset } from "../types/buybacks";

describe("validateDataset", () => {
  it("accepts the normalized buybacks shape", () => {
    const dataset: BuybacksDataset = {
      companies: [
        {
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          market: "KOSPI",
          sector: null,
          last_updated: "2026-06-20"
        },
        {
          corp_code: "00111722",
          stock_code: "00680K",
          corp_name: "미래에셋증권2우B",
          market: "KOSPI",
          sector: null,
          last_updated: "2026-06-20"
        }
      ],
      events: [
        {
          event_id: "event-1",
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          event_type: "direct_acquisition",
          disclosure_date: "2026-05-22",
          decision_date: "2026-05-22",
          period_start: null,
          period_end: null,
          planned_shares_common: 100,
          planned_shares_other: null,
          planned_amount_krw: 1000,
          actual_shares: null,
          actual_amount_krw: null,
          method: null,
          purpose: null,
          broker: null,
          holding_before_common: null,
          holding_before_ratio_common: null,
          source: "DART",
          rcept_no: "20260522000001",
          source_url: null,
          raw_report_name: "자기주식취득"
        }
      ],
      holdingSnapshots: [],
      priceReactions: [
        {
          event_id: "event-1",
          stock_code: "005930",
          event_date: "2026-05-22",
          close_t0: 100,
          return_1d: 0.01,
          return_5d: null,
          return_20d: null,
          return_60d: null,
          max_drawdown_20d: null,
          max_drawdown_60d: null,
          market_return_20d: null,
          abnormal_return_20d: null,
          volume_change_20d: null,
          data_quality: "partial"
        }
      ],
      latestPrices: [
        {
          stock_code: "005930",
          price_date: "2026-06-19",
          close: 110,
          source: "fixture",
          change_rate: 0.01,
          issued_shares: 1000,
          market_cap_krw: 110000,
          change_code: "2"
        }
      ],
      executions: [
        {
          execution_id: "exec-1",
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          execution_type: "acquisition_result",
          disclosure_date: "2026-06-19",
          origin_report_date: "2026-05-22",
          period_start: "2026-05-23",
          period_end: "2026-06-18",
          ordered_shares: 100,
          actual_shares: 90,
          actual_amount_krw: 9000,
          avg_price_krw: 100,
          planned_amount_krw: 10000,
          planned_shares: null,
          shortfall: false,
          shortfall_reason: null,
          holding_after_qty: 190,
          holding_after_ratio: 0.02,
          trust_contract_amount_krw: null,
          trust_progress_ratio: null,
          // 취득/처분 결과보고서는 보유상황 기준일이 없을 수 있다 — null이 유효해야 한다.
          as_of_date: null,
          linked_event_id: "event-1",
          link_method: "report_date",
          source: "DART",
          rcept_no: "20260619000001",
          source_url: null,
          raw_report_name: "자기주식취득결과보고서"
        }
      ],
      status: {
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: true,
        krx_available: false,
        companies_count: 2,
        events_count: 1,
        holdings_count: 0,
        price_reactions_count: 1,
        latest_prices_count: 1,
        warnings: []
      }
    };

    expect(validateDataset(dataset)).toEqual([]);
  });

  it("reports invalid enum values and foreign keys", () => {
    const dataset = {
      companies: [],
      events: [
        {
          event_id: "bad",
          corp_code: "00000000",
          stock_code: "999999",
          corp_name: "bad",
          event_type: "boom",
          disclosure_date: "20260522",
          source: "NOPE"
        }
      ],
      holdingSnapshots: [],
      priceReactions: [],
      latestPrices: [],
      executions: [],
      status: {
        generated_at: "",
        dart_available: false,
        krx_available: false,
        companies_count: 0,
        events_count: 1,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      }
    } as unknown as BuybacksDataset;

    expect(validateDataset(dataset).length).toBeGreaterThan(0);
  });

  it("reports duplicate execution ids and unknown linked events", () => {
    const dataset = {
      companies: [
        {
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          market: "KOSPI",
          sector: null,
          last_updated: "2026-06-20"
        }
      ],
      events: [],
      holdingSnapshots: [],
      priceReactions: [],
      latestPrices: [],
      executions: [
        {
          execution_id: "dup",
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          execution_type: "acquisition_result",
          disclosure_date: "2026-06-19",
          origin_report_date: null,
          period_start: null,
          period_end: null,
          ordered_shares: null,
          actual_shares: 90,
          actual_amount_krw: 9000,
          avg_price_krw: 100,
          planned_amount_krw: null,
          planned_shares: null,
          shortfall: false,
          shortfall_reason: null,
          holding_after_qty: null,
          holding_after_ratio: null,
          trust_contract_amount_krw: null,
          trust_progress_ratio: null,
          as_of_date: "2026-06-19",
          linked_event_id: "missing-event",
          link_method: "report_date",
          source: "DART",
          rcept_no: null,
          source_url: null,
          raw_report_name: null
        },
        {
          execution_id: "dup",
          corp_code: "00126380",
          stock_code: "005930",
          corp_name: "삼성전자",
          execution_type: "acquisition_result",
          disclosure_date: "2026-06-19",
          origin_report_date: null,
          period_start: null,
          period_end: null,
          ordered_shares: null,
          actual_shares: 90,
          actual_amount_krw: 9000,
          avg_price_krw: 100,
          planned_amount_krw: null,
          planned_shares: null,
          shortfall: false,
          shortfall_reason: null,
          holding_after_qty: null,
          holding_after_ratio: null,
          trust_contract_amount_krw: null,
          trust_progress_ratio: null,
          as_of_date: "2026-06-19",
          linked_event_id: null,
          link_method: "unlinked",
          source: "DART",
          rcept_no: null,
          source_url: null,
          raw_report_name: null
        }
      ],
      status: {
        generated_at: "",
        dart_available: false,
        krx_available: false,
        companies_count: 1,
        events_count: 0,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      }
    } as unknown as BuybacksDataset;

    const errors = validateDataset(dataset);
    expect(errors).toContain("executions[1] duplicate execution_id");
    expect(errors).toContain("executions[0] unknown linked_event_id missing-event");
  });

  it("accepts valid optional reaction series and CAR curves", () => {
    const dataset = {
      companies: [],
      events: [],
      holdingSnapshots: [],
      priceReactions: [],
      latestPrices: [],
      executions: [],
      reactionSeries: [
        {
          event_id: "event-1",
          stock_code: "005930",
          event_date: "2026-05-22",
          t0_date: "2026-05-25",
          daily_return: [0.01, -0.002],
          daily_abnormal: [0.008, null],
          data_quality: "partial"
        }
      ],
      carCurves: {
        window: 60,
        min_events: 5,
        groups: [
          {
            event_type: "direct_acquisition",
            market: "ALL",
            n: 12,
            mean_car: Array.from({ length: 60 }, (_, index) => (index % 7 === 0 ? null : 0.001))
          }
        ]
      },
      status: {
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 0,
        events_count: 0,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      }
    } as unknown as BuybacksDataset;

    expect(validateDataset(dataset)).toEqual([]);
  });

  it("skips optional validation when the files are absent", () => {
    const dataset = {
      companies: [],
      events: [],
      holdingSnapshots: [],
      priceReactions: [],
      latestPrices: [],
      executions: [],
      reactionSeries: [],
      carCurves: null,
      status: {
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 0,
        events_count: 0,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      }
    } as unknown as BuybacksDataset;

    expect(validateDataset(dataset)).toEqual([]);
  });

  it("reports malformed reaction series and CAR curve groups", () => {
    const dataset = {
      companies: [],
      events: [],
      holdingSnapshots: [],
      priceReactions: [],
      latestPrices: [],
      executions: [],
      reactionSeries: [
        {
          event_id: "dup-series",
          stock_code: "005930",
          event_date: "2026-05-22",
          t0_date: "2026-05-25",
          daily_return: Array.from({ length: 61 }, () => 0.001),
          daily_abnormal: Array.from({ length: 61 }, () => 0.001),
          data_quality: "partial"
        },
        {
          event_id: "dup-series",
          stock_code: "005930",
          event_date: "2026-05-22",
          t0_date: "2026-05-25",
          daily_return: [0.01, 0.02],
          daily_abnormal: [0.01],
          data_quality: "partial"
        }
      ],
      carCurves: {
        window: 60,
        min_events: 5,
        groups: [
          {
            event_type: "direct_acquisition",
            market: "KONEX",
            n: 3,
            mean_car: Array.from({ length: 61 }, () => 0.001)
          }
        ]
      },
      status: {
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 0,
        events_count: 0,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      }
    } as unknown as BuybacksDataset;

    const errors = validateDataset(dataset);
    expect(errors).toContain("reactionSeries[0] daily_return longer than 60");
    expect(errors).toContain("reactionSeries[1] duplicate event_id dup-series");
    expect(errors).toContain("reactionSeries[1] daily_abnormal length must match daily_return");
    expect(errors).toContain("carCurves.groups[0] invalid market");
    expect(errors).toContain("carCurves.groups[0] mean_car longer than 60");
  });
});
