import { useMemo, useState } from "react";
import type { EnrichedEvent } from "../types/buybacks";
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

type SortKey = "date" | "company" | "amount" | "stake" | "marketCap";

export function EventTable({ events, selectedStockCode, onSelectStock }: EventTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [ascending, setAscending] = useState(false);

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
      return direction * a.disclosure_date.localeCompare(b.disclosure_date);
    });
    return sorted;
  }, [ascending, events, sortKey]);

  const changeSort = (next: SortKey) => {
    if (next === sortKey) {
      setAscending((value) => !value);
    } else {
      setSortKey(next);
      setAscending(false);
    }
  };

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
              <SortableHeader active={sortKey === "date"} onClick={() => changeSort("date")}>
                공시일
              </SortableHeader>
              <SortableHeader active={sortKey === "company"} onClick={() => changeSort("company")}>
                종목
              </SortableHeader>
              <th>유형</th>
              <SortableHeader active={sortKey === "amount"} onClick={() => changeSort("amount")}>
                예정금액
              </SortableHeader>
              <th>예정주식수</th>
              <SortableHeader active={sortKey === "stake"} onClick={() => changeSort("stake")}>
                예정지분
              </SortableHeader>
              <th>목적</th>
              <th>기보유비율</th>
              <SortableHeader active={sortKey === "marketCap"} onClick={() => changeSort("marketCap")}>
                시가총액
              </SortableHeader>
            </tr>
          </thead>
          <tbody>
            {sortedEvents.map((event) => {
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
                  <td>
                    <AmountBreakdown event={event} />
                  </td>
                  <td>
                    <ShareBreakdown event={event} />
                  </td>
                  <td>
                    <PlannedStakeCell event={event} />
                  </td>
                  <td className="purpose-cell">{event.purpose ?? "-"}</td>
                  <td>{formatPercent(event.holding_before_ratio_common ?? event.holding?.treasury_ratio)}</td>
                  <td>
                    <MarketCapCell event={event} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
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

function plannedStakeValue(event: EnrichedEvent) {
  const marketCap = marketCapFrom(event.latestPrice ?? event.priceReaction, event.holding);
  return plannedEventStake(event, marketCap.amount) ?? -1;
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
  onClick
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <th>
      <button className={active ? "sort-button active-sort" : "sort-button"} type="button" onClick={onClick}>
        {children}
      </button>
    </th>
  );
}
