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
        <a
          className="github-link"
          href="https://github.com/ducklove/buybacks"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
      </header>
      {children}
    </div>
  );
}
