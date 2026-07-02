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
    <aside className="status-banner" aria-label="데이터 갱신 상태">
      <div>
        <span className="status-dot" data-active={status.dart_available} />
        DART {status.dart_available ? "실시간" : "고정 데이터"}
      </div>
      <div>
        <span className="status-dot" data-active={priceSource !== "missing"} />
        시세 {priceSourceLabel(priceSource)}
      </div>
      <div>갱신 {generatedAt}</div>
    </aside>
  );
}

function priceSourceLabel(priceSource: string) {
  switch (priceSource) {
    case "kis_proxy":
      return "kis_proxy";
    case "krx":
      return "KRX";
    case "fixture":
      return "고정 데이터";
    case "missing":
      return "없음";
    default:
      return priceSource;
  }
}
