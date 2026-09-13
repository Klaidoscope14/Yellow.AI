// Presentation helpers. Numbers/technical fields are secondary, so formatting
// stays consistent and plain.

export const pct = (v: number | null | undefined): string =>
  v == null ? "—" : (v * 100).toFixed(v * 100 < 10 ? 1 : 0) + "%";

export const int = (v: number | null | undefined): string =>
  v == null ? "—" : Number(v).toLocaleString();

export const money = (v: number | null | undefined): string =>
  v == null
    ? "—"
    : "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function fmtMetric(metric: string | undefined, v: number | null | undefined): string {
  if (v == null) return "—";
  if (metric && metric.includes("rate")) return pct(v);
  if (metric === "median_turns") return Number(v).toFixed(1) + " turns";
  return Number(v).toLocaleString();
}

export const lowerFirst = (s: string | undefined): string =>
  s ? s.charAt(0).toLowerCase() + s.slice(1) : "";
