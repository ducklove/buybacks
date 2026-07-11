import { useEffect, useState } from "react";
import { loadAnalysisDataset, type AnalysisDataset } from "../data/loadBuybacks";
import { useVisibleOnce } from "../hooks/useVisibleOnce";
import type { BuybackEvent, CarCurves, Company, ReactionSeries } from "../types/buybacks";
import { BacktestPanel } from "./BacktestPanel";
import { CarCurveChart } from "./CarCurveChart";

interface AnalysisSectionProps {
  carCurves: CarCurves | null;
  reactionSeries: ReactionSeries[];
  events: BuybackEvent[];
  companies: Company[];
}

export function AnalysisSection({
  carCurves,
  reactionSeries,
  events,
  companies
}: AnalysisSectionProps) {
  return (
    <section className="analysis-section" id="analysis" aria-label="이벤트 스터디 분석">
      <CarCurveChart carCurves={carCurves} />
      <BacktestPanel reactionSeries={reactionSeries} events={events} companies={companies} />
    </section>
  );
}

interface LazyAnalysisSectionProps {
  events: BuybackEvent[];
  companies: Company[];
}

/**
 * 분석 섹션이 뷰포트에 접근할 때 reaction_series/car_curves(합계 약 5.9MB)를
 * 지연 로드하는 컨테이너. 첫 화면(대시보드) 렌더는 이 데이터를 요청하지 않는다.
 */
export function LazyAnalysisSection({ events, companies }: LazyAnalysisSectionProps) {
  const { ref, visible } = useVisibleOnce<HTMLElement>("400px 0px");
  const [data, setData] = useState<AnalysisDataset | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || data || error) return;
    let cancelled = false;
    loadAnalysisDataset()
      .then((loaded) => {
        if (!cancelled) setData(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [visible, data, error]);

  if (data) {
    return (
      <AnalysisSection
        carCurves={data.carCurves}
        reactionSeries={data.reactionSeries}
        events={events}
        companies={companies}
      />
    );
  }

  return (
    <section
      className="analysis-section"
      id="analysis"
      aria-label="이벤트 스터디 분석"
      ref={ref}
    >
      {error ? (
        <div className="empty-state" role="alert">
          <p>분석 데이터를 불러오지 못했습니다.</p>
          <p className="muted">{error}</p>
          <button className="secondary-button" type="button" onClick={() => setError(null)}>
            다시 시도
          </button>
        </div>
      ) : (
        <div className="loading-panel" aria-live="polite">
          <div className="loading-bar" />
          <p>분석 데이터를 불러오는 중입니다.</p>
        </div>
      )}
    </section>
  );
}
