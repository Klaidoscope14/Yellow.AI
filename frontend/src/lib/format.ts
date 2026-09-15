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

// Direction inference for comparison visuals: most rate metrics here are
// "goodness" rates (resolution_rate, containment_rate) where a drop is the
// harm. A handful are "badness" rates or costs (miss/error/fail/cost/latency/
// turns) where a rise is the harm — those need the inverse reading.
const HIGHER_IS_WORSE = /(miss|error|fail|cost|latency|turns|churn|abandon)/i;
export function lowerIsWorseFor(metric: string | undefined): boolean {
  return !metric || !HIGHER_IS_WORSE.test(metric);
}

export function humanizeMetric(metric: string | undefined): string {
  if (!metric) return "This metric";
  return metric.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// The PS's own example — "Resolution in cohort X fell from 0.86 to 0.31" —
// as a literal, checkable sentence built from the same expected/observed
// numbers the bar chart renders. Nothing here is asserted beyond the data.
export function claimSentence(metric: string | undefined, expected: number, observed: number): string {
  const label = humanizeMetric(metric);
  const dir = observed < expected ? "fell" : observed > expected ? "rose" : "stayed flat";
  return `${label} in this cohort ${dir} from ${fmtMetric(metric, expected)} to ${fmtMetric(metric, observed)}.`;
}

const DOWNSTREAM_LABELS: Record<string, string> = {
  would_have_resolved_at_baseline: "Would have resolved at baseline",
  deficit: "Would have resolved and didn't",
  silent_empty_responses: "Silent empty responses",
  extra_turns_total: "Extra turns",
  extra_cost_usd: "Extra cost",
  unplanned_handoffs: "Reached a human unnecessarily",
  abandoned: "Abandoned",
};
export function downstreamLabel(key: string): string {
  return DOWNSTREAM_LABELS[key] ?? humanizeMetric(key);
}
export const isMoneyKey = (key: string): boolean => /cost|usd/i.test(key);

// A plain-English synthesis of "what happened to these users" — built only
// from whatever downstream numbers the backend actually computed, never
// invented. Falls back to nothing if there's no downstream data at all.
export function usersSentence(downstream: Record<string, number | undefined> | undefined): string | null {
  if (!downstream) return null;
  const parts: string[] = [];
  if (downstream.deficit != null) {
    parts.push(`${int(downstream.deficit)} conversations that would have resolved did not`);
  } else if (downstream.would_have_resolved_at_baseline != null) {
    parts.push(`about ${int(downstream.would_have_resolved_at_baseline)} conversations would have resolved at baseline`);
  }
  if (downstream.unplanned_handoffs != null) {
    parts.push(`${int(downstream.unplanned_handoffs)} reached a human who wasn't meant to be involved`);
  }
  if (downstream.abandoned != null) {
    parts.push(`${int(downstream.abandoned)} were abandoned`);
  }
  if (downstream.silent_empty_responses != null) {
    parts.push(`${int(downstream.silent_empty_responses)} got a silent empty response`);
  }
  if (downstream.extra_turns_total != null) {
    parts.push(`${int(downstream.extra_turns_total)} extra turns were added`);
  }
  if (parts.length === 0) return null;
  const joined = parts.length === 1 ? parts[0] : parts.slice(0, -1).join("; ") + "; " + parts[parts.length - 1];
  return joined.charAt(0).toUpperCase() + joined.slice(1) + ".";
}
