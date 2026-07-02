import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS } from "./metrics";
import { parseAppStateFromSearch, serializeAppState } from "./urlState";

describe("parseAppStateFromSearch", () => {
  it("returns defaults for an empty query string", () => {
    expect(parseAppStateFromSearch("")).toEqual({
      filters: DEFAULT_FILTERS,
      selectedStockCode: null
    });
  });

  it("restores every filter and the selected stock from the query", () => {
    const state = parseAppStateFromSearch(
      "?market=KOSDAQ&types=direct_acquisition,retirement&year=2025&search=%EC%82%BC%EC%84%B1&stock=005930"
    );

    expect(state).toEqual({
      filters: {
        market: "KOSDAQ",
        eventTypes: ["direct_acquisition", "retirement"],
        year: "2025",
        search: "삼성"
      },
      selectedStockCode: "005930"
    });
  });

  it("falls back to defaults for invalid market and year values", () => {
    const state = parseAppStateFromSearch("?market=NASDAQ&year=20xx");

    expect(state.filters.market).toBe(DEFAULT_FILTERS.market);
    expect(state.filters.year).toBe(DEFAULT_FILTERS.year);
  });

  it("keeps only allowed event type literals and deduplicates them", () => {
    const state = parseAppStateFromSearch(
      "?types=retirement,bogus,retirement,%20direct_disposition%20,DROP%20TABLE"
    );

    expect(state.filters.eventTypes).toEqual(["retirement", "direct_disposition"]);
  });

  it("returns an empty event type list for a query of only invalid values", () => {
    expect(parseAppStateFromSearch("?types=foo,bar").filters.eventTypes).toEqual([]);
  });

  it("normalizes stock codes to uppercase and rejects malformed ones", () => {
    expect(parseAppStateFromSearch("?stock=00680k").selectedStockCode).toBe("00680K");
    expect(parseAppStateFromSearch("?stock=1234").selectedStockCode).toBeNull();
    expect(parseAppStateFromSearch("?stock=%3Cscript%3E").selectedStockCode).toBeNull();
  });
});

describe("serializeAppState", () => {
  it("produces an empty string when everything is at its default", () => {
    expect(serializeAppState(DEFAULT_FILTERS, "005930", "005930")).toBe("");
  });

  it("omits the stock parameter when it matches the default stock code", () => {
    const query = serializeAppState({ ...DEFAULT_FILTERS, year: "2026" }, "005930", "005930");

    expect(query).toBe("?year=2026");
  });

  it("serializes non-default filters and a non-default stock", () => {
    const query = serializeAppState(
      {
        market: "KOSPI",
        eventTypes: ["direct_acquisition", "retirement"],
        year: "2025",
        search: "삼성"
      },
      "006800",
      "005930"
    );
    const params = new URLSearchParams(query);

    expect(params.get("market")).toBe("KOSPI");
    expect(params.get("types")).toBe("direct_acquisition,retirement");
    expect(params.get("year")).toBe("2025");
    expect(params.get("search")).toBe("삼성");
    expect(params.get("stock")).toBe("006800");
  });

  it("omits whitespace-only search terms", () => {
    expect(serializeAppState({ ...DEFAULT_FILTERS, search: "   " }, "", "")).toBe("");
  });

  it("round-trips through parseAppStateFromSearch", () => {
    const filters = {
      market: "KOSDAQ" as const,
      eventTypes: ["trust_contract_start" as const],
      year: "2024",
      search: "한화 3"
    };
    const query = serializeAppState(filters, "00680K", "005930");

    expect(parseAppStateFromSearch(query)).toEqual({
      filters,
      selectedStockCode: "00680K"
    });
  });
});
