import { EVENT_TYPES, type EventType, type Filters, type Market } from "../types/buybacks";
import { EVENT_TYPE_LABELS, MARKET_LABELS } from "../utils/format";
import { DEFAULT_FILTERS, marketOptions } from "../utils/metrics";

interface FilterBarProps {
  filters: Filters;
  years: string[];
  onChange: (filters: Filters) => void;
}

export function FilterBar({ filters, years, onChange }: FilterBarProps) {
  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    onChange({ ...filters, [key]: value });
  };

  return (
    <section className="filter-panel" aria-label="이벤트 필터">
      <div className="filter-grid">
        <label>
          시장
          <select
            value={filters.market}
            onChange={(event) => setFilter("market", event.target.value as Market | "ALL")}
          >
            {marketOptions().map((market) => (
              <option value={market} key={market}>
                {market === "ALL" ? "전체 시장" : MARKET_LABELS[market]}
              </option>
            ))}
          </select>
        </label>
        <label>
          이벤트 유형
          <select
            value={filters.eventType}
            onChange={(event) => setFilter("eventType", event.target.value as EventType | "ALL")}
          >
            <option value="ALL">전체</option>
            {EVENT_TYPES.map((type) => (
              <option value={type} key={type}>
                {EVENT_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </label>
        <label>
          연도
          <select value={filters.year} onChange={(event) => setFilter("year", event.target.value)}>
            <option value="ALL">전체 기간</option>
            {years.map((year) => (
              <option value={year} key={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
        <label>
          보유비율 최소
          <input
            min="0"
            max="30"
            step="0.5"
            type="number"
            value={Math.round(filters.minHoldingRatio * 1000) / 10}
            onChange={(event) => setFilter("minHoldingRatio", Number(event.target.value) / 100)}
          />
        </label>
        <label>
          보유비율 최대
          <input
            min="0"
            max="30"
            step="0.5"
            type="number"
            value={Math.round(filters.maxHoldingRatio * 1000) / 10}
            onChange={(event) => setFilter("maxHoldingRatio", Number(event.target.value) / 100)}
          />
        </label>
        <label className="search-label">
          검색
          <input
            type="search"
            value={filters.search}
            placeholder="종목명 또는 종목코드"
            onChange={(event) => setFilter("search", event.target.value)}
          />
        </label>
        <button className="secondary-button" type="button" onClick={() => onChange(DEFAULT_FILTERS)}>
          초기화
        </button>
      </div>
      <div className="active-filters" aria-live="polite">
        <span>시장: {filters.market === "ALL" ? "전체" : filters.market}</span>
        <span>연도: {filters.year === "ALL" ? "전체" : filters.year}</span>
        <span>
          보유비율 {(filters.minHoldingRatio * 100).toFixed(1)}% ~{" "}
          {(filters.maxHoldingRatio * 100).toFixed(1)}%
        </span>
      </div>
    </section>
  );
}

