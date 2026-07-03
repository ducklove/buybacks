import { useMemo, useState } from "react";
import {
  DEFAULT_TABLE_PAGE_SIZE,
  PAGINATION_WINDOW_SIZE,
  TABLE_PAGE_SIZE_OPTIONS,
  type TablePageSize
} from "../constants";
import type { EnrichedEvent } from "../types/buybacks";
import { completionRate, executionStatus } from "../utils/executions";
import {
  EVENT_TYPE_LABELS,
  formatKRW,
  formatMarketCapKRW,
  formatNumber,
  formatPercent
} from "../utils/format";
import { marketCapFrom, plannedEventStake } from "../utils/marketCap";

interface EventTableProps {
  events: EnrichedEvent[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

type SortKey = "date" | "company" | "amount" | "stake" | "marketCap" | "completion";

export function EventTable({ events, selectedStockCode, onSelectStock }: EventTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [ascending, setAscending] = useState(false);
  const [pageSize, setPageSize] = useState<TablePageSize>(DEFAULT_TABLE_PAGE_SIZE);
  const [page, setPage] = useState(1);
  const [lastEvents, setLastEvents] = useState(events);

  if (events !== lastEvents) {
    setLastEvents(events);
    setPage(1);
  }

  const sortedEvents = useMemo(() => {
    const sorted = [...events].sort((a, b) => {
      const direction = ascending ? 1 : -1;
      if (sortKey === "date") return direction * a.disclosure_date.localeCompare(b.disclosure_date);
      if (sortKey === "company") return direction * a.corp_name.localeCompare(b.corp_name);
      if (sortKey === "amount") {
        return direction * ((a.planned_amount_krw ?? -1) - (b.planned_amount_krw ?? -1));
      }
      if (sortKey === "marketCap") {
        return (
          direction *
          ((marketCapFrom(a.latestPrice ?? a.priceReaction, a.holding).amount ?? -1) -
            (marketCapFrom(b.latestPrice ?? b.priceReaction, b.holding).amount ?? -1))
        );
      }
      if (sortKey === "stake") {
        return direction * (plannedStakeValue(a) - plannedStakeValue(b));
      }
      if (sortKey === "completion") {
        return direction * (completionRateValue(a) - completionRateValue(b));
      }
      return direction * a.disclosure_date.localeCompare(b.disclosure_date);
    });
    return sorted;
  }, [ascending, events, sortKey]);

  const pageCount = Math.max(1, Math.ceil(sortedEvents.length / pageSize));
  const clampedPage = Math.min(page, pageCount);
  const startIndex = sortedEvents.length === 0 ? 0 : (clampedPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, sortedEvents.length);
  const visibleEvents = sortedEvents.slice(startIndex, endIndex);

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

  return (
    <section className="table-panel" id="events">
      <header className="panel-header">
        <div>
          <h2>이벤트 탐색기</h2>
          <p>공시 이벤트를 정렬하고 종목 상세 패널로 보낼 수 있습니다.</p>
        </div>
        <span>{events.length}건</span>
      </header>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <SortableHeader
                active={sortKey === "date"}
                ascending={ascending}
                onClick={() => changeSort("date")}
              >
                공시일
              </SortableHeader>
              <SortableHeader
                active={sortKey === "company"}
                ascending={ascending}
                onClick={() => changeSort("company")}
              >
                종목
              </SortableHeader>
              <th>유형</th>
              <SortableHeader
                active={sortKey === "amount"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("amount")}
              >
                예정금액
              </SortableHeader>
              <th className="numeric-cell col-optional">예정주식수</th>
              <SortableHeader
                active={sortKey === "stake"}
                ascending={ascending}
                className="col-optional"
                onClick={() => changeSort("stake")}
              >
                예정지분
              </SortableHeader>
              <th className="col-optional">목적</th>
              <th className="col-optional">기보유비율</th>
              <SortableHeader
                active={sortKey === "marketCap"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("marketCap")}
              >
                시가총액
              </SortableHeader>
              <SortableHeader
                active={sortKey === "completion"}
                ascending={ascending}
                className="numeric-cell"
                onClick={() => changeSort("completion")}
              >
                이행률
              </SortableHeader>
            </tr>
          </thead>
          <tbody>
            {visibleEvents.map((event) => {
              return (
                <tr
                  className={event.stock_code === selectedStockCode ? "selected-row" : undefined}
                  key={event.event_id}
                >
                  <td>{event.disclosure_date}</td>
                  <td>
                    <button
                      className="link-button"
                      type="button"
                      onClick={() => onSelectStock(event.stock_code)}
                    >
                      {event.corp_name}
                      <small>{event.stock_code}</small>
                    </button>
                  </td>
                  <td>
                    <span className={`event-chip event-${event.event_type}`}>
                      {EVENT_TYPE_LABELS[event.event_type]}
                    </span>
                  </td>
                  <td className="numeric-cell">
                    <AmountBreakdown event={event} />
                  </td>
                  <td className="numeric-cell col-optional">
                    <ShareBreakdown event={event} />
                  </td>
                  <td className="col-optional">
                    <PlannedStakeCell event={event} />
                  </td>
                  <td className="purpose-cell col-optional">{event.purpose ?? "-"}</td>
                  <td className="col-optional">
                    <HoldingBeforeCell event={event} />
                  </td>
                  <td className="numeric-cell">
                    <MarketCapCell event={event} />
                  </td>
                  <td className="numeric-cell">
                    <CompletionRateCell event={event} />
                  </td>
                </tr>
              );
            })}
            {visibleEvents.length === 0 ? (
              <tr>
                <td className="empty-table-cell" colSpan={10}>
                  표시할 이벤트가 없습니다.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="table-pagination" aria-label="이벤트 탐색기 페이지">
        <div className="pagination-summary">
          {sortedEvents.length === 0
            ? "0건"
            : `${startIndex + 1}-${endIndex} / ${sortedEvents.length}건`}
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

function AmountBreakdown({ event }: { event: EnrichedEvent }) {
  return (
    <div className="stacked-value">
      <strong>{formatKRW(event.planned_amount_krw)}</strong>
    </div>
  );
}

function ShareBreakdown({ event }: { event: EnrichedEvent }) {
  return (
    <div className="stacked-value">
      <strong>{formatNumber(event.planned_shares_common)}</strong>
    </div>
  );
}

function PlannedStakeCell({ event }: { event: EnrichedEvent }) {
  const marketCap = marketCapFrom(event.latestPrice ?? event.priceReaction, event.holding);
  const stake = plannedEventStake(event, marketCap.amount);
  return (
    <div className="stacked-value">
      <strong>{formatPercent(stake, 2)}</strong>
    </div>
  );
}

function HoldingBeforeCell({ event }: { event: EnrichedEvent }) {
  if (event.holding_before_ratio_common !== null) {
    return <>{formatPercent(event.holding_before_ratio_common)}</>;
  }
  if (event.holding?.treasury_ratio !== null && event.holding?.treasury_ratio !== undefined) {
    return (
      <div
        className="stacked-value"
        title="정기보고서 기준 보유비율입니다. 공시일 직전 보유비율과 다를 수 있습니다."
      >
        <span>{formatPercent(event.holding.treasury_ratio)}</span>
        <small>{event.holding.as_of_date}</small>
      </div>
    );
  }
  return <>-</>;
}

function plannedStakeValue(event: EnrichedEvent) {
  const marketCap = marketCapFrom(event.latestPrice ?? event.priceReaction, event.holding);
  return plannedEventStake(event, marketCap.amount) ?? -1;
}

function completionRateValue(event: EnrichedEvent) {
  return completionRate(event, event.execution) ?? -1;
}

function CompletionRateCell({ event }: { event: EnrichedEvent }) {
  const rate = completionRate(event, event.execution);
  const { status, reason } = executionStatus(event.execution);
  if (rate === null && status === null) {
    return <>-</>;
  }
  return (
    <div className="stacked-value" title={status === "미달" ? (reason ?? undefined) : undefined}>
      <strong>{formatPercent(rate, 1)}</strong>
      {status ? (
        <span className={`status-badge status-${statusClassName(status)}`}>{status}</span>
      ) : null}
    </div>
  );
}

function statusClassName(status: "완료" | "미달" | "진행중") {
  if (status === "완료") return "complete";
  if (status === "미달") return "shortfall";
  return "in-progress";
}

function MarketCapCell({ event }: { event: EnrichedEvent }) {
  const marketCap = marketCapFrom(event.latestPrice ?? event.priceReaction, event.holding);
  return (
    <div className="stacked-value">
      <strong>{formatMarketCapKRW(marketCap.amount)}</strong>
    </div>
  );
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
