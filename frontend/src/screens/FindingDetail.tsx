import { useParams, useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { diagnosisFor, prescriptionFor, verificationFor, plainCause, statusOf } from "../lib/report";
import { pct, int, money, fmtMetric } from "../lib/format";
import { ROLE_LABEL } from "../lib/asks";
import { DecisionGate } from "../components/DecisionGate";
import type { Audience } from "../api/types";

export function FindingDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { report } = useReport();
  if (!report || !id) return null;

  const finding = report.findings.find((f) => f.id === id);
  if (!finding) return <p className="error">Finding not found.</p>;

  const diagnosis = diagnosisFor(report, finding);
  const prescription = prescriptionFor(report, finding);
  const verification = prescription ? verificationFor(report, prescription) : undefined;
  const status = statusOf(report, finding);

  return (
    <>
      <button className="back" onClick={() => nav(-1)}>&larr; Back</button>

      <div className="detail">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className={`pill ${status.cls}`}>{status.label}</span>
          <span className={`sev-dot sev-${finding.severity}`} />
          <span className="muted small" style={{ textTransform: "uppercase", fontWeight: 600, letterSpacing: ".04em" }}>
            {finding.severity}
          </span>
        </div>

        <h1>{finding.plain_summary}</h1>

        {/* Affected slice */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="role">{finding.tenant}</span>
          {Object.entries(finding.cohort).map(([k, v]) => (
            <span className="role" key={k}>{v}</span>
          ))}
          <span className="role">
            day {finding.window.from_day}&ndash;{finding.window.to_day}
          </span>
        </div>

        {/* Audience */}
        {finding.audience && finding.audience.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <span className="muted small">Owner: </span>
            {finding.audience.map((a) => (
              <span className="role" key={a}>{ROLE_LABEL[a as Audience] ?? a}</span>
            ))}
          </div>
        )}

        {/* Impact */}
        {finding.impact && (
          <>
            <div className="facts">
              <div className="fact">
                <div className="n">{int(finding.impact.conversations_affected)}</div>
                <div className="l">Conversations affected</div>
              </div>
              <div className="fact">
                <div className="n">{pct(finding.impact.share_of_traffic)}</div>
                <div className="l">Share of traffic</div>
              </div>
              <div className="fact">
                <div className="n">{finding.impact.days_running}d</div>
                <div className="l">Running</div>
              </div>
              {finding.impact.cost_usd != null && (
                <div className="fact">
                  <div className="n">{money(finding.impact.cost_usd)}</div>
                  <div className="l">Cost impact</div>
                </div>
              )}
            </div>

            {finding.impact.downstream && (
              <div className="facts">
                {finding.impact.downstream.would_have_resolved_at_baseline != null && (
                  <div className="fact">
                    <div className="n">{int(finding.impact.downstream.would_have_resolved_at_baseline)}</div>
                    <div className="l">Would have resolved</div>
                  </div>
                )}
                {finding.impact.downstream.silent_empty_responses != null && (
                  <div className="fact">
                    <div className="n">{int(finding.impact.downstream.silent_empty_responses)}</div>
                    <div className="l">Silent empty responses</div>
                  </div>
                )}
                {finding.impact.downstream.extra_turns_total != null && (
                  <div className="fact">
                    <div className="n">{int(finding.impact.downstream.extra_turns_total)}</div>
                    <div className="l">Extra turns</div>
                  </div>
                )}
                {finding.impact.downstream.extra_cost_usd != null && (
                  <div className="fact">
                    <div className="n">{money(finding.impact.downstream.extra_cost_usd)}</div>
                    <div className="l">Extra cost</div>
                  </div>
                )}
              </div>
            )}

            <div className="block">
              <h2>Derivation</h2>
              <p>{finding.impact.derivation}</p>
            </div>
          </>
        )}

        {/* Observed vs expected */}
        {finding.observed != null && finding.expected != null && (
          <div className="callout">
            <span className="k">{finding.metric}: </span>
            {fmtMetric(finding.metric, finding.expected)} &rarr; {fmtMetric(finding.metric, finding.observed)}
          </div>
        )}

        {/* What happened — plain cause */}
        <div className="block">
          <h2>What happened</h2>
          <p>{plainCause(diagnosis?.cause_class)}</p>
        </div>

        {/* If nothing changes */}
        {finding.if_nothing_changes && (
          <div className="block">
            <h2>If nobody acts</h2>
            <p className="consequence">{finding.if_nothing_changes}</p>
          </div>
        )}

        {/* Evidence */}
        {finding.evidence.length > 0 && (
          <details className="receipts">
            <summary />
            <div className="body">
              <ul>
                {finding.evidence.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          </details>
        )}

        {/* Diagnosis */}
        {diagnosis && (
          <>
            <hr className="divider" />
            <div className="block">
              <h2>Diagnosis</h2>
              <p>
                Cause: <strong>{diagnosis.cause_class}</strong>{" "}
                (confidence {pct(diagnosis.confidence)})
              </p>
              {diagnosis.attributed_change && (
                <p className="muted small">
                  Attributed to {diagnosis.attributed_change.kind} on day {diagnosis.attributed_change.day}
                </p>
              )}
              {diagnosis.evidence.length > 0 && (
                <details className="receipts" style={{ marginTop: 10 }}>
                  <summary />
                  <div className="body">
                    <ul>
                      {diagnosis.evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                </details>
              )}
            </div>
          </>
        )}

        {/* Prescription */}
        {prescription && (
          <>
            <hr className="divider" />
            <div className="block fix">
              <h2>Proposed fix</h2>
              <p><strong>{prescription.change_type}</strong> &rarr; {prescription.target}</p>
              <p>{prescription.description}</p>

              <div className="callout" style={{ marginTop: 12 }}>
                <p><span className="k">Asking approval for: </span>{prescription.decision.asking_approval_for}</p>
                <p style={{ marginTop: 6 }}>
                  <span className="k">Risk if wrong: </span>{prescription.decision.risk_if_diagnosis_wrong}
                </p>
                <p style={{ marginTop: 6 }}>
                  <span className="k">Would NOT ship if: </span>{prescription.decision.would_not_ship_if}
                </p>
              </div>

              <p className="muted small" style={{ marginTop: 8 }}>
                Predicted: {prescription.predicted_delta.metric}{" "}
                {fmtMetric(prescription.predicted_delta.metric, prescription.predicted_delta.from)}
                {" → "}
                {fmtMetric(prescription.predicted_delta.metric, prescription.predicted_delta.to)}
              </p>
            </div>
          </>
        )}

        {/* Verification / replay */}
        {verification && (
          <>
            <hr className="divider" />
            <div className="block fix">
              <h2>Replay verification</h2>
              <div className="replay">
                <div className="fact">
                  <div className="n">{fmtMetric(verification.metric, verification.before)}</div>
                  <div className="l">Before</div>
                </div>
                <div className="fact">
                  <div className="n">{fmtMetric(verification.metric, verification.after)}</div>
                  <div className="l">After</div>
                </div>
              </div>
              <p className="riskline">
                Verdict: <b>{verification.verdict.replace("_", " ")}</b>
                {verification.golden_set_pass != null && (
                  <> &middot; Golden set: {verification.golden_set_pass ? "passed" : "FAILED"}</>
                )}
              </p>
              {verification.prediction_error != null && (
                <p className="muted small">Prediction error: {pct(verification.prediction_error)}</p>
              )}
            </div>
          </>
        )}

        {/* Decision gate */}
        {prescription && <DecisionGate prescription={prescription} />}
      </div>
    </>
  );
}
