import type { EnrichedEvent, PriceReaction, TreasuryHoldingSnapshot } from "../types/buybacks";
import { EVENT_TYPE_LABELS } from "../utils/format";
import {
  eventTypeCounts,
  returnDistribution,
  topHoldings,
  yearlyEventCounts,
  type ChartDatum
} from "../utils/metrics";

interface DashboardChartsProps {
  events: EnrichedEvent[];
  holdings: TreasuryHoldingSnapshot[];
  reactions: PriceReaction[];
}

export function DashboardCharts({ events, holdings, reactions }: DashboardChartsProps) {
  return (
    <section className="charts-grid" aria-label="대시보드 차트">
      <ChartPanel title="연도별 이벤트 건수" summary="공시일 기준 이벤트 수입니다.">
        <VerticalBars data={yearlyEventCounts(events)} />
      </ChartPanel>
      <ChartPanel title="이벤트 유형 분포" summary="현재 필터에 포함된 이벤트 유형 비중입니다.">
        <DistributionList
          data={eventTypeCounts(events).map((item) => ({
            ...item,
            label: EVENT_TYPE_LABELS[item.label as keyof typeof EVENT_TYPE_LABELS] ?? item.label
          }))}
        />
      </ChartPanel>
      <ChartPanel title="보유비율 상위 종목" summary="최근 정기보고서 기준 자기주식 보유비율입니다.">
        <HorizontalBars data={topHoldings(holdings, 8)} percent />
      </ChartPanel>
      <ChartPanel title="+20D 수익률 분포" summary="가격 데이터가 있는 이벤트만 집계합니다.">
        <VerticalBars data={returnDistribution(reactions)} compact />
      </ChartPanel>
    </section>
  );
}

function ChartPanel({
  title,
  summary,
  children
}: {
  title: string;
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <article className="chart-panel">
      <header>
        <h2>{title}</h2>
        <p>{summary}</p>
      </header>
      {children}
    </article>
  );
}

function VerticalBars({ data, compact = false }: { data: ChartDatum[]; compact?: boolean }) {
  const max = Math.max(...data.map((item) => item.value), 1);
  return (
    <div className={compact ? "vertical-bars compact-bars" : "vertical-bars"}>
      {data.map((item) => (
        <div className="bar-column" key={item.label}>
          <div className="bar-value">{item.value}</div>
          <div className="bar-track" aria-hidden="true">
            <span style={{ height: `${(item.value / max) * 100}%` }} />
          </div>
          <span className="bar-label">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function HorizontalBars({ data, percent = false }: { data: ChartDatum[]; percent?: boolean }) {
  const max = Math.max(...data.map((item) => item.value), 0.01);
  return (
    <div className="horizontal-bars">
      {data.map((item) => (
        <div className="hbar-row" key={item.label}>
          <span>{item.label}</span>
          <div className="hbar-track" aria-hidden="true">
            <i style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
          <strong>{percent ? `${(item.value * 100).toFixed(2)}%` : item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function DistributionList({ data }: { data: ChartDatum[] }) {
  const total = data.reduce((sum, item) => sum + item.value, 0) || 1;
  return (
    <div className="distribution-list">
      {data.map((item) => (
        <div className="distribution-row" key={item.label}>
          <span>{item.label}</span>
          <meter min={0} max={total} value={item.value}>
            {item.value}
          </meter>
          <strong>{((item.value / total) * 100).toFixed(1)}%</strong>
        </div>
      ))}
    </div>
  );
}

