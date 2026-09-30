import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// index.html 의 <!-- vc:theme-boot --> 블록(생태계 공통 pre-paint 부트, value-invest
// scripts/sync-ecosystem.mjs 가 채운다)을 그대로 추출해 jsdom 에서 실행한다.
// vitest 는 프로젝트 루트를 cwd 로 실행한다.
const indexHtml = readFileSync(path.join(process.cwd(), "index.html"), "utf-8");
const stylesCss = readFileSync(path.join(process.cwd(), "src", "styles.css"), "utf-8");

function bootScript(): string {
  const match = indexHtml.match(
    /<!-- vc:theme-boot --><script>([\s\S]*?)<\/script><!-- \/vc:theme-boot -->/
  );
  if (!match) throw new Error("index.html에서 vc:theme-boot 블록을 찾지 못했다");
  return match[1];
}

function stubColorScheme(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query.includes("dark"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    }))
  );
}

function runBoot(search: string) {
  window.history.replaceState(null, "", `/${search}`);
  new Function(bootScript())();
}

describe("테마·임베드 부트 스크립트 (vc-theme-boot)", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.embed;
    window.history.replaceState(null, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("?theme=dark 는 localStorage 저장값보다 우선하되 저장하지는 않는다", () => {
    localStorage.setItem("theme", "light");
    runBoot("?theme=dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("?theme=light 는 저장된 다크 테마를 덮어쓴다", () => {
    localStorage.setItem("theme", "dark");
    runBoot("?theme=light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("URL 파라미터가 없으면 공용 localStorage 'theme' 값을 적용한다", () => {
    localStorage.setItem("theme", "dark");
    runBoot("");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("저장값도 파라미터도 없으면 prefers-color-scheme 를 명시적 data-theme 로 적용한다", () => {
    stubColorScheme(true);
    runBoot("");
    expect(document.documentElement.dataset.theme).toBe("dark");

    stubColorScheme(false);
    runBoot("");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("잘못된 테마 값은 무시하고 OS 선호로 폴백한다", () => {
    stubColorScheme(false);
    localStorage.setItem("theme", "solarized");
    runBoot("?theme=blue");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("다른 대시보드의 레거시 테마 키를 공용 'theme' 키로 옮겨 적용한다", () => {
    localStorage.setItem("spac-hunter-theme", "dark");
    runBoot("");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("?embed(0/false 제외)는 data-embed 를 설정한다", () => {
    runBoot("?embed=true");
    expect(document.documentElement.hasAttribute("data-embed")).toBe(true);

    delete document.documentElement.dataset.embed;
    runBoot("?embed=1");
    expect(document.documentElement.hasAttribute("data-embed")).toBe(true);

    delete document.documentElement.dataset.embed;
    runBoot("?embed=false");
    expect(document.documentElement.hasAttribute("data-embed")).toBe(false);

    runBoot("?embed=0");
    expect(document.documentElement.hasAttribute("data-embed")).toBe(false);
  });

  it("CSS가 임베드 모드에서 topbar 를 숨기고 본문 여백을 줄인다", () => {
    expect(stylesCss).toMatch(/html\[data-embed\] \.topbar\s*\{\s*display:\s*none/);
    expect(stylesCss).toMatch(/html\[data-embed\] \.app-main/);
  });

  it("다크 토큰은 data-theme 경로 하나에만 정의한다(부트가 항상 data-theme 를 명시)", () => {
    expect(stylesCss).toContain(':root[data-theme="dark"]');
    expect(stylesCss).not.toMatch(/@media \(prefers-color-scheme: dark\)/);
    expect(stylesCss.match(/--bg: #10161a;/g)).toHaveLength(1);
  });
});
