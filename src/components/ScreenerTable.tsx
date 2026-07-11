import { useMemo, useState } from "react";
import {
  DEFAULT_TABLE_PAGE_SIZE,
  PAGINATION_WINDOW_SIZE,
  TABLE_PAGE_SIZE_OPTIONS,
  type TablePageSize
} from "../constants";
import type { EnrichedEvent, Market } from "../types/buybacks";
import { buildScreenerRows } from "../utils/screener";
import { MARKET_LABELS, formatKRW, formatPercent } from "../utils/format";

interface ScreenerTableProps {
  events: EnrichedEvent[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

type SortKey =
  | "company"
  | "market"
  | "eventCount"
  | "recentAmount"
  | "intensity"
  | "dividendYield"
  | "totalReturn"
  | "retirementShare"
  | "completion"
  | "holding"
  | "lastEventDate";

type MinEventCount = 1 | 2 | 3;

const MIN_EVENT_COUNT_OPTIONS: MinEventCount[] = [1, 2, 3];

export function ScreenerTable({ events, selectedStockCode, onSelectStock }: ScreenerTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("intensity");
  const [ascending, setAscending] = useState(false);
  const [pageSize, setPageSize] = useState<TablePageSize>(DEFAULT_TABLE_PAGE_SIZE);
  const [page, setPage] = useState(1);
  const [marketFilter, setMarketFilter] = useState<Market | "ALL">("ALL");
  const [minEventCount, setMinEventCount] = useState<MinEventCount>(1);
  const [retirementOnly, setRetirementOnly] = useState(false);
  const [highCompletionOnly, setHighCompletionOnly] = useState(false);

  const rows = useMemo(() => buildScreenerRows(events), [events]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const marketMatch = marketFilter === "ALL" || row.market === marketFilter;
      const countMatch = row.eventCount >= minEventCount;
      const retirementMatch = !retirementOnly || row.retirementEventCount > 0;
      const completionMatch =
        !highCompletionOnly ||
        (row.averageCompletionRate !== null && row.averageCompletionRate >= 0.8);
      return marketMatch && countMatch && retirementMatch && completionMatch;
    });
  }, [rows, marketFilter, minEventCount, retirementOnly, highCompletionOnly]);

  const [lastFilteredRows, setLastFilteredRows] = useState(filteredRows);
  if (filteredRows !== lastFilteredRows) {
    setLastFilteredRows(filteredRows);
    setPage(1);
  }

  const sortedRows = useMemo(() => {
    const direction = ascending ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      if (sortKey === "company") return direction * a.corpName.localeCompare(b.corpName);
      if (sortKey === "market") return compareNullableString(a.market, b.market, direction);
      if (sortKey === "eventCount") return direction * (a.eventCount - b.eventCount);
      if (sortKey === "recentAmount") {
        return compareNullableNumber(
          a.recentPlannedAcquisitionAmountKrw,
          b.recentPlannedAcquisitionAmountKrw,
          direction
        );
      }
      if (sortKey === "intensity") {
        return compareNullableNumber(a.acquisitionIntensity, b.acquisitionIntensity, direction);
      }
      if (sortKey === "dividendYield") {
        return compareNullableNumber(a.dividendYield, b.dividendYield, direction);
      }
      if (sortKey === "totalReturn") {
        return compareNullableNumber(a.totalShareholderReturn, b.totalShareholderReturn, direction);
      }
      if (sortKey === "retirementShare") {
        return compareNullableNumber(a.retirementShare, b.retirementShare, direction);
      }
      if (sortKey === "completion") {
        return compareNullableNumber(a.averageCompletionRate, b.averageCompletionRate, direction);
      }
      if (sortKey === "holding") {
        return compareNullableNumber(a.holdingRatio, b.holdingRatio, direction);
      }
      if (sortKey === "lastEventDate") {
        return compareNullableString(a.lastEventDate, b.lastEventDate, direction);
      }
      return 0;
    });
  }, [ascending, filteredRows, sortKey]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const clampedPage = Math.min(page, pageCount);
  const startIndex = sortedRows.length === 0 ? 0 : (clampedPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, sortedRows.length);
  const visibleRows = sortedRows.slice(startIndex, endIndex);

  const changeSort = (next: SortKey) => {
    setPage(1);
    if (next === sortKey) {
      setAscending((value) => !value);
    } else {
      setSortKey(next);
      setAscending(false);
    }
  };

  const changePageSize = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setPageSize(Number(event.target.value) as TablePageSize);
    setPage(1);
  };

  const pageNumbers = paginationWindow(clampedPage, pageCount);

  const selectStock = (stockCode: string) => {
    onSelectStock(stockCode);
    document.getElementById("company")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="table-panel card-table" id="screener">
      <header className="panel-header">
        <div>
          <h2>기업 스크리너</h2>
          <p>
            자사주 활동 강도별 기업 비교 — 계획 공시 기준이며 이행률은 결과보고서 연결분만
            반영합니다.
          </p>
        </div>
        <span>{filteredRows.length}개 기업</span>
      </header>

      <div className="screener-filters" role="group" aria-label="스크리너 필터">
        <label>
          시장
          <select
            value={marketFilter}
            onChange={(event) => setMarketFilter(event.target.value as Market | "ALL")}
          >
            <option value="ALL">전체 시장</option>
            <option value="KOSPI">{MARKET_LABELS.KOSPI}</option>
            <option value="KOSDAQ">{MARKET_LABELS.KOSDAQ}</option>
          </select>
        </label>
        <label>
          최소 이벤트 수
          <select
            value={minEventCount}
            onChange={(event) => setMinEventCount(Number(event.target.value) as MinEventCount)}
          >
            {MIN_EVENT_COUNT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}건{option === 3 ? "+" : ""} 이상
              </option>
            ))}
          </select>
        </label>
        <button
          className={retirementOnly ? "filter-toggle active-filter-toggle" : "filter-toggle"}
          type="button"
          aria-pressed={retirementOnly}
          onClick={() => setRetirementOnly((value) => !value)}
        >
          소각 있는 기업만
        </button>
        <button
          className={highCompletionOnly ? "filter-toggle active-filter-toggle" : "filter-toggle"}
          type="button"
          aria-pressed={highCompletionOnly}
          onClick={() => setHighCompletionOnly((value) => !value)}
        >
          이행률 80%+ 만
        </button>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <SortableHeader
                active={sortKey === "company"}
                ascending={ascending}
                onClick={() => changeSort("company")}
              >
                종목
              </SortableHeader>
              <SortableHeader
                active={sortKey === "market"}
                ascending={ascending}
                className="col-optional"
                onClick={() => changeSort("market")}
              >
                시장
              </SortableHeader>
              <SortableHeader
                active={sortKey === "eventCount"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("eventCount")}
              >
                이벤트 수
              </SortableHeader>
              <SortableHeader
                active={sortKey === "recentAmount"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("recentAmount")}
              >
                12M 취득계획
              </SortableHeader>
              <SortableHeader
                active={sortKey === "intensity"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("intensity")}
              >
                시총대비 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "dividendYield"}
                ascending={ascending}
                className="numeric-cell col-optional"
                onClick={() => changeSort("dividendYield")}
              >
                배당수익률 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "totalReturn"}
                ascending={ascending}
                className="numeric-cell col-optional"
                onClick={() => changeSort("totalReturn")}
              >
                총환원율 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "retirementShare"}
                ascending={ascending}
                className="numeric-cell col-optional"
                onClick={() => changeSort("retirementShare")}
              >
                소각비중 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "completion"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("completion")}
              >
                평균 이행률 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "holding"}
                ascending={ascending}
                className="numeric-cell col-optional"
                onClick={() => changeSort("holding")}
              >
                보유비율 %
              </SortableHeader>
              <SortableHeader
                active={sortKey === "lastEventDate"}
                ascending={ascending}
                className="col-optional"
                onClick={() => changeSort("lastEventDate")}
              >
                최근 이벤트일
              </SortableHeader>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr
                className={row.stockCode === selectedStockCode ? "selected-row" : undefined}
                key={row.stockCode}
              >
                <td className="company-cell">
                  <button
                    className="link-button"
                    type="button"
                    onClick={() => selectStock(row.stockCode)}
                  >
                    {row.corpName || row.stockCode}
                    <small>{row.stockCode}</small>
                  </button>
                </td>
                <td className="col-optional" data-label="시장">
                  {row.market ? MARKET_LABELS[row.market] : "-"}
                </td>
                <td className="numeric-cell" data-label="이벤트 수">
                  {row.eventCount}
                </td>
                <td className="numeric-cell" data-label="12M 취득계획">
                  {formatKRW(row.recentPlannedAcquisitionAmountKrw)}
                </td>
                <td className="numeric-cell" data-label="시총대비 %">
                  {formatPercent(row.acquisitionIntensity, 2)}
                </td>
                <td className="numeric-cell col-optional" data-label="배당수익률 %">
                  {formatPercent(row.dividendYield, 2)}
                </td>
                <td className="numeric-cell col-optional" data-label="총환원율 %">
                  {formatPercent(row.totalShareholderReturn, 2)}
                </td>
                <td className="numeric-cell col-optional" data-label="소각비중 %">
                  {formatPercent(row.retirementShare, 1)}
                </td>
                <td className="numeric-cell" data-label="평균 이행률 %">
                  {formatPercent(row.averageCompletionRate, 1)}
                </td>
                <td className="numeric-cell col-optional" data-label="보유비율 %">
                  {formatPercent(row.holdingRatio)}
                </td>
                <td className="col-optional" data-label="최근 이벤트일">
                  {row.lastEventDate ?? "-"}
                </td>
              </tr>
            ))}
            {visibleRows.length === 0 ? (
              <tr>
                <td className="empty-table-cell" colSpan={11}>
                  조건에 맞는 기업이 없습니다.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="table-pagination" aria-label="기업 스크리너 페이지">
        <div className="pagination-summary">
          {sortedRows.length === 0
            ? "0개"
            : `${startIndex + 1}-${endIndex} / ${sortedRows.length}개`}
        </div>
        <label className="page-size-control">
          페이지당
          <select value={pageSize} onChange={changePageSize}>
            {TABLE_PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}건
              </option>
            ))}
          </select>
        </label>
        <div className="pagination-actions">
          <button
            aria-label="첫 페이지"
            className="page-button"
            disabled={clampedPage === 1}
            type="button"
            onClick={() => setPage(1)}
          >
            처음
          </button>
          <button
            aria-label="이전 페이지"
            className="page-button"
            disabled={clampedPage === 1}
            type="button"
            onClick={() => setPage(Math.max(1, clampedPage - 1))}
          >
            이전
          </button>
          {pageNumbers.map((pageNumber) => (
            <button
              aria-current={pageNumber === clampedPage ? "page" : undefined}
              aria-label={`${pageNumber} 페이지`}
              className={pageNumber === clampedPage ? "page-button active-page" : "page-button"}
              key={pageNumber}
              type="button"
              onClick={() => setPage(pageNumber)}
            >
              {pageNumber}
            </button>
          ))}
          <button
            aria-label="다음 페이지"
            className="page-button"
            disabled={clampedPage === pageCount}
            type="button"
            onClick={() => setPage(Math.min(pageCount, clampedPage + 1))}
          >
            다음
          </button>
          <button
            aria-label="마지막 페이지"
            className="page-button"
            disabled={clampedPage === pageCount}
            type="button"
            onClick={() => setPage(pageCount)}
          >
            끝
          </button>
        </div>
      </div>
    </section>
  );
}

function paginationWindow(currentPage: number, pageCount: number) {
  const half = Math.floor(PAGINATION_WINDOW_SIZE / 2);
  const start = Math.max(1, Math.min(currentPage - half, pageCount - (PAGINATION_WINDOW_SIZE - 1)));
  const end = Math.min(pageCount, start + PAGINATION_WINDOW_SIZE - 1);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

/** null 값은 정렬 방향과 무관하게 항상 맨 뒤에 위치시킨다. */
function compareNullableNumber(a: number | null, b: number | null, direction: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction * (a - b);
}

/** null 값은 정렬 방향과 무관하게 항상 맨 뒤에 위치시킨다. */
function compareNullableString(a: string | null, b: string | null, direction: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction * a.localeCompare(b);
}

function SortableHeader({
  children,
  active,
  ascending,
  className,
  onClick
}: {
  children: React.ReactNode;
  active: boolean;
  ascending: boolean;
  className?: string;
  onClick: () => void;
}) {
  const ariaSort = active ? (ascending ? "ascending" : "descending") : "none";
  return (
    <th className={className} aria-sort={ariaSort}>
      <button
        className={active ? "sort-button active-sort" : "sort-button"}
        type="button"
        onClick={onClick}
      >
        {children}
        <span aria-hidden="true" className="sort-indicator">
          {active ? (ascending ? "↑" : "↓") : ""}
        </span>
      </button>
    </th>
  );
}
