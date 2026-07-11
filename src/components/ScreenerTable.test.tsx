import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenerTable } from "./ScreenerTable";
import type { EnrichedEvent } from "../types/buybacks";

function makeEvent(index: number, corpName: string): EnrichedEvent {
  const code = String(index).padStart(6, "0");
  const day = String((index % 27) + 1).padStart(2, "0");
  return {
    event_id: `event-${index}`,
    corp_code: `corp-${index}`,
    stock_code: code,
    corp_name: corpName,
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

function companyNames(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("tbody td.company-cell .link-button")).map(
    (button) => button.childNodes[0]?.textContent ?? ""
  );
}

describe("ScreenerTable", () => {
  const events = [makeEvent(1, "다니엘"), makeEvent(2, "가나다"), makeEvent(3, "나비스")];

  it("카드 모드 마크업 계약: 셀 data-label 라벨과 company-cell 종목 셀을 제공한다", () => {
    const { container } = render(
      <ScreenerTable events={events} selectedStockCode="" onSelectStock={vi.fn()} />
    );

    // ≤760px CSS 카드 모드는 section.card-table 로 옵트인한다.
    expect(container.querySelector("section.table-panel.card-table#screener")).not.toBeNull();

    const firstRow = container.querySelector("tbody tr");
    const labels = Array.from(firstRow?.querySelectorAll("td[data-label]") ?? []).map((cell) =>
      cell.getAttribute("data-label")
    );
    expect(labels).toEqual([
      "시장",
      "이벤트 수",
      "12M 취득계획",
      "시총대비 %",
      "배당수익률 %",
      "총환원율 %",
      "소각비중 %",
      "평균 이행률 %",
      "보유비율 %",
      "최근 이벤트일"
    ]);

    const companyCell = firstRow?.querySelector("td.company-cell");
    expect(companyCell?.hasAttribute("data-label")).toBe(false);
    expect(companyCell?.querySelector(".link-button")).not.toBeNull();
  });

  it("data-label 추가 후에도 종목 정렬 토글 동작이 유지된다", () => {
    const { container } = render(
      <ScreenerTable events={events} selectedStockCode="" onSelectStock={vi.fn()} />
    );

    const companySort = screen.getByRole("button", { name: /종목/ });

    fireEvent.click(companySort);
    expect(companyNames(container)).toEqual(["다니엘", "나비스", "가나다"]);

    fireEvent.click(companySort);
    expect(companyNames(container)).toEqual(["가나다", "나비스", "다니엘"]);
  });

  it("선택된 종목 행은 selected-row 로 강조된다", () => {
    const { container } = render(
      <ScreenerTable events={events} selectedStockCode="000002" onSelectStock={vi.fn()} />
    );

    const selected = container.querySelector("tbody tr.selected-row");
    expect(selected?.textContent).toContain("가나다");
  });
});
