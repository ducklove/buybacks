import { describe, expect, it } from "vitest";
import { latestMarketCap, marketCapFrom, plannedAcquisitionStake, plannedEventStake } from "./marketCap";
import type { BuybackEvent, LatestPriceSnapshot, PriceReaction, TreasuryHoldingSnapshot } from "../types/buybacks";

const holding: TreasuryHoldingSnapshot = {
  corp_code: "00111722",
  stock_code: "006800",
  corp_name: "Mirae Asset Securities",
  as_of_date: "2025-12-31",
  report_year: 2025,
  report_code: "11011",
  stock_kind: "보통주",
  beginning_qty: null,
  acquired_qty: null,
  disposed_qty: null,
  retired_qty: null,
  ending_qty: 131_035_874,
  issued_shares: 567_085_734,
  treasury_ratio: 0.231,
  floating_shares: null,
  source_rcept_no: null
};

const reaction: PriceReaction = {
  event_id: "event-1",
  stock_code: "006800",
  event_date: "2026-06-17",
  close_t0: 50_700,
  return_1d: -0.038,
  return_5d: null,
  return_20d: null,
  return_60d: null,
  max_drawdown_20d: null,
  max_drawdown_60d: null,
  market_return_20d: null,
  abnormal_return_20d: null,
  volume_change_20d: null,
  data_quality: "partial"
};

const latestPrice: LatestPriceSnapshot = {
  stock_code: "006800",
  price_date: "2026-06-19",
  close: 51_000,
  source: "kis_proxy"
};

describe("market cap utilities", () => {
  it("calculates market cap from close and issued shares", () => {
    expect(marketCapFrom(reaction, holding)).toMatchObject({
      amount: 50_700 * 567_085_734,
      close: 50_700,
      issuedShares: 567_085_734,
      priceDate: "2026-06-17"
    });
  });

  it("uses the latest reaction with a close", () => {
    const stale = { ...reaction, event_id: "old", event_date: "2026-06-10", close_t0: 49_000 };
    const missing = { ...reaction, event_id: "newer", event_date: "2026-06-18", close_t0: null };
    expect(latestMarketCap(undefined, [stale, missing, reaction], holding).amount).toBe(50_700 * 567_085_734);
  });

  it("prefers latest prices over event reaction closes", () => {
    expect(latestMarketCap(latestPrice, [reaction], holding)).toMatchObject({
      amount: 51_000 * 567_085_734,
      close: 51_000,
      priceDate: "2026-06-19"
    });
  });

  it("uses market cap and issued shares carried by a latest price snapshot", () => {
    expect(
      marketCapFrom(
        {
          ...latestPrice,
          issued_shares: 559_566_880,
          market_cap_krw: 27_278_885_400_000
        },
        undefined
      )
    ).toMatchObject({
      amount: 27_278_885_400_000,
      close: 51_000,
      issuedShares: 559_566_880
    });
  });

  it("returns null when a price or share denominator is unavailable", () => {
    expect(marketCapFrom(undefined, holding).amount).toBeNull();
    expect(marketCapFrom(reaction, undefined).amount).toBeNull();
  });

  it("calculates planned acquisition stake for acquisition-like events only", () => {
    expect(plannedAcquisitionStake("direct_acquisition", 100, 1000)).toBe(0.1);
    expect(plannedAcquisitionStake("trust_contract_start", 25, 1000)).toBe(0.025);
    expect(plannedAcquisitionStake("direct_disposition", 100, 1000)).toBeNull();
    expect(plannedAcquisitionStake("direct_acquisition", 100, null)).toBeNull();
  });

  it("uses planned share ratio for retirement event stake", () => {
    const event: BuybackEvent = {
      event_id: "event-1",
      corp_code: "00110893",
      stock_code: "003540",
      corp_name: "Daishin Securities",
      event_type: "retirement",
      disclosure_date: "2026-06-19",
      decision_date: null,
      period_start: null,
      period_end: null,
      planned_shares_common: 1_553_637,
      planned_shares_other: 1_005_000,
      planned_amount_krw: 66_496_435_400,
      planned_share_ratio_common: 0.031564,
      planned_share_ratio_other: 0.024707,
      actual_shares: null,
      actual_amount_krw: null,
      method: null,
      purpose: null,
      broker: null,
      holding_before_common: null,
      holding_before_ratio_common: null,
      source: "DART",
      rcept_no: "20260619800826",
      source_url: null,
      raw_report_name: null
    };

    expect(plannedEventStake(event, null)).toBe(0.031564);
  });
});
