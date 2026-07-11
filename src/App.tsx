import { useEffect, useMemo, useState } from "react";
import { LazyAnalysisSection } from "./components/AnalysisSection";
import { CompanyDetail } from "./components/CompanyDetail";
import { DashboardCharts } from "./components/DashboardCharts";
import { DataStatusBanner } from "./components/DataStatusBanner";
import { EventTable } from "./components/EventTable";
import { FilterBar } from "./components/FilterBar";
import { KpiGrid } from "./components/KpiGrid";
import { Methodology } from "./components/Methodology";
import { ScreenerTable } from "./components/ScreenerTable";
import { Shell } from "./components/Shell";
import { loadBuybacksDataset, loadDetailDataset, type DetailDataset } from "./data/loadBuybacks";
import { useVisibleOnce } from "./hooks/useVisibleOnce";
import {
  availableYears,
  buildKpis,
  enrichEvents,
  filterEvents,
  latestHoldingSnapshots
} from "./utils/metrics";
import { parseAppStateFromSearch, serializeAppState } from "./utils/urlState";
import type { BuybacksDataset, Filters } from "./types/buybacks";

function currentLocationSearch() {
  return typeof window === "undefined" ? "" : window.location.search;
}

function App() {
  const [initialUrlState] = useState(() => parseAppStateFromSearch(currentLocationSearch()));
  const [dataset, setDataset] = useState<BuybacksDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(initialUrlState.filters);
  const [selectedStockCode, setSelectedStockCode] = useState<string>(
    initialUrlState.selectedStockCode ?? ""
  );
  // 이행결과(executions)·배당(dividends)은 이벤트 테이블/상세 섹션 접근 시 지연 로드한다.
  // sentinel div 는 코어 데이터셋 로드 후에야 렌더되므로 그때부터 관찰을 시작한다.
  const { ref: detailGateRef, visible: detailGateVisible } = useVisibleOnce<HTMLDivElement>(
    "800px 0px",
    dataset !== null
  );
  const [detailData, setDetailData] = useState<DetailDataset | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadBuybacksDataset()
      .then((loaded) => {
        if (cancelled) return;
        setDataset(loaded);
        setSelectedStockCode((current) =>
          current && loaded.companies.some((company) => company.stock_code === current)
            ? current
            : (loaded.companies[0]?.stock_code ?? "")
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!dataset || !detailGateVisible || detailData || detailError) return;
    let cancelled = false;
    const knownEventIds = new Set(dataset.events.map((event) => event.event_id));
    loadDetailDataset(knownEventIds)
      .then((loaded) => {
        if (!cancelled) setDetailData(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [dataset, detailGateVisible, detailData, detailError]);

  useEffect(() => {
    if (!dataset || typeof window === "undefined") return;
    const nextSearch = serializeAppState(
      filters,
      selectedStockCode,
      dataset.companies[0]?.stock_code ?? ""
    );
    const { pathname, search, hash } = window.location;
    if (nextSearch === search) return;
    window.history.replaceState(window.history.state, "", `${pathname}${nextSearch}${hash}`);
  }, [dataset, filters, selectedStockCode]);

  const enrichedEvents = useMemo(
    () =>
      dataset
        ? enrichEvents({
            ...dataset,
            executions: detailData?.executions ?? [],
            dividends: detailData?.dividends ?? []
          })
        : [],
    [dataset, detailData]
  );
  const filteredEvents = useMemo(
    () => filterEvents(enrichedEvents, filters),
    [enrichedEvents, filters]
  );
  const years = useMemo(() => availableYears(enrichedEvents), [enrichedEvents]);
  const latestHoldings = useMemo(
    () => (dataset ? latestHoldingSnapshots(dataset.holdingSnapshots) : []),
    [dataset]
  );
  const filteredPriceReactions = useMemo(() => {
    if (!dataset) return [];
    const eventIds = new Set(filteredEvents.map((event) => event.event_id));
    return dataset.priceReactions.filter((reaction) => eventIds.has(reaction.event_id));
  }, [dataset, filteredEvents]);
  const kpis = useMemo(
    () => buildKpis(filteredEvents, latestHoldings),
    [filteredEvents, latestHoldings]
  );

  if (error) {
    return (
      <Shell>
        <main className="app-main">
          <section className="empty-state" role="alert">
            <h1>데이터를 불러오지 못했습니다</h1>
            <p>
              네트워크 연결을 확인한 뒤 다시 시도해 주세요. 문제가 계속되면 데이터 파이프라인 점검이
              필요할 수 있습니다.
            </p>
            <p className="muted">{error}</p>
            <button
              className="secondary-button"
              type="button"
              onClick={() => window.location.reload()}
            >
              다시 시도
            </button>
          </section>
        </main>
      </Shell>
    );
  }

  if (!dataset) {
    return (
      <Shell>
        <main className="app-main">
          <section className="loading-panel" aria-live="polite">
            <div className="loading-bar" />
            <p>정적 데이터셋을 불러오는 중입니다.</p>
          </section>
        </main>
      </Shell>
    );
  }

  return (
    <Shell>
      <main className="app-main">
        <section className="page-title" id="dashboard">
          <div>
            <h1>자사주 매입·처분·소각 분석</h1>
            <p>
              OpenDART 공시와 kis_proxy 가격 데이터를 정적 JSON으로 정규화해 보유 현황, 이벤트, 공시
              후 주가 흐름을 함께 살펴봅니다.
            </p>
          </div>
          <DataStatusBanner status={dataset.status} />
        </section>

        <FilterBar filters={filters} years={years} onChange={setFilters} />

        <KpiGrid metrics={kpis} />

        <DashboardCharts
          events={filteredEvents}
          holdings={latestHoldings}
          reactions={filteredPriceReactions}
        />

        <LazyAnalysisSection events={dataset.events} companies={dataset.companies} />

        {/* 이 지점이 뷰포트에 접근하면 executions/dividends 를 지연 로드한다 */}
        <div ref={detailGateRef} aria-hidden="true" />
        {detailError ? (
          <section className="empty-state" role="alert">
            <p>이행결과·배당 데이터를 불러오지 못했습니다.</p>
            <p className="muted">{detailError}</p>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setDetailError(null)}
            >
              다시 시도
            </button>
          </section>
        ) : null}

        <EventTable
          events={filteredEvents}
          onSelectStock={setSelectedStockCode}
          selectedStockCode={selectedStockCode}
        />

        <ScreenerTable
          events={enrichedEvents}
          onSelectStock={setSelectedStockCode}
          selectedStockCode={selectedStockCode}
        />

        <CompanyDetail
          companies={dataset.companies}
          events={enrichedEvents}
          holdings={dataset.holdingSnapshots}
          priceReactions={dataset.priceReactions}
          latestPrices={dataset.latestPrices}
          executions={detailData?.executions ?? []}
          dividends={detailData?.dividends ?? []}
          selectedStockCode={selectedStockCode}
          onSelectStock={setSelectedStockCode}
        />

        <Methodology status={dataset.status} />
      </main>
    </Shell>
  );
}

export default App;
