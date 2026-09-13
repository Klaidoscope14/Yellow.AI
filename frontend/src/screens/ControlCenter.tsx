import { useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { regressions, dismissed, statusOf, needsDecisionCount } from "../lib/report";
import { pct, int } from "../lib/format";
import type { Finding, Report } from "../api/types";

function severityCls(s: string) {
  return `sev-dot sev-${s}`;
}

function FindingCard({ finding, report }: { finding: Finding; report: Report }) {
  const nav = useNavigate();
  const status = statusOf(report, finding);
  return (
    <button className="card" onClick={() => nav(`/finding/${finding.id}`)}>
      <p className="claim">
        <span className={severityCls(finding.severity)} />
        {finding.plain_summary}
      </p>
      <div className="meta">
        <span className="traffic">
          {finding.tenant} &middot; {Object.values(finding.cohort).join(" / ")}
          {finding.impact ? ` · ${int(finding.impact.conversations_affected)} conversations` : ""}
          {finding.impact ? ` · ${finding.impact.days_running}d` : ""}
        </span>
        <span className={`pill ${status.cls}`}>{status.label}</span>
      </div>
    </button>
  );
}

export function ControlCenter() {
  const { report } = useReport();
  const nav = useNavigate();
  if (!report) return null;

  const regs = regressions(report);
  const dism = dismissed(report);
  const pending = needsDecisionCount(report);
  const verified = report.verifications.filter((v) => v.verdict === "improved").length;

  return (
    <>
      <p className="statusline">
        Agent reliability:{" "}
        <span className="em">{pending > 0 ? "NEEDS ATTENTION" : "ALL CLEAR"}</span>
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 22 }}>
        <span className="pill needs">{regs.length} regression{regs.length !== 1 ? "s" : ""} found</span>
        <span className="pill approved">{dism.length} dismissed</span>
        {pending > 0 && <span className="pill needs">{pending} awaiting decision</span>}
        {verified > 0 && <span className="pill approved">{verified} verified fix{verified !== 1 ? "es" : ""}</span>}
        {report.gaps.length > 0 && (
          <span className="pill rejected">{report.gaps.length} measurement gap{report.gaps.length !== 1 ? "s" : ""}</span>
        )}
      </div>

      <section>
        {regs
          .sort((a, b) => severityRank(b.severity) - severityRank(a.severity))
          .map((f) => (
            <FindingCard key={f.id} finding={f} report={report} />
          ))}
      </section>

      {dism.length > 0 && (
        <section className="strip">
          <p className="muted small" style={{ marginBottom: 8 }}>
            We examined {dism.length} suspicious pattern{dism.length !== 1 ? "s" : ""} and cleared them.{" "}
            <button className="linkbtn" onClick={() => nav("/dismissed")}>
              See why &rsaquo;
            </button>
          </p>
        </section>
      )}

      {report.gaps.length > 0 && (
        <section className="strip">
          <p className="muted small">
            {report.gaps.length} operator question{report.gaps.length !== 1 ? "s" : ""} we refused to answer.{" "}
            <button className="linkbtn" onClick={() => nav("/gaps")}>
              See what&rsquo;s missing &rsaquo;
            </button>
          </p>
        </section>
      )}

      {report.standard.length > 0 && (
        <section className="strip">
          <p className="muted small" style={{ fontWeight: 600, marginBottom: 6 }}>Deployment Standard</p>
          {report.standard.slice(0, 6).map((s, i) => (
            <p key={i} className="muted small">
              {s.tenant} &middot; {s.metric} &middot; best {pct(s.best)} &middot; median {pct(s.median)}
              {s.deficit != null ? ` · deficit ${pct(s.deficit)}` : ""}
            </p>
          ))}
        </section>
      )}
    </>
  );
}

function severityRank(s: string): number {
  return { critical: 4, high: 3, medium: 2, low: 1 }[s] ?? 0;
}
