interface MetricGaugeProps {
  eyebrow: string;
  title: string;
  indexLabel: string;
  value: number | null | undefined;
  note?: string;
}

const ARC_FRACTION = 0.75; // 270° sweep, 90° gap at the bottom
const ROTATE = 135; // centers the gap at the bottom

function rating(value: number): "GOOD" | "FAIR" | "NEEDS WORK" {
  if (value >= 0.8) return "GOOD";
  if (value >= 0.5) return "FAIR";
  return "NEEDS WORK";
}

export function MetricGauge({ eyebrow, title, indexLabel, value, note }: MetricGaugeProps) {
  const clamped = Math.max(0, Math.min(1, value ?? 0));
  const score = clamped * 100;
  const size = 112;
  const strokeWidth = 10;
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const center = size / 2;
  const trackLen = c * ARC_FRACTION;
  const progressLen = trackLen * clamped;

  return (
    <div className="metric-gauge-card">
      <p className="metric-gauge-eyebrow">{eyebrow}</p>
      <h3 className="metric-gauge-title">{title}</h3>

      <div className="metric-gauge-body">
        <div className="metric-gauge-index-col">
          <span className="metric-gauge-index-label">{indexLabel}</span>
          {note && <span className="metric-gauge-note">{note}</span>}
        </div>

        <div className="metric-gauge-arc-wrap" style={{ width: size, height: size }}>
          <div className="metric-gauge-badge">
            {score.toFixed(1)}/100 ({rating(clamped)})
          </div>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            <circle
              cx={center}
              cy={center}
              r={r}
              stroke="var(--border)"
              strokeWidth={strokeWidth}
              fill="none"
              strokeDasharray={`${trackLen} ${c - trackLen}`}
              strokeLinecap="round"
              transform={`rotate(${ROTATE} ${center} ${center})`}
            />
            <circle
              cx={center}
              cy={center}
              r={r}
              stroke="#e8628f"
              strokeWidth={strokeWidth}
              fill="none"
              strokeDasharray={`${progressLen} ${c - progressLen}`}
              strokeLinecap="round"
              transform={`rotate(${ROTATE} ${center} ${center})`}
            />
          </svg>
          <div className="metric-gauge-center">
            <span className="metric-gauge-center-label">Score</span>
            <span className="metric-gauge-center-value">{score.toFixed(1)}</span>
          </div>
        </div>
      </div>

      <div className="metric-gauge-footer">
        <span>
          Rating: <strong>{rating(clamped)}</strong>
        </span>
        <span>Score: {score.toFixed(1)}%</span>
      </div>
    </div>
  );
}
