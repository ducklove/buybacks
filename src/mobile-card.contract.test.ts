import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// ≤760px 카드 모드 CSS 계약을 문자열로 고정한다. EventTable/ScreenerTable 은
// section.card-table 로 옵트인하며, 컴포넌트 쪽 마크업 계약은 각 컴포넌트 테스트에서 검증한다.
const stylesCss = readFileSync(path.join(process.cwd(), "src", "styles.css"), "utf-8");
const mobileStart = stylesCss.indexOf("@media (max-width: 760px)");
const mobileBlock = stylesCss.slice(mobileStart);

describe("모바일 카드 모드 CSS 계약 (≤760px)", () => {
  it("카드 모드 규칙은 760px 미디어 쿼리 내부에만 존재한다 (데스크톱 테이블 불변)", () => {
    expect(mobileStart).toBeGreaterThan(-1);
    expect(stylesCss.slice(0, mobileStart)).not.toContain(".card-table");
  });

  it("카드 모드에서 min-width 640px 가로 스크롤 규칙을 해제한다", () => {
    expect(mobileBlock).toMatch(/\.card-table \.table-scroll \{[^}]*overflow-x: visible/);
    expect(mobileBlock).toMatch(/\.card-table table \{[^}]*min-width: 0/);
  });

  it("tbody 행을 grid 카드로 재배치하고 data-label 을 셀 라벨(::before)로 사용한다", () => {
    expect(mobileBlock).toMatch(/\.card-table tbody tr \{[^}]*display: grid/);
    expect(mobileBlock).toMatch(
      /\.card-table tbody td\[data-label\]::before \{[^}]*content: attr\(data-label\)/
    );
    expect(mobileBlock).toMatch(/\.card-table tbody \.company-cell \{[^}]*grid-column: 1 \/ -1/);
  });

  it("정렬 헤더는 칩으로 유지되고 숫자 셀은 tabular-nums 자릿수 정렬을 유지한다", () => {
    expect(mobileBlock).toMatch(/\.card-table thead th \.sort-button \{/);
    expect(mobileBlock).toMatch(
      /\.card-table tbody \.numeric-cell \{[^}]*font-variant-numeric: tabular-nums/
    );
  });

  it("카드 모드에서도 col-optional 열 숨김 계약이 유지된다", () => {
    // .card-table tbody td 의 display: block 이 .col-optional 의 display: none 을
    // 덮어쓰지 않도록 더 높은 특이도의 재정의 규칙이 존재해야 한다.
    expect(mobileBlock).toMatch(/\.card-table tbody td\.col-optional \{[^}]*display: none/);
  });
});
