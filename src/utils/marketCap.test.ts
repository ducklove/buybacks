import { describe, expect, it } from "vitest";
import { latestMarketCap, marketCapFrom } from "./marketCap";
import type { PriceReaction, TreasuryHoldingSnapshot } from "../types/buybacks";

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
    expect(latestMarketCap([stale, missing, reaction], holding).amount).toBe(50_700 * 567_085_734);
  });

  it("returns null when a price or share denominator is unavailable", () => {
    expect(marketCapFrom(undefined, holding).amount).toBeNull();
    expect(marketCapFrom(reaction, undefined).amount).toBeNull();
  });
});
