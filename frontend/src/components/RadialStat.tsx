interface RadialStatProps {
  value: number | null | undefined;
  label?: string;
  size?: number;
  strokeWidth?: number;
  color?: string;
}

export function RadialStat({ value, label, size = 84, strokeWidth = 7, color }: RadialStatProps) {
  const clamped = Math.max(0, Math.min(1, value ?? 0));
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped);
  const center = size / 2;

  return (
    <div className="radial-stat">
      <div className="radial-stat-wrap" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={center} cy={center} r={r} stroke="var(--border)" strokeWidth={strokeWidth} fill="none" />
          <circle
            cx={center}
            cy={center}
            r={r}
            stroke={color ?? "var(--accent)"}
            strokeWidth={strokeWidth}
            fill="none"
            strokeDasharray={c}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform={`rotate(-90 ${center} ${center})`}
          />
        </svg>
        <div className="radial-stat-value" style={{ fontSize: Math.max(12, size * 0.24) }}>
          {value == null ? "—" : `${Math.round(clamped * 100)}%`}
        </div>
      </div>
      {label && <div className="radial-stat-label">{label}</div>}
    </div>
  );
}
