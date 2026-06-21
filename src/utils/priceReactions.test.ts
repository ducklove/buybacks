import { describe, expect, it } from "vitest";
import {
  displayReactionValue,
  displayRelativeReaction,
  displaySimpleReaction
} from "./priceReactions";
import type { PriceReaction } from "../types/buybacks";

const reaction: PriceReaction = {
  event_id: "event-1",
  stock_code: "005930",
  event_date: "2026-05-22",
  close_t0: 100,
  return_1d: 0.01,
  return_5d: 0.03,
  return_20d: 0.05,
  return_60d: null,
  max_drawdown_20d: null,
  max_drawdown_60d: null,
  market_return_20d: 0.02,
  abnormal_return_20d: 0.03,
  volume_change_20d: null,
  data_quality: "partial"
};

describe("price reaction display helpers", () => {
  it("uses index-relative return as the representative value", () => {
    expect(displayRelativeReaction(reaction)).toMatchObject({
      label: "지수대비 +20D",
      value: 0.03
    });
    expect(displayReactionValue(reaction)).toBe(0.03);
  });

  it("keeps the simple return available for secondary display", () => {
    expect(displaySimpleReaction(reaction)).toMatchObject({
      label: "+20D",
      value: 0.05
    });
  });
});
