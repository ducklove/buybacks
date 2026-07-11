import type { ReactNode } from "react";

interface ShellProps {
  children: ReactNode;
}

const navItems = [
  { label: "대시보드", target: "dashboard" },
  { label: "분석", target: "analysis" },
  { label: "이벤트", target: "events" },
  { label: "스크리너", target: "screener" },
  { label: "기업 상세", target: "company" },
  { label: "방법론", target: "methodology" }
];

/** data-theme 미설정이면 OS 선호(prefers-color-scheme)를 현재 테마로 간주한다. */
function currentTheme(): "dark" | "light" {
  const applied = document.documentElement.dataset.theme;
  if (applied === "dark" || applied === "light") return applied;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** 생태계 공통 계약: html[data-theme] 반영 + localStorage 'theme' 키에 저장. */
function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("theme", next);
  } catch {
    /* 프라이빗 모드 등 저장 불가 시 세션 내 전환만 유지 */
  }
}

export function Shell({ children }: ShellProps) {
  const scrollToSection = (target: string) => {
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={() => scrollToSection("dashboard")}>
          <img
            className="brand-icon"
            src={`${import.meta.env.BASE_URL}buybacks-icon.svg`}
            alt=""
            aria-hidden="true"
          />
          <span className="brand-text">
            <strong>Buybacks</strong>
          </span>
        </button>
        <nav aria-label="Primary navigation">
          {navItems.map((item, index) => (
            <button
              className={index === 0 ? "nav-link nav-link-active" : "nav-link"}
              key={item.target}
              type="button"
              onClick={() => scrollToSection(item.target)}
            >
              {item.label}
            </button>
          ))}
          <a className="hub-link" href="https://cantabile.tplinkdns.com:3691" rel="noopener">
            Value Compass ↗
          </a>
        </nav>
        <div className="topbar-actions">
          <a
            className="github-link"
            href="https://github.com/ducklove/buybacks"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
          <button
            className="theme-toggle"
            type="button"
            title="테마 전환"
            aria-label="테마 전환"
            onClick={toggleTheme}
          >
            🌓
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
