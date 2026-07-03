import {
  CAR_MARKETS,
  DATA_QUALITIES,
  EVENT_TYPES,
  EXECUTION_TYPES,
  LINK_METHODS,
  MARKETS,
  SOURCES,
  type BuybacksDataset,
  type CarMarket,
  type Company,
  type DataQuality,
  type EventType,
  type ExecutionType,
  type LinkMethod,
  type Market,
  type Source
} from "../types/buybacks";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** reaction_series/car_curves 배열의 최대 길이 (t+1..t+60 거래일) */
export const REACTION_WINDOW_MAX = 60;

function isOneOf<T extends readonly string[]>(value: unknown, allowed: T): value is T[number] {
  return typeof value === "string" && allowed.includes(value);
}

export function isMarket(value: unknown): value is Market {
  return isOneOf(value, MARKETS);
}

export function isEventType(value: unknown): value is EventType {
  return isOneOf(value, EVENT_TYPES);
}

export function isSource(value: unknown): value is Source {
  return isOneOf(value, SOURCES);
}

export function isDataQuality(value: unknown): value is DataQuality {
  return isOneOf(value, DATA_QUALITIES);
}

export function isExecutionType(value: unknown): value is ExecutionType {
  return isOneOf(value, EXECUTION_TYPES);
}

export function isLinkMethod(value: unknown): value is LinkMethod {
  return isOneOf(value, LINK_METHODS);
}

export function isCarMarket(value: unknown): value is CarMarket {
  return isOneOf(value, CAR_MARKETS);
}

export function validateDataset(dataset: BuybacksDataset): string[] {
  const errors: string[] = [];
  const companyCodes = new Set<string>();
  const eventIds = new Set<string>();

  dataset.companies.forEach((company, index) => {
    validateCompany(company, index, errors);
    if (companyCodes.has(company.stock_code)) {
      errors.push(`companies[${index}] duplicate stock_code ${company.stock_code}`);
    }
    companyCodes.add(company.stock_code);
  });

  dataset.events.forEach((event, index) => {
    if (!event.event_id) errors.push(`events[${index}] missing event_id`);
    if (eventIds.has(event.event_id)) errors.push(`events[${index}] duplicate event_id`);
    eventIds.add(event.event_id);
    if (!companyCodes.has(event.stock_code)) {
      errors.push(`events[${index}] unknown stock_code ${event.stock_code}`);
    }
    if (!isEventType(event.event_type)) errors.push(`events[${index}] invalid event_type`);
    if (!ISO_DATE.test(event.disclosure_date))
      errors.push(`events[${index}] invalid disclosure_date`);
    if (!isSource(event.source)) errors.push(`events[${index}] invalid source`);
  });

  dataset.holdingSnapshots.forEach((snapshot, index) => {
    if (!companyCodes.has(snapshot.stock_code)) {
      errors.push(`holdingSnapshots[${index}] unknown stock_code ${snapshot.stock_code}`);
    }
    if (!ISO_DATE.test(snapshot.as_of_date))
      errors.push(`holdingSnapshots[${index}] invalid as_of_date`);
    if (
      snapshot.treasury_ratio !== null &&
      (snapshot.treasury_ratio < 0 || snapshot.treasury_ratio > 1)
    ) {
      errors.push(`holdingSnapshots[${index}] treasury_ratio must be 0..1`);
    }
  });

  dataset.priceReactions.forEach((reaction, index) => {
    if (!eventIds.has(reaction.event_id)) {
      errors.push(`priceReactions[${index}] unknown event_id ${reaction.event_id}`);
    }
    if (!isDataQuality(reaction.data_quality)) {
      errors.push(`priceReactions[${index}] invalid data_quality`);
    }
  });

  dataset.latestPrices.forEach((price, index) => {
    if (!companyCodes.has(price.stock_code)) {
      errors.push(`latestPrices[${index}] unknown stock_code ${price.stock_code}`);
    }
    if (!ISO_DATE.test(price.price_date)) {
      errors.push(`latestPrices[${index}] invalid price_date`);
    }
    if (typeof price.close !== "number" || price.close <= 0) {
      errors.push(`latestPrices[${index}] close must be positive`);
    }
    if (
      price.change_rate !== null &&
      price.change_rate !== undefined &&
      typeof price.change_rate !== "number"
    ) {
      errors.push(`latestPrices[${index}] change_rate must be numeric`);
    }
    if (
      price.issued_shares !== null &&
      price.issued_shares !== undefined &&
      (typeof price.issued_shares !== "number" || price.issued_shares <= 0)
    ) {
      errors.push(`latestPrices[${index}] issued_shares must be positive`);
    }
    if (
      price.market_cap_krw !== null &&
      price.market_cap_krw !== undefined &&
      (typeof price.market_cap_krw !== "number" || price.market_cap_krw <= 0)
    ) {
      errors.push(`latestPrices[${index}] market_cap_krw must be positive`);
    }
    if (
      price.change_code !== null &&
      price.change_code !== undefined &&
      typeof price.change_code !== "string"
    ) {
      errors.push(`latestPrices[${index}] change_code must be a string`);
    }
  });

  const executionIds = new Set<string>();
  dataset.executions.forEach((execution, index) => {
    if (!execution.execution_id) {
      errors.push(`executions[${index}] missing execution_id`);
    }
    if (executionIds.has(execution.execution_id)) {
      errors.push(`executions[${index}] duplicate execution_id`);
    }
    executionIds.add(execution.execution_id);
    if (!execution.stock_code) {
      errors.push(`executions[${index}] missing stock_code`);
    }
    if (!isExecutionType(execution.execution_type)) {
      errors.push(`executions[${index}] invalid execution_type`);
    }
    if (!ISO_DATE.test(execution.disclosure_date)) {
      errors.push(`executions[${index}] invalid disclosure_date`);
    }
    if (execution.as_of_date !== null && !ISO_DATE.test(execution.as_of_date)) {
      errors.push(`executions[${index}] invalid as_of_date`);
    }
    if (!isLinkMethod(execution.link_method)) {
      errors.push(`executions[${index}] invalid link_method`);
    }
    if (execution.linked_event_id !== null && !eventIds.has(execution.linked_event_id)) {
      errors.push(`executions[${index}] unknown linked_event_id ${execution.linked_event_id}`);
    }
  });

  validateReactionSeries(dataset, errors);
  validateCarCurves(dataset, errors);
  validateDividends(dataset, errors);

  if (dataset.status.companies_count !== dataset.companies.length) {
    errors.push("data_status.companies_count does not match companies length");
  }
  if (dataset.status.events_count !== dataset.events.length) {
    errors.push("data_status.events_count does not match events length");
  }

  return errors;
}

function validateReactionSeries(dataset: BuybacksDataset, errors: string[]) {
  if (dataset.reactionSeries === undefined) return;
  if (!Array.isArray(dataset.reactionSeries)) {
    errors.push("reactionSeries must be an array");
    return;
  }
  const seriesEventIds = new Set<string>();
  dataset.reactionSeries.forEach((series, index) => {
    if (!series.event_id) errors.push(`reactionSeries[${index}] missing event_id`);
    if (seriesEventIds.has(series.event_id)) {
      errors.push(`reactionSeries[${index}] duplicate event_id ${series.event_id}`);
    }
    seriesEventIds.add(series.event_id);
    if (!ISO_DATE.test(series.event_date)) {
      errors.push(`reactionSeries[${index}] invalid event_date`);
    }
    if (!Array.isArray(series.daily_return) || !Array.isArray(series.daily_abnormal)) {
      errors.push(`reactionSeries[${index}] daily arrays must be arrays`);
      return;
    }
    if (series.daily_return.length > REACTION_WINDOW_MAX) {
      errors.push(`reactionSeries[${index}] daily_return longer than ${REACTION_WINDOW_MAX}`);
    }
    if (series.daily_abnormal.length !== series.daily_return.length) {
      errors.push(`reactionSeries[${index}] daily_abnormal length must match daily_return`);
    }
  });
}

function validateCarCurves(dataset: BuybacksDataset, errors: string[]) {
  if (dataset.carCurves === undefined || dataset.carCurves === null) return;
  const carCurves = dataset.carCurves;
  if (!Array.isArray(carCurves.groups)) {
    errors.push("carCurves.groups must be an array");
    return;
  }
  if (typeof carCurves.window !== "number" || carCurves.window <= 0) {
    errors.push("carCurves.window must be a positive number");
  }
  carCurves.groups.forEach((group, index) => {
    if (!isCarMarket(group.market)) {
      errors.push(`carCurves.groups[${index}] invalid market`);
    }
    if (typeof group.n !== "number" || group.n < 0) {
      errors.push(`carCurves.groups[${index}] n must be a non-negative number`);
    }
    if (!Array.isArray(group.mean_car)) {
      errors.push(`carCurves.groups[${index}] mean_car must be an array`);
      return;
    }
    if (group.mean_car.length > REACTION_WINDOW_MAX) {
      errors.push(`carCurves.groups[${index}] mean_car longer than ${REACTION_WINDOW_MAX}`);
    }
  });
}

function validateDividends(dataset: BuybacksDataset, errors: string[]) {
  if (dataset.dividends === undefined) return;
  if (!Array.isArray(dataset.dividends)) {
    errors.push("dividends must be an array");
    return;
  }
  const keys = new Set<string>();
  dataset.dividends.forEach((dividend, index) => {
    if (!dividend.corp_code) errors.push(`dividends[${index}] missing corp_code`);
    if (!dividend.stock_code) errors.push(`dividends[${index}] missing stock_code`);
    if (typeof dividend.bsns_year !== "number") {
      errors.push(`dividends[${index}] bsns_year must be a number`);
    }
    const key = `${dividend.corp_code}:${dividend.bsns_year}`;
    if (keys.has(key)) {
      errors.push(`dividends[${index}] duplicate corp_code/bsns_year ${key}`);
    }
    keys.add(key);
    if (
      dividend.cash_dividend_total_krw !== null &&
      typeof dividend.cash_dividend_total_krw !== "number"
    ) {
      errors.push(`dividends[${index}] cash_dividend_total_krw must be numeric or null`);
    }
    if (dividend.dps_common_krw !== null && typeof dividend.dps_common_krw !== "number") {
      errors.push(`dividends[${index}] dps_common_krw must be numeric or null`);
    }
  });
}

function validateCompany(company: Company, index: number, errors: string[]) {
  if (!company.corp_code || company.corp_code.length !== 8) {
    errors.push(`companies[${index}] corp_code must be 8 chars`);
  }
  if (!/^[0-9A-Z]{6}$/.test(company.stock_code)) {
    errors.push(`companies[${index}] stock_code must be 6 uppercase letters or digits`);
  }
  if (!company.corp_name) errors.push(`companies[${index}] missing corp_name`);
  if (!isMarket(company.market)) errors.push(`companies[${index}] invalid market`);
}
