import type { DataStatus } from "../types/buybacks";

interface DataStatusBannerProps {
  status: DataStatus;
}

export function DataStatusBanner({ status }: DataStatusBannerProps) {
  const generatedAt = new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(status.generated_at));
  const priceSource = status.price_source ?? (status.krx_available ? "krx" : "missing");

  return (
    <aside className="status-banner" aria-label="Data refresh status">
      <div>
        <span className="status-dot" data-active={status.dart_available} />
        DART {status.dart_available ? "live" : "fixture"}
      </div>
      <div>
        <span className="status-dot" data-active={priceSource !== "missing"} />
        Price {priceSource}
      </div>
      <div>Updated {generatedAt}</div>
    </aside>
  );
}
