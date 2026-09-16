import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { regressions, dismissed, needsDecisionCount } from "../lib/report";
import { SearchIcon } from "../components/Icon";
import { useCountUp } from "../hooks/useCountUp";
import { IncidentsTable } from "../components/IncidentsTable";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

// One hero number card + a muted context row. The number that requires
// action gets weight; reference counts become caption typography.
function KpiHero({ pending }: { pending: number }) {
  const shown = useCountUp(pending);
  return (
    <div className="kpi-hero">
      <span className="kpi-hero-n">{shown}</span>
      <span className="kpi-hero-l">{pending === 1 ? "fix awaiting your call" : "fixes awaiting your call"}</span>
    </div>
  );
}

export function ControlCenter() {
  const { report } = useReport();
  const nav = useNavigate();
  const [query, setQuery] = useState("");
  const [sevFilter, setSevFilter] = useState<string | null>(null);

  const regs = useMemo(() => (report ? regressions(report) : []), [report]);
  const dism = useMemo(() => (report ? dismissed(report) : []), [report]);

  const filtered = useMemo(() => {
    return regs.filter((f) => (sevFilter ? f.severity === sevFilter : true)).filter((f) => {
      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      const hay = [f.plain_summary, f.tenant, ...Object.values(f.cohort)].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [regs, sevFilter, query]);

  if (!report) return null;

  const pending = needsDecisionCount(report);
  const verified = report.verifications.filter((v) => v.verdict === "improved").length;

  return (
    <div className="page-container page-container-wide">
      <div className="page-header">
        <h1>Incidents</h1>
        <p>
          {pending > 0 ? (
            <><span className="eyebrow-accent" style={{ fontWeight: 700 }}>Needs attention.</span> Everything on this page is computed from the report.</>
          ) : (
            <><span className="eyebrow-ok" style={{ fontWeight: 700 }}>All clear.</span> Nothing awaiting your call right now.</>
          )}
        </p>
      </div>

      {pending > 0 && <KpiHero pending={pending} />}

      <p className="kpi-context">
        <strong>{regs.length}</strong> found
        <span className="sep">&middot;</span>
        <strong>{dism.length}</strong> cleared
        {verified > 0 && (
          <>
            <span className="sep">&middot;</span>
            <strong>{verified}</strong> verified
          </>
        )}
        <span className="sep">&middot;</span>
        <strong>{report.gaps.length}</strong> refused
      </p>

      <div className="filter-bar">
        <div className="search-input-wrap">
          <SearchIcon />
          <input
            className="search-input"
            placeholder="Search incident, tenant or intent&hellip;"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="seg-pills">
          <button className={`seg-pill${sevFilter === null ? " active" : ""}`} onClick={() => setSevFilter(null)}>
            All ({regs.length})
          </button>
          {SEVERITIES.map((s) => (
            <button
              key={s}
              className={`seg-pill${sevFilter === s ? " active" : ""}`}
              onClick={() => setSevFilter(sevFilter === s ? null : s)}
            >
              {s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <IncidentsTable findings={filtered} report={report} />

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
    </div>
  );
}
