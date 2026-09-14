import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { regressions, dismissed, diagnosisFor, statusOf, needsDecisionCount } from "../lib/report";
import { pct, int } from "../lib/format";
import { ROLE_LABEL } from "../lib/asks";
import { SearchIcon, ChevronRightIcon } from "../components/Icon";
import { useCountUp } from "../hooks/useCountUp";
import type { Audience, Finding, Report } from "../api/types";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

function KpiTile({ n, label, tone }: { n: number; label: string; tone: "purple" | "green" | "amber" | "blue" }) {
  const shown = useCountUp(n);
  return (
    <div className={`kpi-tile ${tone}`}>
      <div className="n">{shown}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function FindingCard({
  finding,
  report,
  selected,
  kbdFocused,
  cardRef,
}: {
  finding: Finding;
  report: Report;
  selected: boolean;
  kbdFocused?: boolean;
  cardRef?: (el: HTMLButtonElement | null) => void;
}) {
  const nav = useNavigate();
  const status = statusOf(report, finding);
  const diagnosis = diagnosisFor(report, finding);
  const team = (finding.audience ?? []).map((a) => ROLE_LABEL[a as Audience] ?? a).join(", ");

  return (
    <button
      ref={cardRef}
      className={`card${selected ? " selected" : ""}${kbdFocused ? " kbd-focused" : ""}`}
      onClick={() => nav(`/finding/${finding.id}`)}
    >
      <span className={`corner-flag ${finding.severity}`}>
        <span className="corner-flag-letter">{finding.severity[0].toUpperCase()}</span>
      </span>
      <p className="claim">{finding.plain_summary}</p>
      <p className="card-meta-line">
        {finding.tenant} &middot; {Object.values(finding.cohort).join(" / ")}
      </p>
      {team && (
        <p className="card-team-line">
          Assigned team: <strong>{team}</strong>
        </p>
      )}
      <div className="card-bottom-row">
        <span className={`sev-label ${finding.severity}`}>{finding.severity}</span>
        <span className={`pill ${status.cls}`}>{status.label}</span>
        <div className="card-stats">
          {diagnosis && (
            <div className="card-stat">
              <span className="v">{pct(diagnosis.confidence)}</span>
              <span className="l">Confidence</span>
            </div>
          )}
          {finding.impact && (
            <div className="card-stat">
              <span className="v">{int(finding.impact.conversations_affected)}</span>
              <span className="l">Impact</span>
            </div>
          )}
          {finding.impact && (
            <div className="card-stat">
              <span className="v">{finding.impact.days_running}d</span>
              <span className="l">Running</span>
            </div>
          )}
        </div>
        <span className="card-chevron"><ChevronRightIcon /></span>
      </div>
    </button>
  );
}

export function ControlCenter({ selectedId = null }: { selectedId?: string | null }) {
  const { report } = useReport();
  const nav = useNavigate();
  const [query, setQuery] = useState("");
  const [sevFilter, setSevFilter] = useState<string | null>(null);

  const regs = useMemo(() => (report ? regressions(report) : []), [report]);
  const dism = useMemo(() => (report ? dismissed(report) : []), [report]);

  const filtered = useMemo(() => {
    return regs
      .filter((f) => (sevFilter ? f.severity === sevFilter : true))
      .filter((f) => {
        if (!query.trim()) return true;
        const q = query.trim().toLowerCase();
        const hay = [f.plain_summary, f.tenant, ...Object.values(f.cohort)].join(" ").toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => severityRank(b.severity) - severityRank(a.severity));
  }, [regs, sevFilter, query]);

  // Keyboard navigation: j/k (or arrows) move focus through the visible
  // list, Enter opens it. Ignored while typing in an input/textarea.
  const [focusIdx, setFocusIdx] = useState(0);
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    setFocusIdx(0);
  }, [query, sevFilter]);

  // Keep the keyboard cursor pointed at whatever is actually open — a
  // mouse click (or a chat/command-palette jump) shouldn't leave a stale
  // dashed ring sitting on a different card than the one that's selected.
  useEffect(() => {
    if (!selectedId) return;
    const idx = filtered.findIndex((f) => f.id === selectedId);
    if (idx >= 0) setFocusIdx(idx);
  }, [selectedId, filtered]);

  useEffect(() => {
    cardRefs.current[focusIdx]?.scrollIntoView({ block: "nearest" });
  }, [focusIdx]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j" || e.key === "ArrowDown") {
        if (filtered.length === 0) return;
        e.preventDefault();
        setFocusIdx((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        if (filtered.length === 0) return;
        e.preventDefault();
        setFocusIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter" && filtered[focusIdx]) {
        nav(`/finding/${filtered[focusIdx].id}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, focusIdx, nav]);

  if (!report) return null;

  const pending = needsDecisionCount(report);
  const verified = report.verifications.filter((v) => v.verdict === "improved").length;

  return (
    <>
      <div className="hero-card">
        <h1>
          Agent reliability: <span className="em">{pending > 0 ? "Needs attention" : "All clear"}</span>
        </h1>
        <p>Every number below traces back to this report &mdash; nothing here is invented.</p>
      </div>

      <div className="kpi-grid">
        <KpiTile n={regs.length} label="Regressions found" tone="purple" />
        <KpiTile n={dism.length} label="Lookalikes dismissed" tone="green" />
        <KpiTile n={pending} label="Awaiting decision" tone="amber" />
        <KpiTile
          n={verified > 0 ? verified : report.gaps.length}
          label={verified > 0 ? "Fixes verified" : "Measurement gaps"}
          tone="blue"
        />
      </div>

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

      <section>
        {filtered.map((f, i) => (
          <FindingCard
            key={f.id}
            finding={f}
            report={report}
            selected={f.id === selectedId}
            kbdFocused={i === focusIdx}
            cardRef={(el) => (cardRefs.current[i] = el)}
          />
        ))}
        {filtered.length === 0 && (
          <p className="muted small" style={{ padding: "20px 4px" }}>
            No incidents match this search.
          </p>
        )}
      </section>

      <div className="shortcut-hint">
        <span><kbd>j</kbd><kbd>k</kbd> navigate</span>
        <span><kbd>&#9166;</kbd> open</span>
        <span><kbd>&#8984;K</kbd> search</span>
      </div>

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
