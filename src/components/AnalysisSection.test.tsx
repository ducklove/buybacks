import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisSection } from "./AnalysisSection";
import type { BuybackEvent, CarCurves, Company, ReactionSeries } from "../types/buybacks";

const companies = [
  {
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    market: "KOSPI",
    sector: null,
    last_updated: "2026-06-20"
  },
  {
    corp_code: "00164742",
    stock_code: "035720",
    corp_name: "카카오",
    market: "KOSDAQ",
    sector: null,
    last_updated: "2026-06-20"
  }
] as Company[];

const events = [
  {
    event_id: "event-1",
    stock_code: "005930",
    event_type: "direct_acquisition",
    disclosure_date: "2026-05-22"
  },
  {
    event_id: "event-2",
    stock_code: "035720",
    event_type: "retirement",
    disclosure_date: "2025-11-03"
  }
] as BuybackEvent[];

const reactionSeries: ReactionSeries[] = [
  {
    event_id: "event-1",
    stock_code: "005930",
    event_date: "2026-05-22",
    t0_date: "2026-05-25",
    daily_return: Array.from({ length: 20 }, () => 0.01),
    daily_abnormal: Array.from({ length: 20 }, () => 0.005),
    data_quality: "complete"
  },
  {
    event_id: "event-2",
    stock_code: "035720",
    event_date: "2025-11-03",
    t0_date: "2025-11-04",
    daily_return: [0.02, -0.01, 0.005, 0.003, 0.001],
    daily_abnormal: [0.015, null, 0.004, 0.002, 0.001],
    data_quality: "partial"
  }
];

const carCurves: CarCurves = {
  window: 60,
  min_events: 5,
  groups: [
    {
      event_type: "direct_acquisition",
      market: "ALL",
      n: 12,
      mean_car: Array.from({ length: 60 }, (_, index) => index * 0.0005)
    },
    {
      event_type: "retirement",
      market: "ALL",
      n: 7,
      mean_car: Array.from({ length: 60 }, (_, index) => (index % 9 === 0 ? null : index * 0.0003))
    },
    {
      event_type: "direct_disposition",
      market: "ALL",
      n: 5,
      mean_car: Array.from({ length: 60 }, (_, index) => -index * 0.0002)
    },
    {
      event_type: "direct_acquisition",
      market: "KOSPI",
      n: 8,
      mean_car: Array.from({ length: 60 }, (_, index) => index * 0.0004)
    }
  ]
};

function renderSection() {
  return render(
    <AnalysisSection
      carCurves={carCurves}
      reactionSeries={reactionSeries}
      events={events}
      companies={companies}
    />
  );
}

function carPanel() {
  return screen.getByText("CAR 곡선").closest("article") as HTMLElement;
}

function backtestPanel() {
  return screen.getByText("간이 백테스트").closest("article") as HTMLElement;
}

describe("AnalysisSection", () => {
  it("renders default CAR curves with legend counts and an accessible chart", () => {
    renderSection();
    const panel = within(carPanel());
    expect(panel.getByRole("img", { name: /누적초과수익률\(CAR\) 곡선/ })).toBeInTheDocument();
    expect(panel.getByText("직접취득 (n=12)")).toBeInTheDocument();
    expect(panel.getByText("소각 (n=7)")).toBeInTheDocument();
    // 기본 선택(직접취득+소각)에 포함되지 않은 유형은 그리지 않는다
    expect(panel.queryByText("직접처분 (n=5)")).not.toBeInTheDocument();
  });

  it("filters CAR groups by market and event type toggles", () => {
    renderSection();
    const panel = within(carPanel());

    fireEvent.click(panel.getByRole("button", { name: "직접처분" }));
    expect(panel.getByText("직접처분 (n=5)")).toBeInTheDocument();

    fireEvent.change(panel.getByLabelText("시장"), { target: { value: "KOSPI" } });
    expect(panel.getByText("직접취득 (n=8)")).toBeInTheDocument();
    expect(panel.queryByText("소각 (n=7)")).not.toBeInTheDocument();

    fireEvent.change(panel.getByLabelText("시장"), { target: { value: "KOSDAQ" } });
    expect(panel.getByText(/선택한 조건에 해당하는 그룹이 없습니다/)).toBeInTheDocument();
  });

  it("computes backtest metrics for the default 20-day holding period", () => {
    renderSection();
    const panel = within(backtestPanel());
    // 20거래일 시계열을 가진 event-1 만 표본에 포함된다 (1.01^20 - 1 ≈ +22.02%)
    expect(panel.getByText("1건")).toBeInTheDocument();
    expect(panel.getAllByText("+22.02%").length).toBeGreaterThan(0);
    expect(panel.getByText("100.0%")).toBeInTheDocument();
    expect(
      panel.getByText(/과거 공시 후 수익률 분포의 요약이며 투자 성과를 보장하지 않습니다/)
    ).toBeInTheDocument();
  });

  it("expands the sample when the holding period shortens and honors the abnormal basis", () => {
    renderSection();
    const panel = within(backtestPanel());

    fireEvent.change(panel.getByLabelText("보유기간"), { target: { value: "5" } });
    expect(panel.getByText("2건")).toBeInTheDocument();

    // 지수대비 기준에서는 null 이 포함된 event-2 가 제외된다
    fireEvent.change(panel.getByLabelText("수익률 기준"), { target: { value: "abnormal" } });
    expect(panel.getByText("1건")).toBeInTheDocument();
    expect(panel.getAllByText("+2.50%").length).toBeGreaterThan(0);
  });

  it("filters the backtest sample by year", () => {
    renderSection();
    const panel = within(backtestPanel());

    fireEvent.change(panel.getByLabelText("보유기간"), { target: { value: "5" } });
    fireEvent.change(panel.getByLabelText("연도"), { target: { value: "2025" } });
    expect(panel.getByText("1건")).toBeInTheDocument();

    fireEvent.change(panel.getByLabelText("연도"), { target: { value: "2026" } });
    expect(panel.getByText("1건")).toBeInTheDocument();
  });
});
