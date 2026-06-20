import type { KpiMetric } from "../utils/metrics";

interface KpiGridProps {
  metrics: KpiMetric[];
}

export function KpiGrid({ metrics }: KpiGridProps) {
  return (
    <section className="kpi-grid" aria-label="요약 지표">
      {metrics.map((metric) => (
        <article className="kpi-card" data-tone={metric.tone} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <small>{metric.detail}</small>
        </article>
      ))}
    </section>
  );
}

