import type { DataStatus } from "../types/buybacks";

interface DataStatusBannerProps {
  status: DataStatus;
}

export function DataStatusBanner({ status }: DataStatusBannerProps) {
  const generatedAt = new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(status.generated_at));

  return (
    <aside className="status-banner" aria-label="데이터 갱신 상태">
      <div>
        <span className="status-dot" data-active={status.dart_available} />
        DART {status.dart_available ? "연결" : "fixture"}
      </div>
      <div>
        <span className="status-dot" data-active={status.krx_available} />
        KRX {status.krx_available ? "연결" : "대기"}
      </div>
      <div>기준 {generatedAt}</div>
    </aside>
  );
}

