import { useMemo } from "react";
import type {
  Company,
  EnrichedEvent,
  LatestPriceSnapshot,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";
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
import { latestMarketCap, marketCapFrom, plannedAcquisitionStake } from "../utils/marketCap";
import { dedupeHoldingTimeline, latestPriceMap } from "../utils/metrics";
import { displayRelativeReaction, displaySimpleReaction } from "../utils/priceReactions";

interface CompanyDetailProps {
  companies: Company[];
  events: EnrichedEvent[];
  holdings: TreasuryHoldingSnapshot[];
  priceReactions: PriceReaction[];
  latestPrices: LatestPriceSnapshot[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

export function CompanyDetail({
  companies,
  events,
  holdings,
  priceReactions,
  latestPrices,
  selectedStockCode,
  onSelectStock
}: CompanyDetailProps) {
  const company = companies.find((item) => item.stock_code === selectedStockCode) ?? companies[0];
  const companyEvents = useMemo(
    () =>
      events
        .filter((event) => event.stock_code === company?.stock_code)
        .sort((a, b) => b.disclosure_date.localeCompare(a.disclosure_date)),
    [company?.stock_code, events]
  );
  const companyHoldings = useMemo(
    () =>
      dedupeHoldingTimeline(holdings.filter((snapshot) => snapshot.stock_code === company?.stock_code))
        .sort((a, b) => a.as_of_date.localeCompare(b.as_of_date)),
    [company?.stock_code, holdings]
  );
  const companyReactions = useMemo(
    () => priceReactions.filter((reaction) => reaction.stock_code === company?.stock_code),
    [company?.stock_code, priceReactions]
  );
  const latestPriceByStock = useMemo(() => latestPriceMap(latestPrices), [latestPrices]);
  const latestPrice = company ? latestPriceByStock.get(company.stock_code) : undefined;
  const latestHolding = useMemo(() => pickPrimaryHolding(companyHoldings), [companyHoldings]);
  const currentMarketCap = useMemo(
    () => latestMarketCap(latestPrice, companyReactions, latestHolding),
    [companyReactions, latestHolding, latestPrice]
  );
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
        <CurrentPrice latestPrice={latestPrice} />
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
          <span>시가총액</span>
          <strong>{formatMarketCapKRW(currentMarketCap.amount)}</strong>
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
        <h3>공시 목록</h3>
        {companyEvents.length > 0 ? (
          <ol className="disclosure-list">
            {companyEvents.map((event) => (
              <li key={event.event_id}>
                <div className="disclosure-meta">
                  <time>{event.disclosure_date}</time>
                  <span className={`event-chip event-${event.event_type}`}>
                    {EVENT_TYPE_LABELS[event.event_type]}
                  </span>
                </div>
                <div className="event-timeline-copy">
                  <p>{event.purpose ?? event.raw_report_name ?? "목적 데이터 없음"}</p>
                  <EventDetailLines event={event} />
                </div>
                <DisclosureReaction event={event} />
                <DisclosureSourceLink event={event} />
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty-copy">수집된 이벤트가 없습니다.</p>
        )}
      </section>
    </section>
  );
}

function CurrentPrice({ latestPrice }: { latestPrice: LatestPriceSnapshot | undefined }) {
  const priceChange = latestPriceChange(latestPrice?.change_rate);
  return (
    <div className="company-price">
      <strong>{formatNumber(latestPrice?.close)}</strong>
      <small className={`price-change ${priceChange.className}`}>{priceChange.label}</small>
    </div>
  );
}

function latestPriceChange(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return { className: "price-change-flat", label: "-" };
  }
  if (value <= -0.3) {
    return { className: "price-change-down limit-change", label: `▼ ${formatSignedPercent(value)}` };
  }
  if (value < 0) {
    return { className: "price-change-down", label: `▽ ${formatSignedPercent(value)}` };
  }
  if (value >= 0.3) {
    return { className: "price-change-up limit-change", label: `▲ ${formatSignedPercent(value)}` };
  }
  if (value > 0) {
    return { className: "price-change-up", label: `△ ${formatSignedPercent(value)}` };
  }
  return { className: "price-change-flat", label: formatSignedPercent(value) };
}

function DisclosureReaction({ event }: { event: EnrichedEvent }) {
  if (!event.priceReaction) {
    return (
      <div className="disclosure-reaction">
        <span>가격반응</span>
        <strong>-</strong>
      </div>
    );
  }
  const relative = displayRelativeReaction(event.priceReaction);
  const simple = displaySimpleReaction(event.priceReaction);
  return (
    <div className="disclosure-reaction">
      <span>{relative.label}</span>
      <strong>{formatSignedPercent(relative.value)}</strong>
      <small>
        {DATA_QUALITY_LABELS[relative.quality]} · 단순 {simple.label}: {formatSignedPercent(simple.value)}
      </small>
    </div>
  );
}

function DisclosureSourceLink({ event }: { event: EnrichedEvent }) {
  const url = event.source_url ?? dartUrl(event.rcept_no);
  if (!url) {
    return <span className="muted">원문 없음</span>;
  }
  return (
    <a className="source-link" href={url} target="_blank" rel="noreferrer">
      원문
    </a>
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

function EventDetailLines({ event }: { event: EnrichedEvent }) {
  const details = eventDetailLines(event);
  if (details.length === 0) {
    return null;
  }
  return <small>{details.join(" · ")}</small>;
}

function eventDetailLines(event: EnrichedEvent) {
  const lines: string[] = [];
  if (event.planned_amount_common_krw != null || event.planned_amount_other_krw != null) {
    lines.push(
      `예정금액 보통 ${formatKRW(event.planned_amount_common_krw ?? event.planned_amount_krw)} / 기타 ${formatKRW(
        event.planned_amount_other_krw
      )}`
    );
  }
  if (event.planned_shares_other !== null) {
    lines.push(
      `예정주식수 보통 ${formatNumber(event.planned_shares_common)} / 기타 ${formatNumber(event.planned_shares_other)}`
    );
  }

  const marketCap = marketCapFrom(event.latestPrice ?? event.priceReaction, event.holding);
  const stake = plannedAcquisitionStake(event.event_type, event.planned_amount_krw, marketCap.amount);
  if (stake !== null) {
    lines.push(`예정취득지분 ${formatPercent(stake, 2)}`);
  }
  return lines;
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
