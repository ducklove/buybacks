import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { resetBuybacksDataCache } from "./data/loadBuybacks";

/**
 * 지연 로드 회귀 방어: 첫 렌더(대시보드)는 대형 JSON(reaction_series/car_curves/
 * executions/dividends)을 요청하지 않고, 섹션 진입(IntersectionObserver) 시에만
 * 요청·렌더한다.
 */

const okResponse = (payload: unknown) =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve(payload)
  } as Response);

const notFoundResponse = () =>
  Promise.resolve({
    ok: false,
    status: 404,
    json: () => Promise.resolve(null)
  } as Response);

const serverErrorResponse = () =>
  Promise.resolve({
    ok: false,
    status: 500,
    json: () => Promise.resolve(null)
  } as Response);

const companiesFixture = [
  {
    corp_code: "00126380",
    stock_code: "005930",
    corp_name: "삼성전자",
    market: "KOSPI",
    sector: "반도체",
    last_updated: "2026-06-20"
  }
];

const eventsFixture = [
  {
    event_id: "event-1",
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
    purpose: "주주가치 제고",
    broker: null,
    holding_before_common: null,
    holding_before_ratio_common: null,
    source: "MANUAL",
    rcept_no: null,
    source_url: null,
    raw_report_name: null
  }
];

const latestPricesFixture = [
  {
    stock_code: "005930",
    price_date: "2026-06-19",
    close: 110,
    source: "fixture",
    change_rate: 0.015
  }
];

const executionsFixture = [
  {
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
    linked_event_id: "event-1",
    link_method: "report_date",
    source: "DART",
    rcept_no: "20260825000101",
    source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260825000101",
    raw_report_name: "자기주식취득결과보고서"
  }
];

const reactionSeriesFixture = [
  {
    event_id: "event-1",
    stock_code: "005930",
    event_date: "2026-05-22",
    t0_date: "2026-05-25",
    daily_return: Array.from({ length: 20 }, () => 0.01),
    daily_abnormal: Array.from({ length: 20 }, () => 0.005),
    data_quality: "complete"
  }
];

const statusFixture = {
  generated_at: "2026-06-20T00:00:00+09:00",
  dart_available: false,
  krx_available: false,
  companies_count: 1,
  events_count: 1,
  holdings_count: 0,
  price_reactions_count: 0,
  latest_prices_count: 1,
  warnings: []
};

type Responder = () => Promise<Response>;

function createFetchStub(overrides: Record<string, Responder> = {}) {
  const requestedFiles: string[] = [];
  const defaults: Record<string, Responder> = {
    "companies.json": () => okResponse(companiesFixture),
    "events.json": () => okResponse(eventsFixture),
    "holding_snapshots.json": () => okResponse([]),
    "price_reactions.json": () => okResponse([]),
    "latest_prices.json": () => okResponse(latestPricesFixture),
    "data_status.json": () => okResponse(statusFixture),
    "executions.json": () => okResponse(executionsFixture),
    "reaction_series.json": () => okResponse(reactionSeriesFixture),
    "car_curves.json": () => notFoundResponse(),
    "dividends.json": () => notFoundResponse()
  };
  const stub = (input: RequestInfo | URL) => {
    const url = String(input);
    const fileName = url.split("/").pop() ?? url;
    requestedFiles.push(fileName);
    const responder = overrides[fileName] ?? defaults[fileName];
    return responder ? responder() : notFoundResponse();
  };
  return { requestedFiles, stub };
}

/** 테스트에서 진입 시점을 제어할 수 있는 IntersectionObserver 목 */
class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  private readonly callback: IntersectionObserverCallback;
  private readonly elements = new Set<Element>();

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instances.push(this);
  }

  observe(element: Element) {
    this.elements.add(element);
  }

  unobserve(element: Element) {
    this.elements.delete(element);
  }

  disconnect() {
    this.elements.clear();
  }

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  /** 관찰 중인 모든 요소를 뷰포트에 진입한 것으로 처리한다 */
  static enterAll() {
    MockIntersectionObserver.instances.forEach((instance) => {
      const entries = Array.from(instance.elements, (target) => {
        return { isIntersecting: true, target } as IntersectionObserverEntry;
      });
      if (entries.length > 0) {
        instance.callback(entries, instance as unknown as IntersectionObserver);
      }
    });
  }
}

describe("App lazy loading", () => {
  beforeEach(() => {
    resetBuybacksDataCache();
    MockIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not request the heavy JSON files on first render", async () => {
    const { requestedFiles, stub } = createFetchStub();
    vi.stubGlobal("fetch", stub);

    render(<App />);
    expect(await screen.findByText("자사주 매입·처분·소각 분석")).toBeInTheDocument();

    // 코어 데이터만 요청한다
    expect(requestedFiles).toEqual(
      expect.arrayContaining([
        "companies.json",
        "events.json",
        "holding_snapshots.json",
        "price_reactions.json",
        "latest_prices.json",
        "data_status.json"
      ])
    );
    for (const heavy of [
      "reaction_series.json",
      "car_curves.json",
      "executions.json",
      "dividends.json"
    ]) {
      expect(requestedFiles).not.toContain(heavy);
    }
    // 분석 섹션 자리는 기존 loading-panel 패턴으로 표시된다
    expect(screen.getByText("분석 데이터를 불러오는 중입니다.")).toBeInTheDocument();
  });

  it("loads and renders the analysis/detail data when their sections come into view", { timeout: 30000 }, async () => {
    const { requestedFiles, stub } = createFetchStub();
    vi.stubGlobal("fetch", stub);

    render(<App />);
    expect(await screen.findByText("자사주 매입·처분·소각 분석")).toBeInTheDocument();

    await act(async () => {
      MockIntersectionObserver.enterAll();
    });

    // CI 러너는 로컬보다 느려 기본 1초 대기로는 지연 로드 → 파싱 → 재렌더
    // 체인이 끝나지 않을 수 있다(29142680322 실패). 넉넉히 기다린다.
    const findOpts = { timeout: 10000 } as const;
    // 백테스트 패널: 20거래일 × 1% 복리 → +22.02%
    expect((await screen.findAllByText("+22.02%", undefined, findOpts)).length).toBeGreaterThan(0);
    // 이행결과: 998400000000 / 1000000000000 → 99.8%
    expect((await screen.findAllByText("99.8%", undefined, findOpts)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("완료").length).toBeGreaterThan(0);

    for (const lazy of [
      "reaction_series.json",
      "car_curves.json",
      "executions.json",
      "dividends.json"
    ]) {
      expect(requestedFiles).toContain(lazy);
    }
  });

  it("shows the error pattern when the analysis load fails and recovers on retry", async () => {
    let failNextReactionSeries = true;
    const { stub } = createFetchStub({
      "reaction_series.json": () => {
        if (failNextReactionSeries) {
          failNextReactionSeries = false;
          return serverErrorResponse();
        }
        return okResponse(reactionSeriesFixture);
      }
    });
    vi.stubGlobal("fetch", stub);

    render(<App />);
    expect(await screen.findByText("자사주 매입·처분·소각 분석")).toBeInTheDocument();

    await act(async () => {
      MockIntersectionObserver.enterAll();
    });

    expect(await screen.findByText("분석 데이터를 불러오지 못했습니다.")).toBeInTheDocument();
    expect(
      screen.getByText(/reaction_series\.json 파일을 불러오지 못했습니다 \(HTTP 500\)/)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect((await screen.findAllByText("+22.02%")).length).toBeGreaterThan(0);
  });
});
