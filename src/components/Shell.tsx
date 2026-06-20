import type { ReactNode } from "react";

interface ShellProps {
  children: ReactNode;
}

const navItems = [
  { label: "Dashboard", target: "dashboard" },
  { label: "Events", target: "events" },
  { label: "Company", target: "company" },
  { label: "Methodology", target: "methodology" }
];

export function Shell({ children }: ShellProps) {
  const scrollToSection = (target: string) => {
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={() => scrollToSection("dashboard")}>
          <span>value-invest</span>
          <span aria-hidden="true">/</span>
          <strong>buybacks</strong>
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
        <a className="github-link" href="https://github.com" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </header>
      {children}
    </div>
  );
}

