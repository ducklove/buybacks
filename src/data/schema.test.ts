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
          change_rate: 0.01
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
});
