interface ComparisonBarsProps {
  label?: string;
  baseline: number;
  baselineLabel?: string;
  observed: number;
  observedLabel?: string;
  format: (v: number) => string;
  /** true = a lower observed value is the bad outcome (default). false = higher is bad. */
  lowerIsWorse?: boolean;
  /** Overrides the computed better/worse color — use when direction is known (e.g. a verdict), not inferred. */
  statusOverride?: "better" | "worse" | "neutral";
}

export function ComparisonBars({
  label,
  baseline,
  baselineLabel = "Baseline",
  observed,
  observedLabel = "Observed",
  format,
  lowerIsWorse = true,
  statusOverride,
}: ComparisonBarsProps) {
  const max = Math.max(Math.abs(baseline), Math.abs(observed), 0.0001);
  const basePct = (Math.abs(baseline) / max) * 100;
  const obsPct = (Math.abs(observed) / max) * 100;
  const computedWorse = lowerIsWorse ? observed < baseline : observed > baseline;
  const obsClass =
    statusOverride === "better" ? "better" : statusOverride === "worse" ? "worse" : statusOverride === "neutral" ? "base" : computedWorse ? "worse" : "better";

  return (
    <div className="compare-bars">
      {label && <div className="compare-bars-label">{label}</div>}
      <div className="compare-bar-row">
        <span className="compare-bar-tag">{baselineLabel}</span>
        <div className="compare-bar-track">
          <div className="compare-bar-fill base" style={{ width: `${basePct}%` }} />
        </div>
        <span className="compare-bar-value">{format(baseline)}</span>
      </div>
      <div className="compare-bar-row">
        <span className="compare-bar-tag">{observedLabel}</span>
        <div className="compare-bar-track">
          <div className={`compare-bar-fill ${obsClass}`} style={{ width: `${obsPct}%` }} />
        </div>
        <span className="compare-bar-value">{format(observed)}</span>
      </div>
    </div>
  );
}
