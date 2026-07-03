import { describe, expect, it } from "vitest";
import {
  completionRate,
  executionStatus,
  mapExecutionsByEvent,
  pickRepresentativeExecution,
  unlinkedExecutionsForStock
} from "./executions";
import type { BuybackEvent, BuybackExecution } from "../types/buybacks";

function makeExecution(overrides: Partial<BuybackExecution> = {}): BuybackExecution {
  return {
    execution_id: "exec-1",
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    execution_type: "acquisition_result",
    disclosure_date: "2026-08-25",
    origin_report_date: "2026-05-22",
    period_start: "2026-05-23",
    period_end: "2026-08-22",
    ordered_shares: 13100000,
    actual_shares: 12480000,
    actual_amount_krw: 998400000000,
    avg_price_krw: 80000,
    planned_amount_krw: 1000000000000,
    planned_shares: null,
    shortfall: false,
    shortfall_reason: null,
    holding_after_qty: 160480000,
    holding_after_ratio: 0.0269,
    trust_contract_amount_krw: null,
    trust_progress_ratio: null,
    as_of_date: "2026-08-25",
    linked_event_id: "fixture-005930-2026-05-22-acq",
    link_method: "report_date",
    source: "DART",
    rcept_no: "20260825000101",
    source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260825000101",
    raw_report_name: "자기주식취득결과보고서",
    ...overrides
  };
}

function makeEvent(overrides: Partial<BuybackEvent> = {}): BuybackEvent {
  return {
    event_id: "fixture-005930-2026-05-22-acq",
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    event_type: "direct_acquisition",
    disclosure_date: "2026-05-22",
    decision_date: "2026-05-22",
    period_start: "2026-05-23",
    period_end: "2026-08-22",
    planned_shares_common: 12500000,
    planned_shares_other: null,
    planned_amount_krw: 1000000000000,
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
    ...overrides
  };
}

describe("pickRepresentativeExecution", () => {
  it("returns undefined when no execution links to the event", () => {
    const executions = [makeExecution({ linked_event_id: "other-event" })];
    expect(pickRepresentativeExecution("event-1", executions)).toBeUndefined();
  });

  it("ignores unlinked executions", () => {
    const executions = [makeExecution({ linked_event_id: null })];
    expect(
      pickRepresentativeExecution("fixture-005930-2026-05-22-acq", executions)
    ).toBeUndefined();
  });

  it("picks the latest disclosure_date for non-trust executions (corrections)", () => {
    const original = makeExecution({
      execution_id: "exec-original",
      disclosure_date: "2026-08-10",
      raw_report_name: "자기주식취득결과보고서"
    });
    const correction = makeExecution({
      execution_id: "exec-correction",
      disclosure_date: "2026-08-25",
      raw_report_name: "[기재정정]자기주식취득결과보고서"
    });

    const picked = pickRepresentativeExecution("fixture-005930-2026-05-22-acq", [
      original,
      correction
    ]);
    expect(picked?.execution_id).toBe("exec-correction");
  });

  it("picks the latest as_of_date among trust executions instead of summing them", () => {
    const early = makeExecution({
      execution_id: "trust-early",
      execution_type: "trust_status",
      as_of_date: "2026-05-29",
      trust_progress_ratio: 0.1,
      actual_amount_krw: 15000000000
    });
    const late = makeExecution({
      execution_id: "trust-late",
      execution_type: "trust_status",
      as_of_date: "2026-07-29",
      trust_progress_ratio: 0.3234,
      actual_amount_krw: 48510000000
    });

    const picked = pickRepresentativeExecution("fixture-005930-2026-05-22-acq", [early, late]);
    expect(picked?.execution_id).toBe("trust-late");
  });
});

describe("mapExecutionsByEvent", () => {
  it("groups by linked_event_id and keeps only representative executions", () => {
    const eventA1 = makeExecution({
      execution_id: "a-1",
      linked_event_id: "event-a",
      disclosure_date: "2026-08-01"
    });
    const eventA2 = makeExecution({
      execution_id: "a-2",
      linked_event_id: "event-a",
      disclosure_date: "2026-08-10"
    });
    const eventB = makeExecution({ execution_id: "b-1", linked_event_id: "event-b" });
    const unlinked = makeExecution({ execution_id: "u-1", linked_event_id: null });

    const map = mapExecutionsByEvent([eventA1, eventA2, eventB, unlinked]);

    expect(map.size).toBe(2);
    expect(map.get("event-a")?.execution_id).toBe("a-2");
    expect(map.get("event-b")?.execution_id).toBe("b-1");
    expect(map.has("undefined" as string)).toBe(false);
  });
});

describe("completionRate", () => {
  it("prioritizes share-count completion even when amount falls short", () => {
    const event = makeEvent({ planned_shares_common: 100, planned_amount_krw: 1000 });
    const execution = makeExecution({
      actual_shares: 100,
      actual_amount_krw: 700,
      planned_amount_krw: 1000
    });

    expect(completionRate(event, execution)).toBe(1);
  });

  it("falls back to amount ratio when share counts are unavailable", () => {
    const event = makeEvent({ planned_shares_common: null, planned_amount_krw: null });
    const execution = makeExecution({
      actual_shares: null,
      actual_amount_krw: 29988000000,
      planned_amount_krw: null,
      planned_shares: 180000
    });
    // execution.planned_amount_krw is null too, so no ratio can be derived from amount either.
    expect(completionRate(event, execution)).toBeNull();
  });

  it("falls back to the event's planned amount, then the execution's own planned amount", () => {
    const eventWithPlan = makeEvent({
      planned_shares_common: null,
      planned_amount_krw: 30000000000
    });
    const execution = makeExecution({
      actual_shares: null,
      actual_amount_krw: 29988000000,
      planned_amount_krw: null
    });
    expect(completionRate(eventWithPlan, execution)).toBeCloseTo(29988000000 / 30000000000);

    const eventWithoutPlan = makeEvent({ planned_shares_common: null, planned_amount_krw: null });
    const executionWithOwnPlan = makeExecution({
      actual_shares: null,
      actual_amount_krw: 29988000000,
      planned_amount_krw: 30000000000
    });
    expect(completionRate(eventWithoutPlan, executionWithOwnPlan)).toBeCloseTo(
      29988000000 / 30000000000
    );
  });

  it("uses trust_progress_ratio directly for trust executions and ignores share/amount fields", () => {
    const event = makeEvent({ planned_shares_common: 620000, planned_amount_krw: 150000000000 });
    const execution = makeExecution({
      execution_type: "trust_status",
      actual_shares: 231000,
      actual_amount_krw: 48510000000,
      trust_progress_ratio: 0.3234
    });

    expect(completionRate(event, execution)).toBe(0.3234);
  });

  it("returns null when there is no execution", () => {
    expect(completionRate(makeEvent(), undefined)).toBeNull();
  });
});

describe("executionStatus", () => {
  it("returns null status when there is no execution yet", () => {
    expect(executionStatus(undefined)).toEqual({ status: null, reason: null });
  });

  it("reports 완료 when shortfall is false", () => {
    const execution = makeExecution({ shortfall: false });
    expect(executionStatus(execution)).toEqual({ status: "완료", reason: null });
  });

  it("reports 미달 with the shortfall reason when shortfall is true", () => {
    const execution = makeExecution({
      shortfall: true,
      shortfall_reason: "취득기간 중 주가 상승으로 취득예정금액에 미달"
    });
    expect(executionStatus(execution)).toEqual({
      status: "미달",
      reason: "취득기간 중 주가 상승으로 취득예정금액에 미달"
    });
  });

  it("reports 진행중 for trust_status executions regardless of shortfall", () => {
    const execution = makeExecution({ execution_type: "trust_status", shortfall: null });
    expect(executionStatus(execution)).toEqual({ status: "진행중", reason: null });
  });

  it("returns null status when shortfall cannot be determined", () => {
    const execution = makeExecution({ shortfall: null });
    expect(executionStatus(execution)).toEqual({ status: null, reason: null });
  });
});

describe("unlinkedExecutionsForStock", () => {
  it("keeps only unlinked executions for the given stock code", () => {
    const executions = [
      makeExecution({ execution_id: "linked", stock_code: "000660", linked_event_id: "e1" }),
      makeExecution({
        execution_id: "unlinked-match",
        stock_code: "000660",
        linked_event_id: null
      }),
      makeExecution({ execution_id: "unlinked-other", stock_code: "005930", linked_event_id: null })
    ];

    const result = unlinkedExecutionsForStock(executions, "000660");
    expect(result.map((execution) => execution.execution_id)).toEqual(["unlinked-match"]);
  });
});
