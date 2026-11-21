import type { Goal, Role } from "./api/types";

/**
 * Display helpers. Business dates ("2026-11-09", due dates, week starts) are company-time calendar dates and
 * are formatted as plain dates (no time-zone shift). Timestamps are UTC instants shown in the company zone.
 * Nothing here reads the browser's clock: "today" always comes from the API (APP_NOW).
 */

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatNumber(value: number): string {
  return number.format(value);
}

/** A value with its unit: 12 count → "12", 3.5 % → "3.5%", 500 $k → "$500k", 3 hours → "3 h". */
export function withUnit(value: number, unit: string): string {
  const n = formatNumber(value);
  switch (unit) {
    case "count":
      return n;
    case "%":
      return `${n}%`;
    case "$":
      return `$${n}`;
    case "$k":
      return `$${n}k`;
    case "hours":
      return `${n} h`;
    default:
      return `${n} ${unit}`;
  }
}

export function formatGoal(goal: Goal, unit: string): string {
  const v = (x: number | null) => (x === null ? "?" : withUnit(x, unit));
  switch (goal.type) {
    case "at_least":
      return `≥ ${v(goal.value)}`;
    case "at_most":
      return `≤ ${v(goal.value)}`;
    case "exactly":
      return `= ${v(goal.value)}`;
    case "between":
      return `${v(goal.min)} – ${v(goal.max)}`;
  }
}

export function describeGoal(goal: Goal, unit: string): string {
  const v = (x: number | null) => (x === null ? "?" : withUnit(x, unit));
  switch (goal.type) {
    case "at_least":
      return `Goal: at least ${v(goal.value)}`;
    case "at_most":
      return `Goal: at most ${v(goal.value)}`;
    case "exactly":
      return `Goal: exactly ${v(goal.value)}`;
    case "between":
      return `Goal: between ${v(goal.min)} and ${v(goal.max)}`;
  }
}

function plainDate(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

/** "2026-11-09" → "Nov 9" */
export function formatDay(iso: string): string {
  return shortDate.format(plainDate(iso));
}

/** "2026-11-09" → "Mon, Nov 9, 2026" */
export function formatDayLong(iso: string): string {
  return longDate.format(plainDate(iso));
}

/** Week label: "Nov 9 – 15" or "Oct 26 – Nov 1". */
export function formatWeek(weekStart: string): string {
  const start = plainDate(weekStart);
  const end = new Date(start.getTime() + 6 * 86_400_000);
  const sameMonth = start.getUTCMonth() === end.getUTCMonth();
  const endLabel = sameMonth ? String(end.getUTCDate()) : shortDate.format(end);
  return `${shortDate.format(start)} – ${endLabel}`;
}

export function addDays(iso: string, days: number): string {
  return new Date(plainDate(iso).getTime() + days * 86_400_000).toISOString().slice(0, 10);
}

/** A UTC instant in the company time zone: "Nov 10, 3:15 PM". */
export function formatInstant(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

/** Seconds → "4:05" or "1:02:05". */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** A span of time in words: "38 sec", "12 min", "1 h 15 min". */
export function formatLength(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s} sec`;
  const minutes = Math.round(s / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export const roleLabel: Record<Role, string> = {
  admin: "Admin",
  team_member: "Team Member",
  observer: "Observer",
};

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
