import { useMemo, useState } from "react";
import type { EnrichedEvent } from "../types/buybacks";
import {
  DATA_QUALITY_LABELS,
  EVENT_TYPE_LABELS,
  dartUrl,
  formatKRW,
  formatMarketCapKRW,
  formatNumber,
  formatPercent,
  formatSignedPercent
} from "../utils/format";
import { marketCapFrom } from "../utils/marketCap";
import {
  displayReactionValue,
  displayRelativeReaction,
  displaySimpleReaction
} from "../utils/priceReactions";

interface EventTableProps {
  events: EnrichedEvent[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

type SortKey = "date" | "company" | "amount" | "marketCap" | "reaction";

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
          ((marketCapFrom(a.priceReaction, a.holding).amount ?? -1) -
            (marketCapFrom(b.priceReaction, b.holding).amount ?? -1))
        );
      }
      return direction * ((displayReactionValue(a.priceReaction) ?? -99) - (displayReactionValue(b.priceReaction) ?? -99));
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
              <SortableHeader active={sortKey === "marketCap"} onClick={() => changeSort("marketCap")}>
                시가총액
              </SortableHeader>
              <SortableHeader active={sortKey === "reaction"} onClick={() => changeSort("reaction")}>
                가격반응
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
                  <td>
                    <AmountBreakdown event={event} />
                  </td>
                  <td>
                    <ShareBreakdown event={event} />
                  </td>
                  <td className="purpose-cell">{event.purpose ?? "-"}</td>
                  <td>{formatPercent(event.holding?.treasury_ratio ?? event.holding_before_ratio_common)}</td>
                  <td>
                    <MarketCapCell event={event} />
                  </td>
                  <td>
                    <PriceReactionCell event={event} />
                  </td>
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

function AmountBreakdown({ event }: { event: EnrichedEvent }) {
  const commonAmount = event.planned_amount_common_krw ?? event.planned_amount_krw;
  const otherAmount = event.planned_amount_other_krw ?? null;
  return (
    <div className="stacked-value">
      <strong>{formatKRW(event.planned_amount_krw)}</strong>
      {otherAmount !== null && (
        <small>
          보통 {formatKRW(commonAmount)} / 기타 {formatKRW(otherAmount)}
        </small>
      )}
    </div>
  );
}

function ShareBreakdown({ event }: { event: EnrichedEvent }) {
  return (
    <div className="stacked-value">
      <strong>{formatNumber(event.planned_shares_common)}</strong>
      {event.planned_shares_other !== null && (
        <small>기타 {formatNumber(event.planned_shares_other)}</small>
      )}
    </div>
  );
}

function PriceReactionCell({ event }: { event: EnrichedEvent }) {
  const relative = displayRelativeReaction(event.priceReaction);
  const simple = displaySimpleReaction(event.priceReaction);
  return (
    <div className="stacked-value reaction-value">
      <strong>{formatSignedPercent(relative.value)}</strong>
      <small>
        {relative.label} / {DATA_QUALITY_LABELS[relative.quality]}
      </small>
      <small>{`\uB2E8\uC21C ${simple.label}: ${formatSignedPercent(simple.value)}`}</small>
    </div>
  );
}

function MarketCapCell({ event }: { event: EnrichedEvent }) {
  const marketCap = marketCapFrom(event.priceReaction, event.holding);
  return (
    <div className="stacked-value">
      <strong>{formatMarketCapKRW(marketCap.amount)}</strong>
      {marketCap.amount !== null && marketCap.close !== null && marketCap.priceDate !== null ? (
        <small>
          {marketCap.priceDate} 종가 {formatNumber(marketCap.close)}원
        </small>
      ) : marketCap.close !== null && marketCap.issuedShares === null ? (
        <small>발행주식수 없음</small>
      ) : (
        <small>가격 없음</small>
      )}
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
