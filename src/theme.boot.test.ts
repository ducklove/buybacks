import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

// index.html 인라인 부트 스크립트(FOUC 방지)를 그대로 추출해 jsdom 에서 실행한다.
// vitest 는 프로젝트 루트를 cwd 로 실행한다.
const indexHtml = readFileSync(path.join(process.cwd(), "index.html"), "utf-8");
const stylesCss = readFileSync(path.join(process.cwd(), "src", "styles.css"), "utf-8");

function bootScript(): string {
  const match = indexHtml.match(/<script>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("index.html에서 부트 스크립트를 찾지 못했다");
  return match[1];
}

function runBoot(search: string) {
  window.history.replaceState(null, "", `/${search}`);
  new Function(bootScript())();
}

describe("테마·임베드 부트 스크립트", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.embed;
    window.history.replaceState(null, "", "/");
  });

  it("?theme=dark 는 localStorage 저장값보다 우선해 테마를 강제한다", () => {
    localStorage.setItem("theme", "light");
    runBoot("?theme=dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("?theme=light 는 저장된 다크 테마를 덮어쓴다", () => {
    localStorage.setItem("theme", "dark");
    runBoot("?theme=light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("URL 파라미터가 없으면 localStorage 'theme' 값을 적용한다", () => {
    localStorage.setItem("theme", "dark");
    runBoot("");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("저장값도 파라미터도 없으면 data-theme 미설정 → prefers-color-scheme 폴백", () => {
    runBoot("");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("잘못된 테마 값은 무시한다", () => {
    localStorage.setItem("theme", "solarized");
    runBoot("?theme=blue");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("?embed=true 는 data-embed 를 설정하고 embed=false/0 은 무시한다", () => {
    runBoot("?embed=true");
    expect(document.documentElement.dataset.embed).toBe("1");

    delete document.documentElement.dataset.embed;
    runBoot("?embed=false");
    expect(document.documentElement.dataset.embed).toBeUndefined();

    runBoot("?embed=0");
    expect(document.documentElement.dataset.embed).toBeUndefined();
  });

  it("CSS가 임베드 모드에서 topbar 를 숨기고 본문 여백을 줄인다", () => {
    expect(stylesCss).toMatch(/html\[data-embed\] \.topbar\s*\{\s*display:\s*none/);
    expect(stylesCss).toMatch(/html\[data-embed\] \.app-main/);
  });

  it("다크 토큰이 data-theme 강제 경로와 OS 폴백 경로 모두에 존재한다", () => {
    expect(stylesCss).toContain(':root[data-theme="dark"]');
    expect(stylesCss).toMatch(
      /@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\)/
    );
  });
});
