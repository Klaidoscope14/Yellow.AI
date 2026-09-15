import type { Severity } from "../api/types";

const ORDER: Severity[] = ["critical", "high", "medium", "low"];
const COLOR_VAR: Record<Severity, string> = {
  critical: "var(--sev-critical)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  low: "var(--sev-low)",
};

/** Severity breakdown of the open regressions — fills the dead space beside
 * the KPI hero with something that's actually derived from the same data
 * the severity filter pills below use, not decoration. */
export function SeverityDonut({ counts }: { counts: Record<Severity, number> }) {
  const size = 92;
  const strokeWidth = 12;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const center = size / 2;
  const total = ORDER.reduce((sum, k) => sum + counts[k], 0);

  let acc = 0;
  const arcs = ORDER.map((k) => {
    const n = counts[k];
    if (!n || total === 0) return null;
    const dash = (n / total) * c;
    const arc = (
      <circle
        key={k}
        cx={center}
        cy={center}
        r={r}
        stroke={COLOR_VAR[k]}
        strokeWidth={strokeWidth}
        fill="none"
        strokeDasharray={`${dash} ${c - dash}`}
        strokeDashoffset={-acc}
        transform={`rotate(-90 ${center} ${center})`}
      />
    );
    acc += dash;
    return arc;
  });

  return (
    <div className="severity-donut-card">
      <h2>By severity</h2>
      <div className="severity-donut-body">
        <div className="severity-donut">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            <circle cx={center} cy={center} r={r} stroke="var(--border)" strokeWidth={strokeWidth} fill="none" />
            {total > 0 ? arcs : null}
          </svg>
          <div className="severity-donut-center">
            <span className="n">{total}</span>
            <span className="l">open</span>
          </div>
        </div>
        <ul className="severity-donut-legend">
          {ORDER.map((k) => {
            const pct = total > 0 ? (counts[k] / total) * 100 : 0;
            return (
              <li key={k}>
                <span className={`sev-dot ${k}`} />
                <span className="severity-donut-legend-label">{k}</span>
                <span className="severity-donut-legend-bar">
                  <span style={{ width: `${pct}%`, background: COLOR_VAR[k] }} />
                </span>
                <span className="severity-donut-legend-n">{counts[k]}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
