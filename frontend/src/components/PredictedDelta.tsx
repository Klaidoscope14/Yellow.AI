import { fmtMetric, humanizeMetric } from "../lib/format";
import type { PredictedDelta as PredictedDeltaData } from "../api/types";

/** The promised payoff of a fix, made to read as unambiguously positive —
 * not another before/after bar chart. Leans on conventions people already
 * know (struck-through old value → bold new value, a colored delta badge)
 * so the improvement registers before anyone reads a number: the Von
 * Restorff effect (this is the one good-news moment on an otherwise
 * evidence-heavy page) plus recognition over recall (no bar lengths to
 * compare — the badge just says how much better). */
export function PredictedDelta({ delta }: { delta: PredictedDeltaData }) {
  const { metric, from, to } = delta;
  const changed = to !== from;
  const pctChange = from !== 0 ? ((to - from) / Math.abs(from)) * 100 : null;
  const up = to > from;

  return (
    <div className="predicted-delta">
      <p className="predicted-delta-label">Predicted outcome if approved</p>
      <div className="predicted-delta-row">
        <span className="predicted-delta-from">{fmtMetric(metric, from)}</span>
        <span className="predicted-delta-arrow" aria-hidden>&rarr;</span>
        <span className="predicted-delta-to">{fmtMetric(metric, to)}</span>
        {changed && pctChange != null && (
          <span className="predicted-delta-badge">
            {up ? "↑" : "↓"} {Math.abs(Math.round(pctChange))}%
          </span>
        )}
      </div>
      <p className="predicted-delta-metric">{humanizeMetric(metric)}</p>
    </div>
  );
}
