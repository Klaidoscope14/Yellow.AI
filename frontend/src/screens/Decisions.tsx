import { useReport } from "../hooks/ReportContext";
import { regressions, prescriptionFor } from "../lib/report";
import { pct, fmtMetric } from "../lib/format";

export function Decisions() {
  const { report } = useReport();
  if (!report) return null;

  const regs = regressions(report);

  const decided = regs
    .map((f) => {
      const rx = prescriptionFor(report, f);
      return rx?.approval ? { finding: f, prescription: rx, approval: rx.approval } : null;
    })
    .filter(Boolean) as { finding: (typeof regs)[0]; prescription: NonNullable<ReturnType<typeof prescriptionFor>>; approval: NonNullable<NonNullable<ReturnType<typeof prescriptionFor>>["approval"]> }[];

  const sa = report.self_assessment;

  return (
    <>
      <p className="statusline">
        Decision history &amp; <span className="em">self-assessment</span>
      </p>

      {/* Decision audit trail */}
      <section>
        <div className="block">
          <h2>Decisions recorded</h2>
        </div>

        {decided.length === 0 && (
          <p className="muted small" style={{ padding: 20 }}>No decisions recorded yet.</p>
        )}

        {decided.map(({ finding, prescription, approval }) => (
          <div
            key={prescription.id}
            className="card"
            style={{ cursor: "default" }}
          >
            <p style={{ margin: "0 0 8px" }}>
              <strong>{finding.plain_summary}</strong>
            </p>
            <p className="muted small">
              {prescription.change_type} &middot;{" "}
              <span style={{
                fontWeight: 600,
                color: approval.verdict === "accepted" ? "var(--status-ok-ink)" : "var(--status-rej-ink)",
              }}>
                {approval.verdict.toUpperCase()}
              </span>
              {" "}&middot; by {approval.decided_by} &middot; {new Date(approval.at).toLocaleString()}
            </p>
            {approval.reason && (
              <p className="muted small" style={{ marginTop: 4 }}>
                &ldquo;{approval.reason}&rdquo;
              </p>
            )}
          </div>
        ))}
      </section>

      <hr className="divider" />

      {/* Self-assessment */}
      <section>
        <div className="block">
          <h2>Self-assessment</h2>
        </div>

        {report.verifications.length > 0 ? (
          <>
            <p className="muted small" style={{ marginBottom: 12 }}>
              {report.verifications.length} verification{report.verifications.length !== 1 ? "s" : ""} recorded.
              This is the system&rsquo;s honest hit rate over fixes it actually verified.
            </p>

            {report.verifications.map((v) => {
              const rx = report.prescriptions.find((p) => p.id === v.prescription_id);
              return (
                <div key={v.prescription_id} className="card" style={{ cursor: "default" }}>
                  <p style={{ margin: "0 0 6px" }}>
                    <strong>{rx?.change_type ?? "—"}</strong> &rarr; {rx?.target ?? "—"}
                  </p>
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                    <span className="muted small">
                      {v.metric}: {fmtMetric(v.metric, v.before)} &rarr; {fmtMetric(v.metric, v.after)}
                    </span>
                    <span className={`pill ${v.verdict === "improved" ? "approved" : v.verdict === "regressed" ? "needs" : "rejected"}`}>
                      {v.verdict.replace("_", " ")}
                    </span>
                    {v.golden_set_pass != null && (
                      <span className="muted small">
                        Golden set: {v.golden_set_pass ? "passed" : "FAILED"}
                      </span>
                    )}
                  </div>
                  {rx && v.prediction_error != null && (
                    <p className="muted small" style={{ marginTop: 4 }}>
                      Predicted: {fmtMetric(rx.predicted_delta.metric, rx.predicted_delta.from)}
                      {" → "}
                      {fmtMetric(rx.predicted_delta.metric, rx.predicted_delta.to)}
                      {" · "}
                      prediction error {pct(v.prediction_error)}
                    </p>
                  )}
                </div>
              );
            })}
          </>
        ) : (
          <p className="muted small" style={{ padding: 20 }}>No verifications recorded.</p>
        )}

        {sa && Object.keys(sa).length > 0 && (
          <details className="receipts" style={{ marginTop: 16 }}>
            <summary>Raw self-assessment data</summary>
            <div className="body">
              <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>
                {JSON.stringify(sa, null, 2)}
              </pre>
            </div>
          </details>
        )}
      </section>
    </>
  );
}
