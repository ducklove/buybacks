import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EventTable } from "./EventTable";
import type { EnrichedEvent } from "../types/buybacks";

function makeEvent(index: number): EnrichedEvent {
  const code = String(index).padStart(6, "0");
  const day = String(index).padStart(2, "0");
  return {
    event_id: `event-${index}`,
    corp_code: `corp-${index}`,
    stock_code: code,
    corp_name: `회사 ${index}`,
    event_type: "direct_acquisition",
    disclosure_date: `2026-06-${day}`,
    decision_date: null,
    period_start: null,
    period_end: null,
    planned_shares_common: index * 100,
    planned_shares_other: null,
    planned_amount_krw: index * 1000,
    planned_amount_common_krw: null,
    planned_amount_other_krw: null,
    planned_share_ratio_common: null,
    planned_share_ratio_other: null,
    actual_shares: null,
    actual_amount_krw: null,
    method: null,
    purpose: null,
    broker: null,
    holding_before_common: null,
    holding_before_ratio_common: null,
    source: "DART",
    rcept_no: null,
    source_url: null,
    raw_report_name: null
  };
}

describe("EventTable", () => {
  const events = Array.from({ length: 30 }, (_, index) => makeEvent(index + 1));

  it("paginates event rows and can move to the next page", () => {
    const { container } = render(
      <EventTable events={events} selectedStockCode="" onSelectStock={vi.fn()} />
    );

    expect(container.querySelectorAll("tbody tr")).toHaveLength(25);
    expect(screen.getByText("1-25 / 30건")).toBeInTheDocument();
    expect(screen.getByText("회사 30")).toBeInTheDocument();
    expect(screen.queryByText("회사 5")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "다음 페이지" }));

    expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
    expect(screen.getByText("26-30 / 30건")).toBeInTheDocument();
    expect(screen.getByText("회사 5")).toBeInTheDocument();
  });

  it("changes page size", () => {
    const { container } = render(
      <EventTable events={events} selectedStockCode="" onSelectStock={vi.fn()} />
    );

    fireEvent.change(screen.getByLabelText("페이지당"), { target: { value: "50" } });

    expect(container.querySelectorAll("tbody tr")).toHaveLength(30);
    expect(screen.getByText("1-30 / 30건")).toBeInTheDocument();
  });

  it("카드 모드 마크업 계약: 셀 data-label 라벨과 company-cell 종목 셀을 제공한다", () => {
    const { container } = render(
      <EventTable events={events} selectedStockCode="" onSelectStock={vi.fn()} />
    );

    // ≤760px CSS 카드 모드는 section.card-table 로 옵트인한다.
    expect(container.querySelector("section.table-panel.card-table#events")).not.toBeNull();

    const firstRow = container.querySelector("tbody tr");
    const labels = Array.from(firstRow?.querySelectorAll("td[data-label]") ?? []).map((cell) =>
      cell.getAttribute("data-label")
    );
    expect(labels).toEqual([
      "공시일",
      "유형",
      "예정금액",
      "예정주식수",
      "예정지분",
      "목적",
      "기보유비율",
      "시가총액",
      "이행률"
    ]);

    // 종목 셀은 카드 타이틀 역할 — 라벨 없이 company-cell 클래스로 전폭 배치된다.
    const companyCell = firstRow?.querySelector("td.company-cell");
    expect(companyCell?.hasAttribute("data-label")).toBe(false);
    expect(companyCell?.querySelector(".link-button")).not.toBeNull();
  });
});
