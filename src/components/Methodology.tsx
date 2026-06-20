import type { DataStatus } from "../types/buybacks";

interface MethodologyProps {
  status: DataStatus;
}

export function Methodology({ status }: MethodologyProps) {
  return (
    <section className="methodology" id="methodology">
      <header>
        <h2>Methodology / Data Source</h2>
        <p>
          이 화면은 투자 조언이 아니라 자사주 관련 공시와 가격 데이터를 탐색하기 위한 정적
          데이터 도구입니다.
        </p>
      </header>
      <div className="method-grid">
        <article>
          <h3>OpenDART</h3>
          <p>
            기업 고유번호, 자기주식 취득·처분 결정, 신탁계약 체결·해지, 정기보고서 내
            자기주식 보유현황을 수집합니다.
          </p>
        </article>
        <article>
          <h3>KRX</h3>
          <p>
            공식 Open API 승인 범위에서 일별 가격과 지수 데이터를 보강합니다. 자기주식
            체결 상세는 공식 API와 라이선스 확인 후 연결합니다.
          </p>
        </article>
        <article>
          <h3>데이터 품질</h3>
          <p>
            결측치는 0으로 바꾸지 않고 `complete`, `partial`, `missing` 상태로 남깁니다.
            기준일이 다른 데이터는 부분 데이터로 해석합니다.
          </p>
        </article>
      </div>
      {status.warnings.length > 0 && (
        <ul className="warning-list" aria-label="데이터 경고">
          {status.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

