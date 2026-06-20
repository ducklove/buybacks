import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS, filterEvents } from "./metrics";
import type { EnrichedEvent, EventType } from "../types/buybacks";

const event = (event_id: string, event_type: EventType): EnrichedEvent => ({
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
  }
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
