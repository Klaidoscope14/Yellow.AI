import { useParams, useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { diagnosisFor, prescriptionFor, verificationFor, plainCause, statusOf } from "../lib/report";
import {
  pct, int, money, fmtMetric, lowerIsWorseFor,
  claimSentence, usersSentence,
} from "../lib/format";
import { ROLE_LABEL } from "../lib/asks";
import { DecisionGate } from "../components/DecisionGate";
import { RadialStat } from "../components/RadialStat";
import { ComparisonBars } from "../components/ComparisonBars";
import { PredictedDelta } from "../components/PredictedDelta";
import type { Audience } from "../api/types";

const SEVERITY_POSITION: Record<string, number> = { low: 12.5, medium: 37.5, high: 62.5, critical: 87.5 };

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
  const owner = (finding.audience ?? []).map((a) => ROLE_LABEL[a as Audience] ?? a).join(", ");
  // Diagnosis evidence (why we believe the cause) and finding evidence (why
  // this is a regression at all) used to live in two separate "Evidence"
  // boxes — same section, so they're merged into one list here.
  const allEvidence = Array.from(new Set([...(diagnosis?.evidence ?? []), ...finding.evidence]));

  return (
    <div className="page-container finding-page">
      <button className="back" onClick={() => nav("/")}>&larr; Back to Incidents</button>

      {/* ---- HERO ---- */}
      <header className="finding-hero-card">
        <div className="finding-hero-badges">
          <span className={`pill ${status.cls}`}>{status.label}</span>
          <span className={`sev-label ${finding.severity}`}>
            <span className={`sev-dot ${finding.severity}`} />
            {finding.severity} severity
          </span>
        </div>

        <h1 className="finding-title">{finding.plain_summary}</h1>

        <div className="finding-hero-meta">
          <div className="finding-hero-meta-item">
            <span className="l">Tenant</span>
            <span className="v">{finding.tenant}</span>
          </div>
          <div className="finding-hero-meta-item">
            <span className="l">Cohort</span>
            <span className="v">{Object.values(finding.cohort).join(" / ")}</span>
          </div>
          <div className="finding-hero-meta-item">
            <span className="l">Window</span>
            <span className="v">Day {finding.window.from_day}&ndash;{finding.window.to_day}</span>
          </div>
          {owner && (
            <div className="finding-hero-meta-item">
              <span className="l">Owner</span>
              <span className="v">{owner}</span>
            </div>
          )}
        </div>
      </header>

      {/* ---- Four labeled groups instead of a left/right bento split:
              Findings (what was detected), Impact (who/how much it hurt),
              Diagnosis (why it happened), Evidence (what backs that up).
              Same data as before, just arranged so each card sits under
              the group it actually belongs to. ---- */}
      <div className="finding-groups">
        {/* FINDINGS — the detected regression itself */}
        {finding.observed != null && finding.expected != null && (
          <section className="finding-group">
            <h2 className="finding-group-title">Findings</h2>
            <div className="finding-group-cards">
              <div className="finding-card">
                <p className="claim-sentence">
                  {claimSentence(finding.metric, finding.expected, finding.observed)}
                </p>
                <ComparisonBars
                  label={finding.metric}
                  baseline={finding.expected}
                  baselineLabel="Expected"
                  observed={finding.observed}
                  observedLabel="Observed"
                  format={(v) => fmtMetric(finding.metric, v)}
                  lowerIsWorse={lowerIsWorseFor(finding.metric)}
                />
              </div>
            </div>
          </section>
        )}

        {/* IMPACT — who/how much it hurt. The headline stats get their own
            small cards; the two narrative consequences follow underneath. */}
        {(finding.impact || finding.if_nothing_changes) && (
          <section className="finding-group">
            <h2 className="finding-group-title">Impact</h2>

            {finding.impact && (
              <div className="finding-stat-row">
                <div className="finding-stat-card">
                  <span className="finding-stat-n">{int(finding.impact.conversations_affected)}</span>
                  <span className="finding-stat-l">conversations affected</span>
                </div>
                <div className="finding-stat-card">
                  <span className="finding-stat-n">{pct(finding.impact.share_of_traffic)}</span>
                  <span className="finding-stat-l">of tenant traffic</span>
                </div>
                <div className="finding-stat-card">
                  <span className="finding-stat-n">{finding.impact.days_running}</span>
                  <span className="finding-stat-l">days running</span>
                </div>
                {finding.impact.cost_usd != null && (
                  <div className="finding-stat-card">
                    <span className="finding-stat-n">{money(finding.impact.cost_usd)}</span>
                    <span className="finding-stat-l">total cost</span>
                  </div>
                )}
              </div>
            )}

            <div className="finding-group-cards">
              {finding.impact?.downstream && usersSentence(finding.impact.downstream) && (
                <div className="finding-card">
                  <h2>What happened to these users</h2>
                  <p className="lead">{usersSentence(finding.impact.downstream)}</p>
                </div>
              )}

              {finding.if_nothing_changes && (
                <div className="finding-card consequence-card">
                  <h2>If nobody acts</h2>
                  <p className="consequence">{finding.if_nothing_changes}</p>
                </div>
              )}
            </div>
          </section>
        )}

        {/* DIAGNOSIS — why it happened, and how sure we are */}
        {diagnosis && (
          <section className="finding-group">
            <h2 className="finding-group-title">Diagnosis</h2>
            <div className="finding-group-cards">
              <div className="finding-card diagnosis-card">
                <div className="diagnosis-body">
                  <RadialStat value={diagnosis.confidence} size={64} strokeWidth={6} />
                  <div>
                    <p className="lead" style={{ marginBottom: 6 }}>{plainCause(diagnosis.cause_class)}</p>
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
              </div>

              <div className="finding-card severity-meter-card">
                <h2>Severity</h2>
                <div className="severity-meter">
                  <span className="severity-meter-marker" style={{ left: `${SEVERITY_POSITION[finding.severity]}%` }} />
                </div>
                <div className="severity-meter-scale">
                  <span>Low</span>
                  <span>Medium</span>
                  <span>High</span>
                  <span>Critical</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* EVIDENCE — what backs the diagnosis up. Merges the diagnosis's
            own evidence with the finding's, which used to be two
            separately-labeled "Evidence" lists in two different
            dropdowns; de-duplicated into one plain card. */}
        {(finding.impact || allEvidence.length > 0) && (
          <section className="finding-group">
            <h2 className="finding-group-title">Evidence</h2>
            <div className="finding-group-cards">
              {finding.impact && (
                <div className="finding-card">
                  <h2>How we computed this</h2>
                  <p>
                    {finding.impact.derivation.split(/(?<=\.)\s+/).map((sentence, i) =>
                      /baseline/i.test(sentence) ? (
                        <strong key={i} className="baseline-highlight">{sentence} </strong>
                      ) : (
                        <span key={i}>{sentence} </span>
                      ),
                    )}
                  </p>
                </div>
              )}

              {allEvidence.length > 0 && (
                <div className="finding-card">
                  <h2>Chain</h2>
                  <ul className="evidence-list">
                    {allEvidence.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </section>
        )}
      </div>

      {/* ---- PROPOSAL: what Nexus wants to change ---- */}
      {prescription && (
        <section className="fix-panel">
          <div className="fix-panel-head">
            <span className="fix-panel-eyebrow">Proposal</span>
            <span className="fix-panel-type">{prescription.change_type} &rarr; {prescription.target}</span>
          </div>
          <p className="fix-panel-desc">{prescription.description}</p>

          <div className="fix-panel-decision-grid">
            <div className="fix-decision-item">
              <span className="fix-decision-label">Asking approval for</span>
              <p>{prescription.decision.asking_approval_for}</p>
            </div>
            <div className="fix-decision-item">
              <span className="fix-decision-label">Risk if wrong</span>
              <p>{prescription.decision.risk_if_diagnosis_wrong}</p>
            </div>
            <div className="fix-decision-item">
              <span className="fix-decision-label">Would NOT ship if</span>
              <p>{prescription.decision.would_not_ship_if}</p>
            </div>
          </div>

          <PredictedDelta delta={prescription.predicted_delta} />
        </section>
      )}

      {/* ---- Replay verification ---- */}
      {verification && (
        <section className="finding-block replay-block">
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
        </section>
      )}

      {/* ---- Decision ---- */}
      {prescription && (
        <section className="decision-panel-wrap">
          <p className="decision-panel-eyebrow">Decision</p>

          <DecisionGate prescription={prescription} />
        </section>
      )}
    </div>
  );
}
