import { useReport } from "../hooks/ReportContext";
import { ASKS } from "../lib/asks";

export function Gaps() {
  const { report } = useReport();
  if (!report) return null;

  const { gaps, metrics } = report;

  return (
    <>
      <p className="statusline">
        Measurement gaps &mdash; <span className="em">refused</span>
      </p>
      <p className="section-title">
        These operator questions cannot be answered with the data available.
        We refuse rather than invent a number.
      </p>

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
        <section className="strip">
          <p className="muted small" style={{ fontWeight: 600, marginBottom: 8 }}>Coverage &amp; Fidelity</p>
          {metrics.map((m) => (
            <p key={m.id} className="muted small" style={{ padding: "3px 0" }}>
              <span style={{ textTransform: "uppercase", fontSize: 11, fontWeight: 600, letterSpacing: ".04em", marginRight: 6 }}>
                {m.fidelity}
              </span>
              {m.name ?? m.id} &middot; coverage {(m.coverage.value * 100).toFixed(0)}% ({m.coverage.basis})
              {m.calibration && (
                <> &middot; calibration {(m.calibration.agreement * 100).toFixed(1)}% (n={m.calibration.n})</>
              )}
            </p>
          ))}
        </section>
      )}

      {gaps.length === 0 && (
        <p className="muted" style={{ padding: 40, textAlign: "center" }}>
          All operator questions can be answered with available data.
        </p>
      )}
    </>
  );
}
