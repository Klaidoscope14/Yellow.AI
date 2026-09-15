import { useReport } from "../hooks/ReportContext";
import { ASKS } from "../lib/asks";
import { MetricGauge } from "../components/MetricGauge";

export function Gaps() {
  const { report } = useReport();
  if (!report) return null;

  const { gaps, metrics } = report;

  return (
    <div className="page-container page-container-wide">
      <div className="page-header">
        <h1>Diagnostics</h1>
        <p>
          {gaps.length} question{gaps.length !== 1 ? "s" : ""} we can&rsquo;t answer with the current data.
          What&rsquo;s needed to answer each is listed below.
        </p>
      </div>

      {gaps.map((g) => (
        <div className="refusal" key={g.ask_id}>
          <p className="q">{ASKS[g.ask_id] ?? g.ask_id}</p>
          <p className="why">{g.why}</p>

          {g.nearest_proxy && (
            <div className="need" style={{ marginBottom: 8 }}>
              <strong>Tempting proxy:</strong> {g.nearest_proxy}
              {g.why_the_proxy_misleads && (
                <span> &mdash; {g.why_the_proxy_misleads}</span>
              )}
            </div>
          )}

          {g.required_event && (
            <div className="need">
              <strong>What would make this answerable:</strong><br />
              Event: <code>{g.required_event.name}</code> &middot;
              Grain: <code>{g.required_event.grain}</code><br />
              Fields: {g.required_event.fields.join(", ")}<br />
              Owner: {g.required_event.owner}
            </div>
          )}

          <p className="muted small" style={{ marginTop: 8 }}>
            Verdict: {g.verdict.replace(/_/g, " ")}
          </p>
        </div>
      ))}

      {/* Coverage summary from metrics */}
      {metrics.length > 0 && (
        <section>
          <p className="muted small" style={{ fontWeight: 600, marginBottom: 12 }}>Coverage &amp; Fidelity</p>
          <div className="metric-gauge-grid">
            {metrics.slice(0, 8).map((m) => (
              <MetricGauge
                key={m.id}
                eyebrow={`${m.fidelity} metric`}
                title={m.name ?? m.id}
                indexLabel={`${m.coverage.basis} coverage`}
                value={m.coverage.value}
                note={
                  m.calibration
                    ? `calibration ${(m.calibration.agreement * 100).toFixed(1)}% (n=${m.calibration.n})`
                    : undefined
                }
              />
            ))}
          </div>
        </section>
      )}

      {gaps.length === 0 && (
        <p className="muted" style={{ padding: 40, textAlign: "center" }}>
          All operator questions can be answered with available data.
        </p>
      )}
    </div>
  );
}
