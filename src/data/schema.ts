import {
  DATA_QUALITIES,
  EVENT_TYPES,
  MARKETS,
  SOURCES,
  type BuybacksDataset,
  type Company,
  type DataQuality,
  type EventType,
  type Market,
  type Source
} from "../types/buybacks";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

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
    if (!ISO_DATE.test(event.disclosure_date)) errors.push(`events[${index}] invalid disclosure_date`);
    if (!isSource(event.source)) errors.push(`events[${index}] invalid source`);
  });

  dataset.holdingSnapshots.forEach((snapshot, index) => {
    if (!companyCodes.has(snapshot.stock_code)) {
      errors.push(`holdingSnapshots[${index}] unknown stock_code ${snapshot.stock_code}`);
    }
    if (!ISO_DATE.test(snapshot.as_of_date)) errors.push(`holdingSnapshots[${index}] invalid as_of_date`);
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

  if (dataset.status.companies_count !== dataset.companies.length) {
    errors.push("data_status.companies_count does not match companies length");
  }
  if (dataset.status.events_count !== dataset.events.length) {
    errors.push("data_status.events_count does not match events length");
  }

  return errors;
}

function validateCompany(company: Company, index: number, errors: string[]) {
  if (!company.corp_code || company.corp_code.length !== 8) {
    errors.push(`companies[${index}] corp_code must be 8 chars`);
  }
  if (!/^\d{6}$/.test(company.stock_code)) {
    errors.push(`companies[${index}] stock_code must be 6 digits`);
  }
  if (!company.corp_name) errors.push(`companies[${index}] missing corp_name`);
  if (!isMarket(company.market)) errors.push(`companies[${index}] invalid market`);
}

