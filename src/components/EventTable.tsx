import { useMemo, useState } from "react";
import type { EnrichedEvent } from "../types/buybacks";
import {
  EVENT_TYPE_LABELS,
  dartUrl,
  formatKRW,
  formatNumber,
  formatPercent,
  formatSignedPercent
} from "../utils/format";

interface EventTableProps {
  events: EnrichedEvent[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

type SortKey = "date" | "company" | "amount" | "return20d";

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
      return direction * ((a.priceReaction?.return_20d ?? -99) - (b.priceReaction?.return_20d ?? -99));
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
              <th>목적</th>
              <th>보유비율</th>
              <SortableHeader active={sortKey === "return20d"} onClick={() => changeSort("return20d")}>
                +20D
              </SortableHeader>
              <th>DART</th>
            </tr>
          </thead>
          <tbody>
            {sortedEvents.map((event) => {
              const url = event.source_url ?? dartUrl(event.rcept_no);
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
                  <td>{formatKRW(event.planned_amount_krw)}</td>
                  <td>{formatNumber(event.planned_shares_common)}</td>
                  <td className="purpose-cell">{event.purpose ?? "-"}</td>
                  <td>{formatPercent(event.holding?.treasury_ratio ?? event.holding_before_ratio_common)}</td>
                  <td>{formatSignedPercent(event.priceReaction?.return_20d)}</td>
                  <td>
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer">
                        원문
                      </a>
                    ) : (
                      <span className="muted">없음</span>
                    )}
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

