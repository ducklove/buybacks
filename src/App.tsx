import { useEffect, useMemo, useState } from "react";
import { CompanyDetail } from "./components/CompanyDetail";
import { DashboardCharts } from "./components/DashboardCharts";
import { DataStatusBanner } from "./components/DataStatusBanner";
import { EventTable } from "./components/EventTable";
import { FilterBar } from "./components/FilterBar";
import { KpiGrid } from "./components/KpiGrid";
import { Methodology } from "./components/Methodology";
import { Shell } from "./components/Shell";
import { loadBuybacksDataset } from "./data/loadBuybacks";
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

  useEffect(() => {
    let cancelled = false;
    loadBuybacksDataset()
      .then((loaded) => {
        if (cancelled) return;
        setDataset(loaded);
        setSelectedStockCode((current) =>
          current && loaded.companies.some((company) => company.stock_code === current)
            ? current
            : loaded.companies[0]?.stock_code ?? ""
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

  const enrichedEvents = useMemo(() => (dataset ? enrichEvents(dataset) : []), [dataset]);
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
  const kpis = useMemo(() => buildKpis(filteredEvents, latestHoldings), [filteredEvents, latestHoldings]);

  if (error) {
    return (
      <Shell>
        <main className="app-main">
          <section className="empty-state" role="alert">
            <h1>데이터를 불러오지 못했습니다</h1>
            <p>
              네트워크 연결을 확인한 뒤 다시 시도해 주세요. 문제가 계속되면 데이터 파이프라인
              점검이 필요할 수 있습니다.
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
              OpenDART 공시와 kis_proxy 가격 데이터를 정적 JSON으로 정규화해 보유 현황, 이벤트,
              공시 후 주가 흐름을 함께 살펴봅니다.
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

        <section className="split-layout">
          <EventTable
            events={filteredEvents}
            onSelectStock={setSelectedStockCode}
            selectedStockCode={selectedStockCode}
          />
          <CompanyDetail
            companies={dataset.companies}
            events={enrichedEvents}
            holdings={dataset.holdingSnapshots}
            priceReactions={dataset.priceReactions}
            latestPrices={dataset.latestPrices}
            selectedStockCode={selectedStockCode}
            onSelectStock={setSelectedStockCode}
          />
        </section>

        <Methodology status={dataset.status} />
      </main>
    </Shell>
  );
}

export default App;
