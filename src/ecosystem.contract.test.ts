import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { setShellStock } from "./utils/vcShell";

// Value Compass 생태계 계약(value-invest config/ecosystem.json, tool id "buybacks").
// public/vc-shell.js·public/vc-tokens.css 는 value-invest scripts/sync-ecosystem.mjs 가
// 벤더링한 사본이다(직접 수정 금지). Vite 가 public/ 을 dist/ 루트로 복사해 Pages 에 배포된다.
const root = process.cwd();
const indexHtml = readFileSync(path.join(root, "index.html"), "utf-8");
const stylesCss = readFileSync(path.join(root, "src", "styles.css"), "utf-8");
const shellJs = readFileSync(path.join(root, "public", "vc-shell.js"), "utf-8");
const tokensCss = readFileSync(path.join(root, "public", "vc-tokens.css"), "utf-8");

describe("생태계 셸 채택 (index.html)", () => {
  it("vc:theme-boot 마커가 정확히 한 번, 어떤 스타일시트보다 먼저 온다", () => {
    const open = indexHtml.indexOf("<!-- vc:theme-boot -->");
    expect(open).toBeGreaterThan(-1);
    expect(indexHtml.split("<!-- vc:theme-boot -->")).toHaveLength(2);
    expect(indexHtml).toContain("<!-- /vc:theme-boot -->");
    expect(open).toBeLessThan(indexHtml.indexOf('rel="stylesheet"'));
  });

  it("vc-tokens.css 와 defer vc-shell.js 를 BASE_URL 기준으로 로드한다", () => {
    expect(indexHtml).toMatch(/<link rel="stylesheet" href="%BASE_URL%vc-tokens\.css\?v=[^"]+"/);
    expect(indexHtml).toMatch(/<script defer src="%BASE_URL%vc-shell\.js\?v=[^"]+"><\/script>/);
  });

  it('<vc-shell tool="buybacks"> 는 #root 의 형제(React 트리 밖)이고 허브 링크 폴백을 가진다', () => {
    const shellTag = indexHtml.indexOf('<vc-shell tool="buybacks">');
    const rootDiv = indexHtml.indexOf('<div id="root"></div>');
    expect(shellTag).toBeGreaterThan(indexHtml.indexOf("<body>"));
    expect(shellTag).toBeLessThan(rootDiv);
    const fallback = indexHtml.slice(shellTag, indexHtml.indexOf("</vc-shell>"));
    expect(fallback).toContain('href="https://ducklove.duckdns.org:3691"');
    expect(fallback).toContain("Value Compass ↗");
  });

  it("허브 보유 배지 스크립트 ?v 가 레지스트리 heldBadges.version 과 같다", () => {
    expect(indexHtml).toContain("/js/portfolio-held-badges.js?v=20260930-vc");
  });

  it("벤더링 파일이 public/ 에 있어 dist/ 루트로 배포된다", () => {
    expect(existsSync(path.join(root, "public", "vc-shell.js"))).toBe(true);
    expect(shellJs).toContain("window.VCShell");
    expect(tokensCss).toContain("--vc-up:");
    expect(tokensCss).toContain("--vc-font-sans:");
  });

  it("방향색·글꼴이 생태계 토큰을 따른다(상승=빨강 --vc-up, 하락=파랑 --vc-down)", () => {
    expect(stylesCss).toContain("--price-up: var(--vc-up");
    expect(stylesCss).toContain("--price-down: var(--vc-down");
    expect(stylesCss).toMatch(/font-family: var\(\s*--vc-font-sans/);
  });
});

describe("VCShell.setStock 연동 (실제 vc-shell.js)", () => {
  beforeAll(() => {
    document.body.innerHTML = '<vc-shell tool="buybacks"></vc-shell><div id="root"></div>';
    new Function(shellJs)();
  });

  it("벤더링된 셸이 전역 API 를 노출한다", () => {
    expect(window.VCShell).toBeDefined();
    expect(typeof window.VCShell?.setStock).toBe("function");
    expect(window.VCShell?.hubAnalysisUrl("005930")).toMatch(/\/analysis\?code=005930/);
  });

  it("setShellStock 이 종목 코드·이름을 <vc-shell> 속성으로 전달하고 null 로 해제한다", () => {
    const el = document.querySelector("vc-shell");
    setShellStock("005930", "삼성전자");
    expect(el?.getAttribute("stock")).toBe("005930");
    expect(el?.getAttribute("stock-name")).toBe("삼성전자");

    setShellStock(null);
    expect(el?.hasAttribute("stock")).toBe(false);
    expect(el?.hasAttribute("stock-name")).toBe(false);
  });
});
