import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

const okResponse = (payload: unknown) =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve(payload)
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
            planned_shares_other: null,
            planned_amount_krw: 1000,
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
            source: "fixture"
          }
        ]);
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
  });
});
