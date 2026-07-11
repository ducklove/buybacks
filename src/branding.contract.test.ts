import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// index.html 정적 마크업(타이틀·메타)의 한국어 브랜딩 계약을 고정한다.
const indexHtml = readFileSync(path.join(process.cwd(), "index.html"), "utf-8");

describe("한국어 브랜딩 계약 (index.html)", () => {
  it("문서 타이틀이 한국어 서비스명 '자사주 분석' 이다", () => {
    expect(indexHtml).toContain("<title>자사주 분석</title>");
  });

  it("meta description 이 한국어로 작성돼 있다", () => {
    const match = indexHtml.match(/<meta[^>]*name="description"[^>]*content="([^"]+)"/);
    expect(match).not.toBeNull();
    expect(match?.[1]).toMatch(/[가-힣]/);
    expect(match?.[1]).toContain("자사주");
  });

  it("og:title / og:description 메타 태그가 한국어로 존재한다", () => {
    const ogTitle = indexHtml.match(/<meta[^>]*property="og:title"[^>]*content="([^"]+)"/);
    expect(ogTitle?.[1]).toBe("자사주 분석");

    const ogDescription = indexHtml.match(
      /<meta[^>]*property="og:description"[^>]*content="([^"]+)"/
    );
    expect(ogDescription).not.toBeNull();
    expect(ogDescription?.[1]).toMatch(/[가-힣]/);
  });
});
