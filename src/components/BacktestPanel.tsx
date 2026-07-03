import { useMemo, useState } from "react";
import {
  CAR_MARKETS,
  EVENT_TYPES,
  type BuybackEvent,
  type CarMarket,
  type Company,
  type EventType,
  type ReactionSeries
} from "../types/buybacks";
import {
  HOLDING_PERIODS,
  availableBacktestYears,
  buildBacktestItems,
  runBacktest,
  type HoldingPeriod,
  type ReturnBasis
} from "../utils/backtest";
import { EVENT_TYPE_LABELS, formatPercent, formatSignedPercent } from "../utils/format";
import { DEFAULT_CAR_EVENT_TYPES } from "./CarCurveChart";

interface BacktestPanelProps {
  reactionSeries: ReactionSeries[];
  events: BuybackEvent[];
  companies: Company[];
}

export function BacktestPanel({ reactionSeries, events, companies }: BacktestPanelProps) {
  const [selectedTypes, setSelectedTypes] = useState<EventType[]>(DEFAULT_CAR_EVENT_TYPES);
  const [market, setMarket] = useState<CarMarket>("ALL");
  const [holdDays, setHoldDays] = useState<HoldingPeriod>(20);
  const [basis, setBasis] = useState<ReturnBasis>("simple");
  const [year, setYear] = useState("ALL");

  const items = useMemo(
    () => buildBacktestItems(reactionSeries, events, companies),
    [reactionSeries, events, companies]
  );
  const years = useMemo(() => availableBacktestYears(reactionSeries), [reactionSeries]);
  const availableTypes = useMemo(() => {
    const present = new Set(
      items.map((item) => item.eventType).filter((type): type is EventType => type !== null)
    );
    return EVENT_TYPES.filter((type) => present.has(type));
  }, [items]);

  const result = useMemo(
    () => runBacktest(items, { eventTypes: selectedTypes, market, year, holdDays, basis }),
    [items, selectedTypes, market, year, holdDays, basis]
  );

  const toggleType = (type: EventType) => {
    setSelectedTypes((current) =>
      current.includes(type) ? current.filter((item) => item !== type) : [...current, type]
    );
  };

  return (
    <article className="chart-panel analysis-panel">
      <header>
        <div className="chart-heading">
          <h2>간이 백테스트</h2>
        </div>
        <p>공시 후 첫 거래일(t0) 종가 매수 → N 거래일 보유 전략의 수익률 분포 요약입니다.</p>
      </header>
      {reactionSeries.length === 0 ? (
        <p className="empty-copy analysis-empty">
          수익률 시계열 데이터가 아직 없습니다. 가격 시계열 보강 후 표시됩니다.
        </p>
      ) : (
        <>
          <div className="analysis-controls">
            <label>
              시장
              <select
                value={market}
                onChange={(event) => setMarket(event.target.value as CarMarket)}
              >
                {CAR_MARKETS.map((option) => (
                  <option value={option} key={option}>
                    {option === "ALL" ? "전체 시장" : option}
                  </option>
                ))}
              </select>
            </label>
            <label>
              보유기간
              <select
                value={holdDays}
                onChange={(event) => setHoldDays(Number(event.target.value) as HoldingPeriod)}
              >
                {HOLDING_PERIODS.map((period) => (
                  <option value={period} key={period}>
                    {period}거래일
                  </option>
                ))}
              </select>
            </label>
            <label>
              수익률 기준
              <select
                value={basis}
                onChange={(event) => setBasis(event.target.value as ReturnBasis)}
              >
                <option value="simple">단순수익률</option>
                <option value="abnormal">지수대비</option>
              </select>
            </label>
            <label>
              연도
              <select value={year} onChange={(event) => setYear(event.target.value)}>
                <option value="ALL">전체 기간</option>
                {years.map((option) => (
                  <option value={option} key={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <div className="event-type-filter">
              <span>이벤트 유형</span>
              <div className="event-type-options" role="group" aria-label="백테스트 이벤트 유형">
                <button
                  className={
                    selectedTypes.length === 0
                      ? "filter-toggle active-filter-toggle"
                      : "filter-toggle"
                  }
                  type="button"
                  aria-pressed={selectedTypes.length === 0}
                  onClick={() => setSelectedTypes([])}
                >
                  전체
                </button>
                {availableTypes.map((type) => {
                  const active = selectedTypes.includes(type);
                  return (
                    <button
                      className={active ? "filter-toggle active-filter-toggle" : "filter-toggle"}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleType(type)}
                      key={type}
                    >
                      {EVENT_TYPE_LABELS[type]}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          {result.n === 0 ? (
            <p className="empty-copy analysis-empty">
              조건에 맞는 이벤트가 없습니다. 필터나 보유기간을 조정해 보세요.
            </p>
          ) : (
            <>
              <div className="detail-metrics backtest-metrics">
                <div>
                  <span>평균</span>
                  <strong>{formatSignedPercent(result.mean)}</strong>
                  <small>
                    +{holdDays}D {basis === "simple" ? "단순" : "지수대비"} 누적
                  </small>
                </div>
                <div>
                  <span>중앙값</span>
                  <strong>{formatSignedPercent(result.median)}</strong>
                  <small>표본 중앙 수익률</small>
                </div>
                <div>
                  <span>승률</span>
                  <strong>{formatPercent(result.winRate, 1)}</strong>
                  <small>수익률 &gt; 0 비중</small>
                </div>
                <div>
                  <span>표본수</span>
                  <strong>{result.n}건</strong>
                  <small>
                    최고 {formatSignedPercent(result.best)} · 최저{" "}
                    {formatSignedPercent(result.worst)}
                  </small>
                </div>
              </div>
              <BacktestHistogram
                distribution={result.distribution}
                ariaLabel={`보유기간 ${holdDays}거래일 수익률 분포 히스토그램`}
              />
            </>
          )}
          <p className="muted backtest-disclaimer">
            과거 공시 후 수익률 분포의 요약이며 투자 성과를 보장하지 않습니다. 거래비용·호가
            슬리피지 미반영.
          </p>
        </>
      )}
    </article>
  );
}

function BacktestHistogram({
  distribution,
  ariaLabel
}: {
  distribution: Array<{ label: string; from: number; count: number }>;
  ariaLabel: string;
}) {
  const max = Math.max(...distribution.map((bucket) => bucket.count), 1);
  return (
    <div className="vertical-bars compact-bars backtest-bars" aria-label={ariaLabel}>
      {distribution.map((bucket) => (
        <div className="bar-column" key={bucket.label} title={`${bucket.label}: ${bucket.count}건`}>
          <div className="bar-value">{bucket.count}</div>
          <div className="bar-track" aria-hidden="true">
            <span style={{ height: `${(bucket.count / max) * 100}%` }} />
          </div>
          <span className="bar-label">{`${(bucket.from * 100).toFixed(1)}%`}</span>
        </div>
      ))}
    </div>
  );
}
