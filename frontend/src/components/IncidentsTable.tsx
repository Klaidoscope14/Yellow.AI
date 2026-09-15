import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { diagnosisFor, statusOf } from "../lib/report";
import { pct, int } from "../lib/format";
import { useResizableColumns } from "../hooks/useResizableColumns";
import { ChevronRightIcon } from "./Icon";
import type { Finding, Report } from "../api/types";

type SortKey = "severity" | "title" | "context" | "status" | "confidence" | "impact" | "running";
type SortDir = "asc" | "desc";

interface ColumnDef {
  key: SortKey;
  label: string;
  width: number;
  sortable: boolean;
  align?: "right";
}

// Column widths tuned for a ~1136px content column at the default page
// container: total sits well inside that width so nothing is cut off.
// (Title stays generous with wrap; numeric columns tight; severity/status
// stateful pills sized to their content.)
const COLUMNS: ColumnDef[] = [
  { key: "severity", label: "Severity", width: 96, sortable: true },
  { key: "title", label: "Incident", width: 340, sortable: false },
  { key: "context", label: "Tenant · Intent", width: 190, sortable: true },
  { key: "status", label: "Status", width: 122, sortable: true },
  { key: "confidence", label: "Confidence", width: 100, sortable: true, align: "right" },
  { key: "impact", label: "Impact", width: 88, sortable: true, align: "right" },
  { key: "running", label: "Running", width: 88, sortable: true, align: "right" },
];

const SEVERITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

interface Row {
  finding: Finding;
  context: string;
  statusLabel: string;
  statusCls: string;
  confidence: number | null;
  impact: number | null;
  running: number | null;
}

function buildRows(findings: Finding[], report: Report): Row[] {
  return findings.map((f) => {
    const status = statusOf(report, f);
    const diagnosis = diagnosisFor(report, f);
    return {
      finding: f,
      context: `${f.tenant} · ${Object.values(f.cohort).join(" / ")}`,
      statusLabel: status.label,
      statusCls: status.cls,
      confidence: diagnosis ? diagnosis.confidence : null,
      impact: f.impact ? f.impact.conversations_affected : null,
      running: f.impact ? f.impact.days_running : null,
    };
  });
}

function sortRows(rows: Row[], key: SortKey, dir: SortDir): Row[] {
  const mul = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    switch (key) {
      case "severity":
        return (SEVERITY_RANK[a.finding.severity] - SEVERITY_RANK[b.finding.severity]) * mul;
      case "context":
        return a.context.localeCompare(b.context) * mul;
      case "status":
        return a.statusLabel.localeCompare(b.statusLabel) * mul;
      case "confidence":
        return ((a.confidence ?? -1) - (b.confidence ?? -1)) * mul;
      case "impact":
        return ((a.impact ?? -1) - (b.impact ?? -1)) * mul;
      case "running":
        return ((a.running ?? -1) - (b.running ?? -1)) * mul;
      default:
        return 0;
    }
  });
}

export function IncidentsTable({ findings, report }: { findings: Finding[]; report: Report }) {
  const nav = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const { widths, startResize } = useResizableColumns(
    Object.fromEntries(COLUMNS.map((c) => [c.key, c.width])),
  );

  const rows = useMemo(() => buildRows(findings, report), [findings, report]);
  const sorted = useMemo(() => sortRows(rows, sortKey, sortDir), [rows, sortKey, sortDir]);

  const [focusIdx, setFocusIdx] = useState(0);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => setFocusIdx(0), [findings]);
  useEffect(() => {
    rowRefs.current[focusIdx]?.scrollIntoView({ block: "nearest" });
  }, [focusIdx]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j" || e.key === "ArrowDown") {
        if (sorted.length === 0) return;
        e.preventDefault();
        setFocusIdx((i) => Math.min(sorted.length - 1, i + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        if (sorted.length === 0) return;
        e.preventDefault();
        setFocusIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter" && sorted[focusIdx]) {
        nav(`/finding/${sorted[focusIdx].finding.id}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sorted, focusIdx, nav]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (findings.length === 0) {
    return (
      <p className="muted small" style={{ padding: "24px 4px" }}>
        No incidents match this search.
      </p>
    );
  }

  return (
    <div className="incidents-table-wrap">
      <div className="incidents-table-scroll">
        <table className="incidents-table">
          <colgroup>
            {COLUMNS.map((c) => (
              <col key={c.key} style={{ width: widths[c.key] }} />
            ))}
            <col style={{ width: 36 }} />
          </colgroup>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={c.align === "right" ? "num" : undefined}
                  onClick={() => c.sortable && toggleSort(c.key)}
                  style={{ cursor: c.sortable ? "pointer" : "default" }}
                >
                  <span className="th-label">
                    {c.label}
                    {c.sortable && sortKey === c.key && (
                      <span className="th-sort-arrow">{sortDir === "asc" ? "↑" : "↓"}</span>
                    )}
                  </span>
                  <span className="col-resize-handle" onMouseDown={(e) => startResize(e, c.key)} />
                </th>
              ))}
              <th aria-hidden />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.finding.id}
                ref={(el) => (rowRefs.current[i] = el)}
                className={i === focusIdx ? "kbd-focused" : ""}
                onClick={() => nav(`/finding/${row.finding.id}`)}
              >
                <td>
                  <span className={`sev-dot ${row.finding.severity}`} />
                  <span className={`sev-label ${row.finding.severity}`}>{row.finding.severity}</span>
                </td>
                <td className="title-cell">{row.finding.plain_summary}</td>
                <td className="muted">{row.context}</td>
                <td>
                  <span className={`pill ${row.statusCls}`}>{row.statusLabel}</span>
                </td>
                <td className="num">{row.confidence != null ? pct(row.confidence) : "—"}</td>
                <td className="num">{row.impact != null ? int(row.impact) : "—"}</td>
                <td className="num">{row.running != null ? `${row.running}d` : "—"}</td>
                <td className="chevron-cell"><ChevronRightIcon size={15} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
