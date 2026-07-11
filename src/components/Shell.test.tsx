import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Shell } from "./Shell";

describe("Shell", () => {
  it("renders the Value Compass hub link and the GitHub repository link", () => {
    render(<Shell>본문</Shell>);

    const hubLink = screen.getByRole("link", { name: "Value Compass ↗" });
    expect(hubLink).toHaveAttribute("href", "https://cantabile.tplinkdns.com:3691");

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
