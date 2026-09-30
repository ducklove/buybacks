import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

describe("Shell", () => {
  it("renders the GitHub repository link and leaves the hub link to the <vc-shell> bar", () => {
    render(<Shell>본문</Shell>);

    // 허브 링크는 index.html 의 <vc-shell tool="buybacks"> (React 트리 밖) 가 담당한다.
    expect(screen.queryByRole("link", { name: "Value Compass ↗" })).toBeNull();

    const githubLink = screen.getByRole("link", { name: "GitHub" });
    expect(githubLink).toHaveAttribute("href", "https://github.com/ducklove/buybacks");
  });

  it("브랜드 텍스트가 한국어 서비스명 '자사주 분석' 을 표시한다", () => {
    const { container } = render(<Shell>본문</Shell>);

    const brandText = container.querySelector(".brand .brand-text");
    expect(brandText?.querySelector("strong")?.textContent).toBe("자사주 분석");
    expect(brandText?.querySelector(".brand-sub")?.textContent).toBe("Buybacks");
  });
});

describe("Shell 테마 토글", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("클릭 시 html[data-theme] 를 전환하고 localStorage 'theme' 키에 저장한다", () => {
    render(<Shell>본문</Shell>);
    const toggle = screen.getByRole("button", { name: "테마 전환" });

    // jsdom 의 prefers-color-scheme 매치는 false → 현재 라이트로 간주, 첫 클릭은 다크로
    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");

    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("부트 스크립트가 설정해 둔 data-theme 값에서 이어서 전환한다", () => {
    document.documentElement.dataset.theme = "dark";
    render(<Shell>본문</Shell>);

    fireEvent.click(screen.getByRole("button", { name: "테마 전환" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
  });
});

describe("Shell 과 생태계 바(VCShell) 연동", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    delete window.VCShell;
  });

  it("VCShell 이 있으면 토글이 VCShell.setTheme 으로 위임한다", () => {
    const setTheme = vi.fn((theme: "light" | "dark" | "auto") => {
      const next = theme === "dark" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      return next;
    });
    window.VCShell = {
      version: "test",
      getTheme: () => "light",
      setTheme,
      setStock: vi.fn(),
      hubAnalysisUrl: () => null
    };
    document.documentElement.dataset.theme = "light";
    render(<Shell>본문</Shell>);

    fireEvent.click(screen.getByRole("button", { name: "테마 전환" }));
    expect(setTheme).toHaveBeenCalledWith("dark");
    // 저장은 셸의 몫이다: 폴백 경로처럼 직접 localStorage 에 쓰지 않는다.
    expect(localStorage.getItem("theme")).toBeNull();
  });

  it("'vc:themechange' 이벤트(셸 토글·다른 탭)로 토글 상태를 갱신한다", () => {
    document.documentElement.dataset.theme = "light";
    render(<Shell>본문</Shell>);
    const toggle = screen.getByRole("button", { name: "테마 전환" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    act(() => {
      document.dispatchEvent(new CustomEvent("vc:themechange", { detail: { theme: "dark" } }));
    });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveAttribute("title", "라이트 테마로 전환");
  });

  it("셸이 없을 때의 폴백 토글도 'vc:themechange' 를 발행한다", () => {
    const listener = vi.fn();
    document.addEventListener("vc:themechange", listener);
    render(<Shell>본문</Shell>);

    fireEvent.click(screen.getByRole("button", { name: "테마 전환" }));
    document.removeEventListener("vc:themechange", listener);
    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({ theme: "dark" });
  });
});
