// Value Compass 생태계 바(public/vc-shell.js, index.html의 <vc-shell>)와의 얇은 연결부.
// vc-shell.js는 React 밖에서 로드되는 classic script라 없을 수도 있다(차단·로드 실패·테스트).
// 그래서 모든 호출은 window.VCShell 존재 여부를 확인하고, 없으면 조용히 기존 동작으로 폴백한다.

export type Theme = "light" | "dark";

interface VCShellApi {
  version: string;
  getTheme(): Theme;
  setTheme(theme: Theme | "auto"): Theme;
  setStock(code: string | null, name?: string | null): void;
  hubAnalysisUrl(code: string): string | null;
}

declare global {
  interface Window {
    VCShell?: VCShellApi;
  }
  interface DocumentEventMap {
    "vc:themechange": CustomEvent<{ theme: Theme }>;
  }
}

export const THEME_CHANGE_EVENT = "vc:themechange";

function shell(): VCShellApi | undefined {
  return typeof window === "undefined" ? undefined : window.VCShell;
}

/** html[data-theme]가 없으면 OS 선호(prefers-color-scheme)를 현재 테마로 간주한다. */
export function currentTheme(): Theme {
  const applied = document.documentElement.dataset.theme;
  if (applied === "dark" || applied === "light") return applied;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * 생태계 공통 테마 계약으로 테마를 바꾼다. 셸이 있으면 VCShell.setTheme(저장·?theme 정리·
 * 'vc:themechange' 발행)을 쓰고, 없으면 html[data-theme] + localStorage 'theme'에 직접 쓴 뒤
 * 같은 이벤트를 발행해 구독자가 한 경로만 보면 되게 한다.
 */
export function applyTheme(next: Theme): Theme {
  const api = shell();
  if (api) return api.setTheme(next);
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("theme", next);
  } catch {
    /* 프라이빗 모드 등 저장 불가 시 세션 내 전환만 유지 */
  }
  document.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: { theme: next } }));
  return next;
}

/** 셸 바에 현재 종목을 알린다('허브에서 분석 ↗' 칩). null이면 해제한다. */
export function setShellStock(code: string | null, name?: string | null) {
  shell()?.setStock(code || null, code ? (name ?? null) : null);
}
