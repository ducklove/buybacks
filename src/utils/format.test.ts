import { describe, expect, it } from "vitest";
import { formatKRW } from "./format";

describe("formatKRW", () => {
  it("formats amounts in hundred-million KRW units", () => {
    expect(formatKRW(86_829_000)).toBe("0.87억");
    expect(formatKRW(200_000_000_000)).toBe("2,000억");
  });
});
