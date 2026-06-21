import { describe, expect, it } from "vitest";
import { quoteToLatestPriceSnapshot } from "./realtimeQuotes";

describe("quoteToLatestPriceSnapshot", () => {
  it("normalizes naverfinance proxy quotes into latest price snapshots", () => {
    const snapshot = quoteToLatestPriceSnapshot(
      {
        symbol: "006800",
        summary: {
          current_price: 48_750,
          previous_close: 50_700,
          change_pct: 3.85
        },
        raw: {
          rf: "5",
          countOfListedStock: 559_566_880
        },
        meta: {
          polled_at: 1_782_050_233_207
        }
      },
      "006800"
    );

    expect(snapshot).toMatchObject({
      stock_code: "006800",
      close: 48_750,
      source: "naverfinance_proxy",
      change_rate: -0.0385,
      issued_shares: 559_566_880,
      market_cap_krw: 48_750 * 559_566_880,
      change_code: "5"
    });
  });

  it("keeps preferred share codes that include letters", () => {
    const snapshot = quoteToLatestPriceSnapshot(
      {
        symbol: "00680K",
        summary: { current_price: "20,000" },
        raw: { countOfListedStock: "140,000,000", rf: "2", cr: "1.5" }
      },
      "00680K"
    );

    expect(snapshot).toMatchObject({
      stock_code: "00680K",
      close: 20_000,
      change_rate: 0.015,
      issued_shares: 140_000_000,
      market_cap_krw: 2_800_000_000_000
    });
  });
});
