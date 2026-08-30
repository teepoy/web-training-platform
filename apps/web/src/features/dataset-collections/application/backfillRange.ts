export interface BackfillRangeInput {
  startAt: number | null;
  endAt: number | null;
  timezone: string;
}

export interface ResolvedBackfillRange {
  start_utc: string;
  end_utc: string;
  timezone: string;
}

type IntlWithSupportedValues = typeof Intl & {
  supportedValuesOf?: (key: "timeZone") => string[];
};

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export function supportedTimeZoneOptions(): Array<{ label: string; value: string }> {
  const zones = (Intl as IntlWithSupportedValues).supportedValuesOf?.("timeZone") ?? [];
  const values = new Set(["UTC", browserTimeZone(), ...zones]);
  return [...values].sort().map((value) => ({ label: value, value }));
}

export function isValidTimeZone(timezone: string): boolean {
  if (!timezone.trim()) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: timezone }).format();
    return true;
  } catch {
    return false;
  }
}

function zonedParts(timestamp: number, timezone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  return Object.fromEntries(
    parts.filter((part) => part.type !== "literal").map((part) => [part.type, Number(part.value)]),
  );
}

export function datePickerWallTimeToUtcIso(value: number, timezone: string): string {
  if (!isValidTimeZone(timezone)) throw new Error("Invalid IANA timezone");
  const local = new Date(value);
  const intendedWallTime = Date.UTC(
    local.getFullYear(),
    local.getMonth(),
    local.getDate(),
    local.getHours(),
    local.getMinutes(),
    local.getSeconds(),
    local.getMilliseconds(),
  );
  let utcTimestamp = intendedWallTime;
  for (let pass = 0; pass < 3; pass += 1) {
    const parts = zonedParts(utcTimestamp, timezone);
    const renderedWallTime = Date.UTC(
      parts.year ?? 0,
      (parts.month ?? 1) - 1,
      parts.day ?? 1,
      parts.hour ?? 0,
      parts.minute ?? 0,
      parts.second ?? 0,
      local.getMilliseconds(),
    );
    utcTimestamp += intendedWallTime - renderedWallTime;
  }
  return new Date(utcTimestamp).toISOString();
}

export function resolveBackfillRange(input: BackfillRangeInput): ResolvedBackfillRange | null {
  const timezone = input.timezone.trim();
  if (
    input.startAt === null ||
    input.endAt === null ||
    input.startAt >= input.endAt ||
    !isValidTimeZone(timezone)
  ) {
    return null;
  }
  return {
    start_utc: datePickerWallTimeToUtcIso(input.startAt, timezone),
    end_utc: datePickerWallTimeToUtcIso(input.endAt, timezone),
    timezone,
  };
}
