import type { DataStatus } from "../types/buybacks";

interface MethodologyProps {
  status: DataStatus;
}

export function Methodology({ status }: MethodologyProps) {
  return (
    <section className="methodology" id="methodology">
      <header>
        <h2>Methodology / Data Source</h2>
        <p>
          This dashboard keeps disclosure facts, holdings, and price reactions separate so missing
          market data stays visible.
        </p>
      </header>
      <div className="method-grid">
        <article>
          <h3>OpenDART</h3>
          <p>
            Official disclosure metadata, treasury-stock decisions, trust contracts, retirements,
            and periodic treasury-stock holdings.
          </p>
        </article>
        <article>
          <h3>kis_proxy</h3>
          <p>
            Daily stock and index history for return windows. When the proxy is unavailable,
            reaction metrics remain null instead of being filled with an unofficial replacement.
          </p>
        </article>
        <article>
          <h3>Quality</h3>
          <p>
            Returns are marked complete, partial, or missing according to the available trading-day
            window.
          </p>
        </article>
      </div>
      {status.warnings.length > 0 && (
        <ul className="warning-list" aria-label="Data warnings">
          {status.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
