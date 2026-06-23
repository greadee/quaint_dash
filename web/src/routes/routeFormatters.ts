export const percent = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;

export const number = (value: number | null | undefined, digits = 2) =>
  value == null ? "Unavailable" : value.toFixed(digits);

export const signedNumber = (value: number | null | undefined, digits = 1) =>
  value == null ? "Unavailable" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;

const cleanCurrency = (value: string | null | undefined, fallback = "CAD") => {
  if (!value) return fallback;
  const direct = value.trim().toUpperCase();
  if (/^[A-Z]{3}$/.test(direct)) return direct;
  const match = direct.match(/['"]?CODE['"]?\s*:\s*['"]?([A-Z]{3})['"]?/);
  return match?.[1] ?? fallback;
};

export const formatMoney = (value: number | null | undefined, currency = "CAD") =>
  value == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: cleanCurrency(currency),
      maximumFractionDigits: 0,
    }).format(value);

export const money = formatMoney;

export function formatActionResult(result: Record<string, unknown>): string {
  const entries = Object.entries(result).slice(0, 4);
  if (!entries.length) return "done";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(", ");
}

export function boundedInt(value: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

export function formatCount(value: number | null | undefined, noun: string): string {
  if (value == null) return "Not run yet";
  return `${value} ${noun}${value === 1 ? "" : "s"}`;
}

export function formatDuration(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}

export function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "never";
}

export function dateRange(start?: string | null, end?: string | null): string {
  if (start && end) return `${new Date(start).toLocaleDateString()} - ${new Date(end).toLocaleDateString()}`;
  if (start) return `From ${new Date(start).toLocaleDateString()}`;
  if (end) return `Until ${new Date(end).toLocaleDateString()}`;
  return "Any";
}

export function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
