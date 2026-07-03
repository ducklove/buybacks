import { memo, useEffect, useMemo, useState } from "react";
import type {
  BuybackExecution,
  Company,
  EnrichedEvent,
  LatestPriceSnapshot,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";
import { completionRate, executionStatus, unlinkedExecutionsForStock } from "../utils/executions";
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
import { isCommonHoldingKind } from "../utils/holdings";
import { latestMarketCap, marketCapFrom, plannedEventStake } from "../utils/marketCap";
import { dedupeHoldingTimeline, latestPriceMap } from "../utils/metrics";
import { displayRelativeReaction, displaySimpleReaction } from "../utils/priceReactions";
import { fetchNaverFinanceQuote } from "../data/realtimeQuotes";

interface CompanyDetailProps {
  companies: Company[];
  events: EnrichedEvent[];
  holdings: TreasuryHoldingSnapshot[];
  priceReactions: PriceReaction[];
  latestPrices: LatestPriceSnapshot[];
  executions: BuybackExecution[];
  selectedStockCode: string;
  onSelectStock: (stockCode: string) => void;
}

export const CompanyDetail = memo(function CompanyDetail({
  companies,
  events,
  holdings,
  priceReactions,
  latestPrices,
  executions,
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
      dedupeHoldingTimeline(
        holdings.filter((snapshot) => snapshot.stock_code === company?.stock_code)
      ).sort((a, b) => a.as_of_date.localeCompare(b.as_of_date)),
    [company?.stock_code, holdings]
  );
  const companyReactions = useMemo(
    () => priceReactions.filter((reaction) => reaction.stock_code === company?.stock_code),
    [company?.stock_code, priceReactions]
  );
  const companyUnlinkedExecutions = useMemo(
    () =>
      company
        ? [...unlinkedExecutionsForStock(executions, company.stock_code)].sort((a, b) =>
            b.disclosure_date.localeCompare(a.disclosure_date)
          )
        : [],
    [company, executions]
  );
  const latestPriceByStock = useMemo(() => latestPriceMap(latestPrices), [latestPrices]);
  const [runtimePricesByStock, setRuntimePricesByStock] = useState<
    Record<string, LatestPriceSnapshot>
  >({});
  const [priceLookupMisses, setPriceLookupMisses] = useState<Record<string, true>>({});
  const staticLatestPrice = company ? latestPriceByStock.get(company.stock_code) : undefined;
  const runtimeLatestPrice = company ? runtimePricesByStock[company.stock_code] : undefined;
  const latestPrice = staticLatestPrice ?? runtimeLatestPrice;
  const loadingPriceStockCode =
    company && !staticLatestPrice && !runtimeLatestPrice && !priceLookupMisses[company.stock_code]
      ? company.stock_code
      : null;
  const latestHolding = useMemo(() => pickPrimaryHolding(companyHoldings), [companyHoldings]);
  const currentMarketCap = useMemo(
    () => latestMarketCap(latestPrice, companyReactions, latestHolding),
    [companyReactions, latestHolding, latestPrice]
  );
  const maxHoldingRatio = useMemo(
    () => Math.max(...companyHoldings.map((snapshot) => snapshot.treasury_ratio ?? 0), 0.01),
    [companyHoldings]
  );

  useEffect(() => {
    const stockCode = company?.stock_code;
    if (
      !stockCode ||
      staticLatestPrice ||
      runtimePricesByStock[stockCode] ||
      priceLookupMisses[stockCode]
    ) {
      return;
    }

    let cancelled = false;
    fetchNaverFinanceQuote(stockCode)
      .then((snapshot) => {
        if (cancelled) return;
        if (snapshot) {
          setRuntimePricesByStock((previous) => ({ ...previous, [stockCode]: snapshot }));
        } else {
          setPriceLookupMisses((previous) => ({ ...previous, [stockCode]: true }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPriceLookupMisses((previous) => ({ ...previous, [stockCode]: true }));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [company?.stock_code, priceLookupMisses, runtimePricesByStock, staticLatestPrice]);

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
          <select
            value={company.stock_code}
            onChange={(event) => onSelectStock(event.target.value)}
          >
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
        <CurrentPrice
          latestPrice={latestPrice}
          isLoading={loadingPriceStockCode === company.stock_code}
        />
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
                  <EventDetailLines event={event} latestPrice={latestPrice} />
                  <ExecutionSummary event={event} />
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

      <UnlinkedExecutionsSection executions={companyUnlinkedExecutions} />
    </section>
  );
});

function CurrentPrice({
  latestPrice,
  isLoading
}: {
  latestPrice: LatestPriceSnapshot | undefined;
  isLoading: boolean;
}) {
  const priceChange = latestPriceChange(latestPrice?.change_rate, latestPrice?.change_code);
  return (
    <div className="company-price" aria-busy={isLoading}>
      <strong>{isLoading && !latestPrice ? "..." : formatNumber(latestPrice?.close)}</strong>
      <small className={`price-change ${priceChange.className}`}>
        {isLoading && !latestPrice ? "" : priceChange.label}
      </small>
    </div>
  );
}

function latestPriceChange(
  value: number | null | undefined,
  changeCode: string | null | undefined
) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return { className: "price-change-flat", label: "-" };
  }
  const codeDisplay = priceChangeDisplayFromCode(changeCode);
  if (codeDisplay) {
    return {
      className: codeDisplay.className,
      label: codeDisplay.symbol
        ? `${codeDisplay.symbol} ${formatSignedPercent(value)}`
        : formatSignedPercent(value)
    };
  }
  if (value <= -0.3) {
    return {
      className: "price-change-down limit-change",
      label: `▼ ${formatSignedPercent(value)}`
    };
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

function priceChangeDisplayFromCode(changeCode: string | null | undefined) {
  switch (changeCode) {
    case "1":
      return { className: "price-change-up limit-change", symbol: "▲" };
    case "2":
      return { className: "price-change-up", symbol: "△" };
    case "3":
      return { className: "price-change-flat", symbol: "" };
    case "4":
      return { className: "price-change-down limit-change", symbol: "▼" };
    case "5":
      return { className: "price-change-down", symbol: "▽" };
    default:
      return null;
  }
}

const DisclosureReaction = memo(function DisclosureReaction({ event }: { event: EnrichedEvent }) {
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
        {DATA_QUALITY_LABELS[relative.quality]} · 단순 {simple.label}:{" "}
        {formatSignedPercent(simple.value)}
      </small>
    </div>
  );
});

const DisclosureSourceLink = memo(function DisclosureSourceLink({
  event
}: {
  event: EnrichedEvent;
}) {
  const url = event.source_url ?? dartUrl(event.rcept_no);
  if (!url) {
    return <span className="muted">원문 없음</span>;
  }
  return (
    <a className="source-link" href={url} target="_blank" rel="noreferrer">
      원문
    </a>
  );
});

function pickPrimaryHolding(
  snapshots: TreasuryHoldingSnapshot[]
): TreasuryHoldingSnapshot | undefined {
  const latestDate = snapshots[snapshots.length - 1]?.as_of_date;
  if (!latestDate) {
    return undefined;
  }
  const latestSnapshots = snapshots.filter((snapshot) => snapshot.as_of_date === latestDate);
  return latestSnapshots.find(isCommonHoldingKind) ?? latestSnapshots[latestSnapshots.length - 1];
}

const EventDetailLines = memo(function EventDetailLines({
  event,
  latestPrice
}: {
  event: EnrichedEvent;
  latestPrice: LatestPriceSnapshot | undefined;
}) {
  const details = eventDetailLines(event, latestPrice);
  if (details.length === 0) {
    return null;
  }
  return <small>{details.join(" · ")}</small>;
});

function eventDetailLines(event: EnrichedEvent, latestPrice: LatestPriceSnapshot | undefined) {
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

  const marketCap = marketCapFrom(
    latestPrice ?? event.latestPrice ?? event.priceReaction,
    event.holding
  );
  const stake = plannedEventStake(event, marketCap.amount);
  if (stake !== null) {
    lines.push(
      `${event.event_type === "retirement" ? "소각지분" : "예정취득지분"} ${formatPercent(stake, 2)}`
    );
  }
  if (event.event_type === "retirement" && event.planned_share_ratio_other != null) {
    lines.push(`종류주식 소각지분 ${formatPercent(event.planned_share_ratio_other, 2)}`);
  }
  return lines;
}

const ExecutionSummary = memo(function ExecutionSummary({ event }: { event: EnrichedEvent }) {
  const execution = event.execution;
  if (!execution) {
    return null;
  }

  const { status, reason } = executionStatus(execution);
  const url = execution.source_url ?? dartUrl(execution.rcept_no);

  if (execution.execution_type === "trust_status") {
    const rate = completionRate(event, execution);
    return (
      <div className="execution-progress">
        <div className="disclosure-meta">
          <span>신탁 이행 현황</span>
          {status ? (
            <span
              className={`status-badge status-${statusClassName(status)}`}
              title={status === "미달" ? (reason ?? undefined) : undefined}
            >
              {status}
            </span>
          ) : null}
        </div>
        <meter max={1} min={0} value={rate ?? 0}>
          {formatPercent(rate)}
        </meter>
        <small>
          누적 {formatNumber(execution.actual_shares)}주 · {formatKRW(execution.actual_amount_krw)}
          원 · 진행률 {formatPercent(rate)} · 기준일 {execution.as_of_date}
          {url ? (
            <>
              {" · "}
              <a className="source-link" href={url} target="_blank" rel="noreferrer">
                원문
              </a>
            </>
          ) : null}
        </small>
      </div>
    );
  }

  const rate = completionRate(event, execution);
  return (
    <div
      className="execution-summary"
      title={status === "미달" ? (reason ?? undefined) : undefined}
    >
      <span>
        실제 {execution.execution_type === "disposition_result" ? "처분" : "취득"}{" "}
        <strong>{formatNumber(execution.actual_shares)}주</strong> ·{" "}
        <strong>{formatKRW(execution.actual_amount_krw)}</strong> · 이행률{" "}
        <strong>{formatPercent(rate)}</strong>
        {status ? (
          <span className={`status-badge status-${statusClassName(status)}`}> {status}</span>
        ) : null}
      </span>
      {url ? (
        <a className="source-link" href={url} target="_blank" rel="noreferrer">
          결과보고서 원문
        </a>
      ) : null}
    </div>
  );
});

function statusClassName(status: "완료" | "미달" | "진행중") {
  if (status === "완료") return "complete";
  if (status === "미달") return "shortfall";
  return "in-progress";
}

const UnlinkedExecutionsSection = memo(function UnlinkedExecutionsSection({
  executions
}: {
  executions: BuybackExecution[];
}) {
  if (executions.length === 0) {
    return null;
  }
  return (
    <section className="detail-section unlinked-executions">
      <h3>미연결 결과보고서</h3>
      <p className="empty-copy">
        이벤트 공시와 자동으로 연결되지 않은 이행 결과보고서입니다. 종목코드로만 매칭되어 있습니다.
      </p>
      <ol className="disclosure-list">
        {executions.map((execution) => {
          const url = execution.source_url ?? dartUrl(execution.rcept_no);
          const { status, reason } = executionStatus(execution);
          return (
            <li key={execution.execution_id}>
              <div className="disclosure-meta">
                <time>{execution.disclosure_date}</time>
                <span className="event-chip">
                  {EXECUTION_TYPE_LABELS[execution.execution_type]}
                </span>
              </div>
              <div className="event-timeline-copy">
                <p>{execution.raw_report_name ?? "결과보고서"}</p>
                <small>
                  실제 {formatNumber(execution.actual_shares)}주 ·{" "}
                  {formatKRW(execution.actual_amount_krw)}원
                  {status ? (
                    <>
                      {" · "}
                      <span
                        className={`status-badge status-${statusClassName(status)}`}
                        title={status === "미달" ? (reason ?? undefined) : undefined}
                      >
                        {status}
                      </span>
                    </>
                  ) : null}
                </small>
              </div>
              <span className="muted">기준일 {execution.as_of_date}</span>
              {url ? (
                <a className="source-link" href={url} target="_blank" rel="noreferrer">
                  원문
                </a>
              ) : (
                <span className="muted">원문 없음</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
});

const EXECUTION_TYPE_LABELS: Record<BuybackExecution["execution_type"], string> = {
  acquisition_result: "취득결과",
  disposition_result: "처분결과",
  trust_status: "신탁현황"
};

function formatHoldingLabel(snapshot: TreasuryHoldingSnapshot) {
  return snapshot.stock_kind
    ? `${snapshot.as_of_date} ${snapshot.stock_kind}`
    : snapshot.as_of_date;
}

function holdingBarWidth(ratio: number | null, maxRatio: number) {
  if (ratio === null || ratio <= 0 || maxRatio <= 0) {
    return 0;
  }
  return Math.min(100, Math.max((ratio / maxRatio) * 100, 3));
}
