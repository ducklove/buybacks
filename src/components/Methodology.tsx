import type { DataStatus } from "../types/buybacks";

interface MethodologyProps {
  status: DataStatus;
}

export function Methodology({ status }: MethodologyProps) {
  return (
    <section className="methodology" id="methodology">
      <header>
        <h2>산출 방법 / 데이터 출처</h2>
        <p>
          이 대시보드는 공시 사실, 보유 현황, 가격 반응 데이터를 서로 분리해서 관리합니다. 그래서
          시장 데이터가 없을 때 이를 감추지 않고 그대로 드러냅니다.
        </p>
      </header>
      <div className="method-grid">
        <article>
          <h3>OpenDART</h3>
          <p>
            공식 공시 메타데이터와 자기주식 취득·처분 결정, 신탁계약 체결·해지, 소각, 정기보고서
            기준 자기주식 보유 현황을 제공합니다.
          </p>
        </article>
        <article>
          <h3>kis_proxy</h3>
          <p>
            수익률 산출을 위한 일별 주가·지수 데이터를 제공합니다. 프록시를 사용할 수 없는 경우 가격
            반응 지표는 비공식 대체값으로 채우지 않고 null로 남겨둡니다.
          </p>
        </article>
        <article>
          <h3>데이터 품질</h3>
          <p>
            수익률은 확보 가능한 거래일 구간에 따라 완전(complete), 부분(partial), 누락(missing)
            으로 표시됩니다.
          </p>
        </article>
      </div>
      {status.warnings.length > 0 && (
        <ul className="warning-list" aria-label="데이터 경고">
          {status.warnings.map((warning, index) => (
            <li key={`${index}-${warning}`}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
