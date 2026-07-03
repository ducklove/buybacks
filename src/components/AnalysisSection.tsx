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
