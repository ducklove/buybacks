import type { BuybackEvent, BuybackExecution } from "../types/buybacks";

export type ExecutionStatus = "완료" | "미달" | "진행중" | null;

export interface ExecutionStatusInfo {
  status: ExecutionStatus;
  reason: string | null;
}

/**
 * 이벤트별 대표 execution 1건을 선택한다.
 * - 신탁(trust_status)은 as_of_date가 가장 최신인 건을 대표로 삼는다 (누적치라 합산하지 않음).
 * - 그 외 유형은 정정 보고서 반영을 위해 disclosure_date가 가장 최신인 건을 대표로 삼는다.
 * - linked_event_id가 없는(unlinked) execution은 대상에서 제외한다.
 */
export function pickRepresentativeExecution(
  eventId: string,
  executions: BuybackExecution[]
): BuybackExecution | undefined {
  const linked = executions.filter((execution) => execution.linked_event_id === eventId);
  if (linked.length === 0) {
    return undefined;
  }

  const trustExecutions = linked.filter((execution) => execution.execution_type === "trust_status");
  if (trustExecutions.length > 0) {
    return [...trustExecutions].sort((a, b) =>
      (b.as_of_date ?? "").localeCompare(a.as_of_date ?? "")
    )[0];
  }

  return [...linked].sort((a, b) => b.disclosure_date.localeCompare(a.disclosure_date))[0];
}

/**
 * 이벤트별 대표 execution 맵을 만든다. groupExecutionsByEvent와 달리 이벤트 목록을 순회하지 않고
 * linked_event_id 기준으로 그룹화한 뒤 각 그룹에서 대표 1건을 뽑는다.
 */
export function mapExecutionsByEvent(
  executions: BuybackExecution[]
): Map<string, BuybackExecution> {
  const byEvent = new Map<string, BuybackExecution[]>();
  executions.forEach((execution) => {
    if (!execution.linked_event_id) {
      return;
    }
    const bucket = byEvent.get(execution.linked_event_id);
    if (bucket) {
      bucket.push(execution);
    } else {
      byEvent.set(execution.linked_event_id, [execution]);
    }
  });

  const representative = new Map<string, BuybackExecution>();
  byEvent.forEach((bucket, eventId) => {
    const picked = pickRepresentativeExecution(eventId, bucket);
    if (picked) {
      representative.set(eventId, picked);
    }
  });
  return representative;
}

/**
 * 이벤트와 대표 execution으로부터 완료율(0~1)을 계산한다.
 * 1. 신탁 진행 상황(trust_progress_ratio)이 있으면 그것을 사용한다.
 * 2. 수량 기준(actual_shares / planned_shares_common)을 우선 사용한다.
 * 3. 수량 기준을 계산할 수 없으면 금액 기준으로 폴백한다.
 */
export function completionRate(
  event: BuybackEvent | undefined,
  execution: BuybackExecution | undefined
): number | null {
  if (!execution) {
    return null;
  }

  if (execution.execution_type === "trust_status") {
    return ratioOrNull(execution.trust_progress_ratio);
  }

  const plannedShares = event?.planned_shares_common ?? null;
  if (execution.actual_shares !== null && plannedShares !== null && plannedShares > 0) {
    return execution.actual_shares / plannedShares;
  }

  const plannedAmount = event?.planned_amount_krw ?? execution.planned_amount_krw ?? null;
  if (execution.actual_amount_krw !== null && plannedAmount !== null && plannedAmount > 0) {
    return execution.actual_amount_krw / plannedAmount;
  }

  return null;
}

/**
 * execution의 이행 상태를 계산한다.
 * - 신탁(trust_status)은 진행중으로 표시한다.
 * - shortfall === true면 미달(사유 포함), false면 완료.
 * - 결과보고서가 아직 없거나 판단할 수 없으면 null(표시 없음, "-").
 */
export function executionStatus(execution: BuybackExecution | undefined): ExecutionStatusInfo {
  if (!execution) {
    return { status: null, reason: null };
  }
  if (execution.execution_type === "trust_status") {
    return { status: "진행중", reason: null };
  }
  if (execution.shortfall === true) {
    return { status: "미달", reason: execution.shortfall_reason };
  }
  if (execution.shortfall === false) {
    return { status: "완료", reason: null };
  }
  return { status: null, reason: null };
}

/** unlinked(이벤트에 연결되지 않은) execution만 골라 종목코드로 필터링한다. */
export function unlinkedExecutionsForStock(
  executions: BuybackExecution[],
  stockCode: string
): BuybackExecution[] {
  return executions.filter(
    (execution) => execution.stock_code === stockCode && execution.linked_event_id === null
  );
}

function ratioOrNull(value: number | null): number | null {
  if (value === null || Number.isNaN(value)) {
    return null;
  }
  return value;
}
