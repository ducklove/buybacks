import { useMemo } from "react";
import type {
  Company,
  EnrichedEvent,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";
import {
  DATA_QUALITY_LABELS,
  EVENT_TYPE_LABELS,
  formatKRW,
  formatNumber,
  formatPercent,
  formatSignedPercent
} from "../utils/format";
import { displayReaction } from "../utils/priceReactions";

interface CompanyDetailProps {
  companies: Company[];
  events: EnrichedEvent[];
  holdings: TreasuryHoldingSnapshot[];
  priceReactions: PriceReaction[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

export function CompanyDetail({
  companies,
  events,
  holdings,
  priceReactions,
  selectedStockCode,
  onSelectStock
}: CompanyDetailProps) {
  const company = companies.find((item) => item.stock_code === selectedStockCode) ?? companies[0];
  const companyEvents = useMemo(
    () => events.filter((event) => event.stock_code === company?.stock_code),
    [company?.stock_code, events]
  );
  const companyHoldings = useMemo(
    () =>
      holdings
        .filter((snapshot) => snapshot.stock_code === company?.stock_code)
        .sort((a, b) => a.as_of_date.localeCompare(b.as_of_date)),
    [company?.stock_code, holdings]
  );
  const companyReactions = useMemo(
    () => priceReactions.filter((reaction) => reaction.stock_code === company?.stock_code),
    [company?.stock_code, priceReactions]
  );
  const latestHolding = useMemo(() => pickPrimaryHolding(companyHoldings), [companyHoldings]);
  const maxHoldingRatio = useMemo(
    () => Math.max(...companyHoldings.map((snapshot) => snapshot.treasury_ratio ?? 0), 0.01),
    [companyHoldings]
  );

  if (!company) {
    return (
      <section className="detail-panel" id="company">
        <h2>기업 상세</h2>
        <p className="empty-copy">선택할 기업 데이터가 없습니다.</p>
      </section>
    );
  }

  return (
    <section className="detail-panel" id="company">
      <header className="panel-header">
        <div>
          <h2>기업 상세</h2>
          <p>선택 종목의 보유비율, 이벤트, 가격 반응을 함께 봅니다.</p>
        </div>
        <label className="compact-select">
          종목
          <select value={company.stock_code} onChange={(event) => onSelectStock(event.target.value)}>
            {companies.map((item) => (
              <option value={item.stock_code} key={item.stock_code}>
                {item.corp_name} {item.stock_code}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div className="company-heading">
        <div>
          <strong>{company.corp_name}</strong>
          <span>
            {company.stock_code} · {company.market} · {company.sector ?? "업종 미상"}
          </span>
        </div>
      </div>

      <div className="detail-metrics">
        <div>
          <span>현재 보유비율</span>
          <strong>{formatPercent(latestHolding?.treasury_ratio)}</strong>
        </div>
        <div>
          <span>보유 주식수</span>
          <strong>{formatNumber(latestHolding?.ending_qty)}</strong>
        </div>
        <div>
          <span>발행주식수</span>
          <strong>{formatNumber(latestHolding?.issued_shares)}</strong>
        </div>
        <div>
          <span>최근 예정금액</span>
          <strong>{formatKRW(companyEvents[0]?.planned_amount_krw)}</strong>
        </div>
      </div>

      <section className="detail-section">
        <h3>보유비율 추이</h3>
        {companyHoldings.length > 0 ? (
          <div className="mini-timeline">
            {companyHoldings.map((snapshot) => {
              const width = holdingBarWidth(snapshot.treasury_ratio, maxHoldingRatio);
              return (
                <div
                  key={`${snapshot.stock_code}-${snapshot.as_of_date}-${snapshot.report_code}-${snapshot.stock_kind}`}
                >
                  <span>{formatHoldingLabel(snapshot)}</span>
                  <i style={{ width: `${width}%` }} />
                  <strong>{formatPercent(snapshot.treasury_ratio)}</strong>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty-copy">정기보고서 기반 보유현황이 없습니다.</p>
        )}
      </section>

      <section className="detail-section">
        <h3>최근 이벤트</h3>
        {companyEvents.length > 0 ? (
          <ol className="event-timeline">
            {companyEvents.slice(0, 5).map((event) => (
              <li key={event.event_id}>
                <time>{event.disclosure_date}</time>
                <span className={`event-chip event-${event.event_type}`}>
                  {EVENT_TYPE_LABELS[event.event_type]}
                </span>
                <p>{event.purpose ?? event.raw_report_name ?? "목적 데이터 없음"}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty-copy">수집된 이벤트가 없습니다.</p>
        )}
      </section>

      <section className="detail-section">
        <h3>공시 후 가격 반응</h3>
        {companyReactions.length > 0 ? (
          <div className="reaction-list">
            {companyReactions.map((reaction) => {
              const display = displayReaction(reaction);
              return (
                <div key={reaction.event_id}>
                  <span>{reaction.event_date}</span>
                  <strong>{formatSignedPercent(display.value)}</strong>
                  <small>
                    {display.label} · {DATA_QUALITY_LABELS[display.quality]}
                  </small>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty-copy">가격 반응 데이터가 아직 없습니다.</p>
        )}
      </section>
    </section>
  );
}

function pickPrimaryHolding(
  snapshots: TreasuryHoldingSnapshot[]
): TreasuryHoldingSnapshot | undefined {
  const latestDate = snapshots[snapshots.length - 1]?.as_of_date;
  if (!latestDate) {
    return undefined;
  }
  const latestSnapshots = snapshots.filter((snapshot) => snapshot.as_of_date === latestDate);
  return latestSnapshots.find(isCommonHolding) ?? latestSnapshots[latestSnapshots.length - 1];
}

function isCommonHolding(snapshot: TreasuryHoldingSnapshot) {
  const stockKind = snapshot.stock_kind.toLowerCase();
  return stockKind.includes("\uBCF4\uD1B5") || stockKind.includes("common");
}

function formatHoldingLabel(snapshot: TreasuryHoldingSnapshot) {
  return snapshot.stock_kind ? `${snapshot.as_of_date} ${snapshot.stock_kind}` : snapshot.as_of_date;
}

function holdingBarWidth(ratio: number | null, maxRatio: number) {
  if (ratio === null || ratio <= 0 || maxRatio <= 0) {
    return 0;
  }
  return Math.min(100, Math.max((ratio / maxRatio) * 100, 3));
}
