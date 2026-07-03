import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

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

describe("App", () => {
  it("renders the primary dashboard after static JSON loads", async () => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("companies.json")) {
        return okResponse([
          {
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            market: "KOSPI",
            sector: "반도체",
            last_updated: "2026-06-20"
          }
        ]);
      }
      if (url.endsWith("events.json")) {
        return okResponse([
          {
            event_id: "event-1",
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            event_type: "direct_acquisition",
            disclosure_date: "2026-05-22",
            decision_date: "2026-05-22",
            period_start: null,
            period_end: null,
            planned_shares_common: 10,
            planned_shares_other: 3,
            planned_amount_krw: 1000,
            planned_amount_common_krw: 700,
            planned_amount_other_krw: 300,
            planned_share_ratio_common: null,
            planned_share_ratio_other: null,
            actual_shares: null,
            actual_amount_krw: null,
            method: null,
            purpose: "주주가치 제고",
            broker: null,
            holding_before_common: null,
            holding_before_ratio_common: null,
            source: "MANUAL",
            rcept_no: null,
            source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260522000001",
            raw_report_name: null
          }
        ]);
      }
      if (url.endsWith("holding_snapshots.json")) {
        return okResponse([
          {
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            as_of_date: "2025-12-31",
            report_year: 2025,
            report_code: "11011",
            stock_kind: "보통주",
            beginning_qty: 1,
            acquired_qty: 1,
            disposed_qty: 0,
            retired_qty: 0,
            ending_qty: 2,
            issued_shares: 100,
            treasury_ratio: 0.02,
            floating_shares: 98,
            source_rcept_no: null
          }
        ]);
      }
      if (url.endsWith("price_reactions.json")) {
        return okResponse([
          {
            event_id: "event-1",
            stock_code: "005930",
            event_date: "2026-05-22",
            close_t0: 100,
            return_1d: 0.01,
            return_5d: 0.02,
            return_20d: 0.03,
            return_60d: null,
            max_drawdown_20d: -0.01,
            max_drawdown_60d: null,
            market_return_20d: 0.01,
            abnormal_return_20d: 0.02,
            volume_change_20d: 0.1,
            data_quality: "partial"
          }
        ]);
      }
      if (url.endsWith("latest_prices.json")) {
        return okResponse([
          {
            stock_code: "005930",
            price_date: "2026-06-19",
            close: 110,
            source: "fixture",
            change_rate: 0.015
          }
        ]);
      }
      if (
        url.endsWith("executions.json") ||
        url.endsWith("reaction_series.json") ||
        url.endsWith("car_curves.json")
      ) {
        return notFoundResponse();
      }
      return okResponse({
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 1,
        events_count: 1,
        holdings_count: 1,
        price_reactions_count: 1,
        latest_prices_count: 1,
        warnings: []
      });
    });

    render(<App />);
    expect(await screen.findByText("자사주 매입·처분·소각 분석")).toBeInTheDocument();
    expect(screen.getByText("이벤트 탐색기")).toBeInTheDocument();
    expect(screen.getAllByText("삼성전자").length).toBeGreaterThan(0);
    expect(screen.getByText("기보유비율")).toBeInTheDocument();
    expect(screen.getByText("예정지분")).toBeInTheDocument();
    expect(screen.getAllByText("9.09%").length).toBeGreaterThan(0);
    expect(screen.getByText("110")).toBeInTheDocument();
    expect(screen.getByText("△ +1.50%")).toBeInTheDocument();
    expect(screen.queryByText("현재가")).not.toBeInTheDocument();
    expect(screen.getByText("공시 목록")).toBeInTheDocument();
    expect(screen.getByText(/예정주식수 보통 10 \/ 기타 3/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "원문" })).toHaveAttribute(
      "href",
      "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260522000001"
    );
    expect(screen.queryByText("최근 예정금액")).not.toBeInTheDocument();
    expect(screen.queryByText("공시 후 가격 반응")).not.toBeInTheDocument();
  });

  it("shows execution completion rate, status badge, and unlinked reports when executions.json is present", async () => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("companies.json")) {
        return okResponse([
          {
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            market: "KOSPI",
            sector: "반도체",
            last_updated: "2026-06-20"
          }
        ]);
      }
      if (url.endsWith("events.json")) {
        return okResponse([
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
        ]);
      }
      if (url.endsWith("holding_snapshots.json")) {
        return okResponse([]);
      }
      if (url.endsWith("price_reactions.json")) {
        return okResponse([]);
      }
      if (
        url.endsWith("latest_prices.json") ||
        url.endsWith("reaction_series.json") ||
        url.endsWith("car_curves.json")
      ) {
        return notFoundResponse();
      }
      if (url.endsWith("executions.json")) {
        return okResponse([
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
          },
          {
            execution_id: "exec-2",
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            execution_type: "acquisition_result",
            disclosure_date: "2026-04-13",
            origin_report_date: "2026-01-09",
            period_start: "2026-01-12",
            period_end: "2026-04-10",
            ordered_shares: 1250000,
            actual_shares: 1180000,
            actual_amount_krw: 236590000000,
            avg_price_krw: 200500,
            planned_amount_krw: 240000000000,
            planned_shares: null,
            shortfall: true,
            shortfall_reason: "취득기간 중 주가 상승으로 취득예정금액에 미달",
            holding_after_qty: 4680000,
            holding_after_ratio: 0.0064,
            trust_contract_amount_krw: null,
            trust_progress_ratio: null,
            as_of_date: "2026-04-13",
            linked_event_id: null,
            link_method: "unlinked",
            source: "DART",
            rcept_no: "20260413000404",
            source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260413000404",
            raw_report_name: "[기재정정]자기주식취득결과보고서"
          }
        ]);
      }
      return okResponse({
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 1,
        events_count: 1,
        holdings_count: 0,
        price_reactions_count: 0,
        latest_prices_count: 0,
        warnings: []
      });
    });

    render(<App />);
    expect(await screen.findByText("이벤트 탐색기")).toBeInTheDocument();
    expect(screen.getByText("이행률")).toBeInTheDocument();
    expect(screen.getAllByText("99.8%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("완료").length).toBeGreaterThan(0);
    expect(screen.getByText("미연결 결과보고서")).toBeInTheDocument();
    expect(screen.getByText("미달")).toBeInTheDocument();
  });

  it("renders the analysis section as empty states when reaction_series and car_curves are absent", async () => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("companies.json")) {
        return okResponse([
          {
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            market: "KOSPI",
            sector: "반도체",
            last_updated: "2026-06-20"
          }
        ]);
      }
      if (url.endsWith("events.json")) {
        return okResponse([
          {
            event_id: "event-1",
            corp_code: "00126380",
            stock_code: "005930",
            corp_name: "삼성전자",
            event_type: "direct_acquisition",
            disclosure_date: "2026-05-22",
            decision_date: "2026-05-22",
            period_start: null,
            period_end: null,
            planned_shares_common: 10,
            planned_shares_other: null,
            planned_amount_krw: 1000,
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
            raw_report_name: null
          }
        ]);
      }
      if (url.endsWith("holding_snapshots.json") || url.endsWith("price_reactions.json")) {
        return okResponse([]);
      }
      if (
        url.endsWith("latest_prices.json") ||
        url.endsWith("executions.json") ||
        url.endsWith("reaction_series.json") ||
        url.endsWith("car_curves.json")
      ) {
        return notFoundResponse();
      }
      return okResponse({
        generated_at: "2026-06-20T00:00:00+09:00",
        dart_available: false,
        krx_available: false,
        companies_count: 1,
        events_count: 1,
        holdings_count: 0,
        price_reactions_count: 0,
        warnings: []
      });
    });

    render(<App />);
    expect(await screen.findByText("자사주 매입·처분·소각 분석")).toBeInTheDocument();
    // 분석 섹션과 네비게이션은 데이터 부재 시에도 렌더된다
    expect(screen.getByRole("button", { name: "분석" })).toBeInTheDocument();
    expect(screen.getByText("CAR 곡선")).toBeInTheDocument();
    expect(screen.getByText("간이 백테스트")).toBeInTheDocument();
    expect(screen.getAllByText(/가격 시계열 보강 후 표시됩니다/)).toHaveLength(2);
    // 나머지 대시보드는 기존과 동일하게 동작한다
    expect(screen.getByText("이벤트 탐색기")).toBeInTheDocument();
    expect(screen.getAllByText("삼성전자").length).toBeGreaterThan(0);
  });
});
