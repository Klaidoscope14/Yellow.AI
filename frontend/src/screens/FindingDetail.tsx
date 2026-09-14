import { useParams, useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { diagnosisFor, prescriptionFor, verificationFor, plainCause, statusOf } from "../lib/report";
import { pct, int, money, fmtMetric, lowerIsWorseFor } from "../lib/format";
import { ROLE_LABEL } from "../lib/asks";
import { DecisionGate } from "../components/DecisionGate";
import { RadialStat } from "../components/RadialStat";
import { ComparisonBars } from "../components/ComparisonBars";
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
      <button className="back" onClick={() => nav("/")}>&larr; Close</button>

      <div className="detail">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className={`pill ${status.cls}`}>{status.label}</span>
          <span className={`sev-dot ${finding.severity}`} />
          <span className={`sev-label ${finding.severity}`}>{finding.severity}</span>
        </div>

        <h1>{finding.plain_summary}</h1>

        {/* Affected slice — descriptive metadata reads as a breadcrumb, not tag-boxes */}
        <p className="breadcrumb">
          {finding.tenant}
          {Object.values(finding.cohort).map((v, i) => (
            <span key={i}>
              <span className="sep">&middot;</span>
              {v}
            </span>
          ))}
          <span className="sep">&middot;</span>
          Day {finding.window.from_day}&ndash;{finding.window.to_day}
        </p>

        {/* Audience */}
        {finding.audience && finding.audience.length > 0 && (
          <p className="owner-line">
            Owner: <strong>{finding.audience.map((a) => ROLE_LABEL[a as Audience] ?? a).join(", ")}</strong>
          </p>
        )}

        {/* Impact — one stat rail, no boxed tiles */}
        {finding.impact && (
          <>
            <div className="stat-rail">
              <div className="stat">
                <span className="n">{int(finding.impact.conversations_affected)}</span>
                <span className="l">Conversations affected</span>
              </div>
              <div className="stat radial">
                <RadialStat value={finding.impact.share_of_traffic} label="Share of traffic" size={60} strokeWidth={5} />
              </div>
              <div className="stat">
                <span className="n">{finding.impact.days_running}d</span>
                <span className="l">Running</span>
              </div>
              {finding.impact.cost_usd != null && (
                <div className="stat">
                  <span className="n">{money(finding.impact.cost_usd)}</span>
                  <span className="l">Cost impact</span>
                </div>
              )}
            </div>

            {finding.impact.downstream && (
              <div className="stat-rail">
                {finding.impact.downstream.would_have_resolved_at_baseline != null && (
                  <div className="stat">
                    <span className="n">{int(finding.impact.downstream.would_have_resolved_at_baseline)}</span>
                    <span className="l">Would have resolved</span>
                  </div>
                )}
                {finding.impact.downstream.silent_empty_responses != null && (
                  <div className="stat">
                    <span className="n">{int(finding.impact.downstream.silent_empty_responses)}</span>
                    <span className="l">Silent empty responses</span>
                  </div>
                )}
                {finding.impact.downstream.extra_turns_total != null && (
                  <div className="stat">
                    <span className="n">{int(finding.impact.downstream.extra_turns_total)}</span>
                    <span className="l">Extra turns</span>
                  </div>
                )}
                {finding.impact.downstream.extra_cost_usd != null && (
                  <div className="stat">
                    <span className="n">{money(finding.impact.downstream.extra_cost_usd)}</span>
                    <span className="l">Extra cost</span>
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
          <ComparisonBars
            label={finding.metric}
            baseline={finding.expected}
            baselineLabel="Expected"
            observed={finding.observed}
            observedLabel="Observed"
            format={(v) => fmtMetric(finding.metric, v)}
            lowerIsWorse={lowerIsWorseFor(finding.metric)}
          />
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
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <RadialStat value={diagnosis.confidence} size={52} strokeWidth={5} />
                <div>
                  <p>
                    Cause: <strong>{diagnosis.cause_class}</strong>
                  </p>
                  {diagnosis.attributed_change && (
                    <p className="muted small">
                      Attributed to {diagnosis.attributed_change.kind} on day {diagnosis.attributed_change.day}
                    </p>
                  )}
                </div>
              </div>
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
              <ComparisonBars
                label={verification.metric}
                baseline={verification.before}
                baselineLabel="Before"
                observed={verification.after}
                observedLabel="After"
                format={(v) => fmtMetric(verification.metric, v)}
                statusOverride={
                  verification.verdict === "improved"
                    ? "better"
                    : verification.verdict === "regressed"
                    ? "worse"
                    : "neutral"
                }
              />
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
