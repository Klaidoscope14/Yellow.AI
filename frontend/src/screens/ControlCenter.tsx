import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Search, CircleCheck, ShieldCheck, CircleHelp, AlertTriangle } from "lucide-react";
import { useReport } from "../hooks/ReportContext";
import { regressions, dismissed, needsDecisionCount, statusOf } from "../lib/report";
import { SearchIcon } from "../components/Icon";
import { useCountUp } from "../hooks/useCountUp";
import { IncidentsTable } from "../components/IncidentsTable";
import { SeverityDonut } from "../components/SeverityDonut";
import type { Severity } from "../api/types";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

const statGroupVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const statVariants = {
  hidden: { opacity: 0, y: 10, scale: 0.9 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 320, damping: 20 },
  },
};

/** One outcome row inside the Outcomes card — icon chip + label + number,
 * each in its own semantic tone so the list reads at a glance. */
function OutcomeRow({
  n,
  label,
  icon: Icon,
  tone,
}: {
  n: number;
  label: string;
  icon: typeof Search;
  tone: "neutral" | "ok" | "pending";
}) {
  return (
    <motion.li className={`outcome-row outcome-row--${tone}`} variants={statVariants}>
      <span className="outcome-icon">
        <Icon size={12} strokeWidth={2.4} aria-hidden />
      </span>
      <span className="outcome-label">{label}</span>
      <span className="outcome-n">{n}</span>
    </motion.li>
  );
}

interface CursorRect {
  left: number;
  width: number;
  opacity: number;
}

/** Segmented severity filter — pills stay separate, individually clickable
 * buttons (not one merged bar); a single indicator glides beneath whichever
 * one is active or hovered, tracked via each button's own ref/offsetLeft. */
function SeverityFilter({
  value,
  onChange,
  counts,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  counts: Record<string, number>;
}) {
  const options = [{ key: null, label: `All (${counts.all})` }, ...SEVERITIES.map((s) => ({
    key: s,
    label: `${s[0].toUpperCase()}${s.slice(1)}`,
  }))];
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [cursor, setCursor] = useState<CursorRect>({ left: 0, width: 0, opacity: 0 });
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const activeIdx = options.findIndex((o) => o.key === value);
  const litIdx = hoveredIdx ?? activeIdx;

  const moveTo = (idx: number) => {
    const el = refs.current[idx];
    if (!el) return;
    setCursor({ left: el.offsetLeft, width: el.offsetWidth, opacity: 1 });
  };

  useEffect(() => {
    moveTo(litIdx === -1 ? 0 : litIdx);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [litIdx, counts.all]);

  return (
    <div className="seg-pills" onMouseLeave={() => setHoveredIdx(null)}>
      <motion.span
        className="seg-cursor"
        animate={{ left: cursor.left, width: cursor.width, opacity: cursor.opacity }}
        transition={{ type: "spring", stiffness: 500, damping: 40, mass: 0.6 }}
      />
      {options.map((o, i) => (
        <button
          key={o.key ?? "all"}
          ref={(el) => {
            refs.current[i] = el;
          }}
          className={`seg-pill${litIdx === i ? " active" : ""}`}
          onMouseEnter={() => setHoveredIdx(i)}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// One hero number card. Top band gives it real context (which severities
// make up the pending count) instead of a bare number in an empty box;
// the number itself is vertically centered in the remaining space so it
// uses the card's full height the way its siblings' content does.
function KpiHero({ pending, bySeverity }: { pending: number; bySeverity: Partial<Record<Severity, number>> }) {
  const shown = useCountUp(pending);
  const breakdown = SEVERITIES.filter((s) => bySeverity[s]);
  return (
    <div className="kpi-hero">
      <div className="kpi-hero-top">
        <span className="kpi-hero-icon">
          <AlertTriangle size={15} strokeWidth={2.4} aria-hidden />
        </span>
        {breakdown.length > 0 && (
          <span className="kpi-hero-sevs">
            {breakdown.map((s) => (
              <span key={s} className="kpi-hero-sev">
                <span className={`sev-dot ${s}`} />
                {bySeverity[s]} {s}
              </span>
            ))}
          </span>
        )}
      </div>
      <div className="kpi-hero-main">
        <span className="kpi-hero-n">{shown}</span>
        <span className="kpi-hero-l">{pending === 1 ? "fix awaiting your call" : "fixes awaiting your call"}</span>
      </div>
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
  const sevCounts = useMemo(() => {
    const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const f of regs) counts[f.severity]++;
    return counts;
  }, [regs]);
  const pendingBySeverity = useMemo(() => {
    if (!report) return {};
    const counts: Partial<Record<Severity, number>> = {};
    for (const f of regs) {
      if (statusOf(report, f).cls === "needs") counts[f.severity] = (counts[f.severity] ?? 0) + 1;
    }
    return counts;
  }, [report, regs]);

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
            <><span className="needs-pill">Needs attention</span> Everything on this page is computed from the report.</>
          ) : (
            <><span className="eyebrow-ok" style={{ fontWeight: 700 }}>All clear.</span> Nothing awaiting your call right now.</>
          )}
        </p>
      </div>

      {/* KPI + Outcomes stack in one column; severity sits beside them as
          the other column, stretching to match their combined height. */}
      <div className="incidents-stat-row">
        <div className="incidents-stat-col">
          {pending > 0 && <KpiHero pending={pending} bySeverity={pendingBySeverity} />}

          <div className="outcomes-card">
            <h2>Outcomes</h2>
            <motion.ul
              className="outcome-list"
              variants={statGroupVariants}
              initial="hidden"
              animate="visible"
            >
              <OutcomeRow n={regs.length} label="Found" icon={Search} tone="neutral" />
              <OutcomeRow n={dism.length} label="Cleared" icon={CircleCheck} tone="ok" />
              {verified > 0 && <OutcomeRow n={verified} label="Verified" icon={ShieldCheck} tone="ok" />}
              <OutcomeRow n={report.gaps.length} label="Refused" icon={CircleHelp} tone="pending" />
            </motion.ul>
          </div>
        </div>

        {regs.length > 0 && <SeverityDonut counts={sevCounts} />}
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
        <SeverityFilter
          value={sevFilter}
          onChange={(v) => setSevFilter(v === sevFilter ? null : v)}
          counts={{ all: regs.length }}
        />
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
