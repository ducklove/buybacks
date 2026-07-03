import { useMemo, useState } from "react";
import {
  CAR_MARKETS,
  EVENT_TYPES,
  type CarCurveGroup,
  type CarCurves,
  type CarMarket,
  type EventType
} from "../types/buybacks";
import { EVENT_TYPE_LABELS, formatSignedPercent } from "../utils/format";

export const DEFAULT_CAR_EVENT_TYPES: EventType[] = ["direct_acquisition", "retirement"];

interface LineStyle {
  color: string;
  dash?: string;
}

/** 색약 대비를 위해 이벤트 유형마다 색상과 대시 패턴을 병용한다. */
const LINE_STYLES: Record<EventType, LineStyle> = {
  direct_acquisition: { color: "var(--teal)" },
  retirement: { color: "var(--amber)", dash: "7 4" },
  direct_disposition: { color: "var(--orange)", dash: "2 3" },
  trust_contract_start: { color: "var(--price-down)", dash: "9 3 2 3" },
  trust_contract_end: { color: "var(--green)", dash: "4 4" },
  periodic_holding_update: { color: "var(--neutral-tone)", dash: "1 3" },
  unknown: { color: "var(--muted)", dash: "3 5" }
};

const WIDTH = 720;
const HEIGHT = 300;
const MARGIN = { top: 14, right: 18, bottom: 32, left: 56 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;
const X_TICKS = [1, 10, 20, 30, 40, 50, 60];

interface CarCurveChartProps {
  carCurves: CarCurves | null;
}

export function CarCurveChart({ carCurves }: CarCurveChartProps) {
  const [market, setMarket] = useState<CarMarket>("ALL");
  const [selectedTypes, setSelectedTypes] = useState<EventType[]>(DEFAULT_CAR_EVENT_TYPES);

  const groups = useMemo(() => carCurves?.groups ?? [], [carCurves]);
  const availableTypes = useMemo(() => {
    const present = new Set(groups.map((group) => group.event_type));
    return EVENT_TYPES.filter((type) => present.has(type));
  }, [groups]);

  const visibleGroups = useMemo(
    () =>
      groups.filter((group) => group.market === market && selectedTypes.includes(group.event_type)),
    [groups, market, selectedTypes]
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
          <h2>CAR 곡선</h2>
        </div>
        <p>이벤트 유형별 공시 후 평균 누적초과수익률(CAR)입니다. x축은 t+1부터의 거래일입니다.</p>
      </header>
      {carCurves === null || groups.length === 0 ? (
        <p className="empty-copy analysis-empty">
          CAR 곡선 데이터가 아직 없습니다. 가격 시계열 보강 후 표시됩니다.
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
            <div className="event-type-filter">
              <span>이벤트 유형</span>
              <div className="event-type-options" role="group" aria-label="CAR 이벤트 유형">
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
          {visibleGroups.length === 0 ? (
            <p className="empty-copy analysis-empty">
              선택한 조건에 해당하는 그룹이 없습니다. 시장이나 이벤트 유형을 바꿔보세요.
            </p>
          ) : (
            <CarSvg carCurves={carCurves} groups={visibleGroups} />
          )}
        </>
      )}
    </article>
  );
}

function CarSvg({ carCurves, groups }: { carCurves: CarCurves; groups: CarCurveGroup[] }) {
  const window = Math.max(
    1,
    Math.min(carCurves.window || 60, Math.max(...groups.map((group) => group.mean_car.length), 1))
  );

  const values = groups.flatMap((group) =>
    group.mean_car.slice(0, window).filter((value): value is number => value !== null)
  );
  if (values.length === 0) {
    return <p className="empty-copy analysis-empty">선택한 그룹에 표시할 수 있는 값이 없습니다.</p>;
  }

  const rawMin = Math.min(...values, 0);
  const rawMax = Math.max(...values, 0);
  const pad = Math.max((rawMax - rawMin) * 0.08, 0.002);
  const yMin = rawMin - pad;
  const yMax = rawMax + pad;

  const xOf = (k: number) =>
    MARGIN.left + (window === 1 ? PLOT_WIDTH / 2 : ((k - 1) / (window - 1)) * PLOT_WIDTH);
  const yOf = (value: number) =>
    MARGIN.top + PLOT_HEIGHT - ((value - yMin) / (yMax - yMin)) * PLOT_HEIGHT;

  const yTicks = buildTicks(yMin, yMax);
  const xTicks = X_TICKS.filter((k) => k <= window);
  const columnWidth = window === 1 ? PLOT_WIDTH : PLOT_WIDTH / (window - 1);

  return (
    <>
      <div className="car-chart">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="이벤트 유형별 공시 후 평균 누적초과수익률(CAR) 곡선 차트"
          preserveAspectRatio="xMidYMid meet"
        >
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                className="car-grid-line"
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={yOf(tick)}
                y2={yOf(tick)}
              />
              <text
                className="car-tick-label"
                x={MARGIN.left - 8}
                y={yOf(tick) + 4}
                textAnchor="end"
              >
                {(tick * 100).toFixed(1)}%
              </text>
            </g>
          ))}
          <line
            className="car-zero-line"
            x1={MARGIN.left}
            x2={WIDTH - MARGIN.right}
            y1={yOf(0)}
            y2={yOf(0)}
          />
          {xTicks.map((k) => (
            <text
              className="car-tick-label"
              key={k}
              x={xOf(k)}
              y={HEIGHT - MARGIN.bottom + 18}
              textAnchor="middle"
            >
              t+{k}
            </text>
          ))}
          {groups.map((group) => {
            const style = LINE_STYLES[group.event_type] ?? LINE_STYLES.unknown;
            return (
              <path
                className="car-line"
                key={`${group.event_type}-${group.market}`}
                d={buildLinePath(group.mean_car, window, xOf, yOf)}
                style={{ stroke: style.color, strokeDasharray: style.dash }}
              />
            );
          })}
          {Array.from({ length: window }, (_, index) => index + 1).map((k) => (
            <rect
              key={k}
              x={xOf(k) - columnWidth / 2}
              y={MARGIN.top}
              width={columnWidth}
              height={PLOT_HEIGHT}
              fill="transparent"
            >
              <title>{tooltipFor(k, groups)}</title>
            </rect>
          ))}
        </svg>
      </div>
      <ul className="car-legend">
        {groups.map((group) => {
          const style = LINE_STYLES[group.event_type] ?? LINE_STYLES.unknown;
          return (
            <li key={`${group.event_type}-${group.market}`}>
              <svg width="28" height="10" aria-hidden="true">
                <line
                  x1={2}
                  x2={26}
                  y1={5}
                  y2={5}
                  strokeWidth={2.5}
                  style={{ stroke: style.color, strokeDasharray: style.dash }}
                />
              </svg>
              <span>
                {EVENT_TYPE_LABELS[group.event_type] ?? group.event_type} (n={group.n})
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function buildLinePath(
  meanCar: Array<number | null>,
  window: number,
  xOf: (k: number) => number,
  yOf: (value: number) => number
): string {
  const segments: string[] = [];
  let penDown = false;
  for (let k = 1; k <= window; k += 1) {
    const value = meanCar[k - 1];
    if (value === null || value === undefined) {
      penDown = false;
      continue;
    }
    const command = penDown ? "L" : "M";
    segments.push(`${command}${xOf(k).toFixed(2)} ${yOf(value).toFixed(2)}`);
    penDown = true;
  }
  return segments.join(" ");
}

function tooltipFor(k: number, groups: CarCurveGroup[]): string {
  const lines = groups.map((group) => {
    const value = group.mean_car[k - 1];
    const label = EVENT_TYPE_LABELS[group.event_type] ?? group.event_type;
    return `${label} (n=${group.n}): ${value === null || value === undefined ? "-" : formatSignedPercent(value, 2)}`;
  });
  return [`t+${k} 거래일`, ...lines].join("\n");
}

function buildTicks(min: number, max: number): number[] {
  const span = max - min;
  const roughStep = span / 4;
  const power = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const normalized = roughStep / power;
  const step = (normalized >= 5 ? 5 : normalized >= 2 ? 2 : 1) * power;
  const ticks: number[] = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + step / 1000; tick += step) {
    ticks.push(Math.abs(tick) < step / 1000 ? 0 : tick);
  }
  return ticks;
}
