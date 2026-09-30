import { useEffect, useState, type ReactNode } from "react";
import { applyTheme, currentTheme, THEME_CHANGE_EVENT, type Theme } from "../utils/vcShell";

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

/**
 * 현재 테마를 추적한다. 셸 바의 토글·다른 탭(storage)·허브 iframe 메시지로 바뀐 테마도
 * vc-shell.js가 'vc:themechange'로 알려 주므로 이 이벤트 하나만 구독하면 된다.
 */
function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  useEffect(() => {
    const onChange = (event: CustomEvent<{ theme: Theme }>) => {
      setTheme(event.detail?.theme === "dark" ? "dark" : "light");
    };
    document.addEventListener(THEME_CHANGE_EVENT, onChange);
    return () => document.removeEventListener(THEME_CHANGE_EVENT, onChange);
  }, []);
  // 부트 스크립트·셸이 설정한 data-theme에서 이어서 전환한다(상태가 뒤처져 있어도 안전).
  const toggle = () => setTheme(applyTheme(currentTheme() === "dark" ? "light" : "dark"));
  return [theme, toggle];
}

export function Shell({ children }: ShellProps) {
  const [theme, toggleTheme] = useTheme();
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
            <strong>자사주 분석</strong>
            <small className="brand-sub">Buybacks</small>
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
            title={theme === "dark" ? "라이트 테마로 전환" : "다크 테마로 전환"}
            aria-label="테마 전환"
            aria-pressed={theme === "dark"}
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
