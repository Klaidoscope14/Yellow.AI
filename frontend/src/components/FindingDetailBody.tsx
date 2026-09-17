import { diagnosisFor, prescriptionFor, verificationFor, plainCause, statusOf } from "../lib/report";
import {
  pct, int, money, fmtMetric, lowerIsWorseFor,
  claimSentence, usersSentence,
} from "../lib/format";
import { ROLE_LABEL } from "../lib/asks";
import { DecisionGate } from "./DecisionGate";
import { ComparisonBars } from "./ComparisonBars";
import { PredictedDelta } from "./PredictedDelta";
import type { Audience, Finding, Report } from "../api/types";

export function FindingDetailBody({
  report,
  finding,
  showDiagnosis = true,
}: {
  report: Report;
  finding: Finding;
  /** Hide the Diagnosis section (cause narrative + attribution). Shown by default. */
  showDiagnosis?: boolean;
}) {
  const diagnosis = diagnosisFor(report, finding);
  const prescription = prescriptionFor(report, finding);
  const verification = prescription ? verificationFor(report, prescription) : undefined;
  const status = statusOf(report, finding);
  const owner = (finding.audience ?? []).map((a) => ROLE_LABEL[a as Audience] ?? a).join(", ");

  return (
    <>
      {/* ---- HERO ---- */}
      <header className="finding-hero">
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

      {/* ---- IMPACT: one hero number, everything else as inline context.
              A single stat carries the human-facing headline; secondary
              facts (traffic share, duration, cost) run as one caption row. */}
      {finding.impact && (
        <section className="impact-hero">
          <div className="impact-hero-primary">
            <span className="impact-hero-n">{int(finding.impact.conversations_affected)}</span>
            <span className="impact-hero-l">conversations affected</span>
          </div>
          <p className="impact-hero-context">
            <strong>{pct(finding.impact.share_of_traffic)}</strong> of tenant traffic
            <span className="sep">&middot;</span>
            <strong>{finding.impact.days_running} days</strong> running
            {finding.impact.cost_usd != null && (
              <>
                <span className="sep">&middot;</span>
                <strong>{money(finding.impact.cost_usd)}</strong> total cost
              </>
            )}
          </p>
        </section>
      )}

      {/* ---- CLAIM + BAR: no tinted band; typography carries the emphasis */}
      {finding.observed != null && finding.expected != null && (
        <section className="finding-block">
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
        </section>
      )}

      {/* ---- What happened to these users: sentence only, no duplicate tiles */}
      {finding.impact?.downstream && usersSentence(finding.impact.downstream) && (
        <section className="finding-block">
          <h2>What happened to these users</h2>
          <p className="lead">{usersSentence(finding.impact.downstream)}</p>
        </section>
      )}

      {/* ---- Why not a regression (lookalikes only) */}
      {finding.not_a_regression_because && (
        <section className="finding-block consequence-block">
          <h2>Why this isn&rsquo;t a regression</h2>
          <p className="consequence">{finding.not_a_regression_because}</p>
        </section>
      )}

      {/* ---- If nobody acts */}
      {finding.if_nothing_changes && (
        <section className="finding-block consequence-block">
          <h2>If nobody acts</h2>
          <p className="consequence">{finding.if_nothing_changes}</p>
        </section>
      )}

      {/* ---- Diagnosis (consolidated with the plain-cause narrative) */}
      {showDiagnosis && diagnosis && (
        <section className="finding-block">
          <h2>Diagnosis</h2>
          <p className="lead">{plainCause(diagnosis.cause_class)}</p>
          <div className="diagnosis-body">
            <p>
              Cause: <strong>{diagnosis.cause_class}</strong>
            </p>
            {diagnosis.attributed_change && (
              <p className="muted small">
                Attributed to {diagnosis.attributed_change.kind} on day {diagnosis.attributed_change.day}
              </p>
            )}
          </div>
        </section>
      )}

      {/* ---- How we computed this — inline collapsible, not a sidebar card */}
      {finding.impact && (
        <details className="finding-block inline-receipts">
          <summary>How we computed this</summary>
          <p>
            {finding.impact.derivation.split(/(?<=\.)\s+/).map((sentence, i) =>
              /baseline/i.test(sentence) ? (
                <strong key={i} className="baseline-highlight">{sentence} </strong>
              ) : (
                <span key={i}>{sentence} </span>
              ),
            )}
          </p>
        </details>
      )}

      {/* ---- Evidence chain — inline collapsible, pre-expanded */}
      {finding.evidence.length > 0 && (
        <details className="finding-block inline-receipts" open>
          <summary>Evidence chain</summary>
          <ul className="evidence-list">
            {finding.evidence.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </details>
      )}

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
    </>
  );
}
