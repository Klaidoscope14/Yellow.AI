import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { regressions } from "../lib/report";
import { SearchIcon } from "./Icon";

interface CmdItem {
  label: string;
  sub?: string;
  action: () => void;
}

/** Global ⌘K / Ctrl+K jump palette — fuzzy-free substring match over
 * incidents and the four screens. Experiment #1. */
export function CommandPalette() {
  const { report } = useReport();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isMeta = e.metaKey || e.ctrlKey;
      if (isMeta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setActiveIdx(0);
    }
  }, [open]);

  const regs = useMemo(() => (report ? regressions(report) : []), [report]);

  const items = useMemo<CmdItem[]>(() => {
    const staticItems: CmdItem[] = [
      { label: "Go to Incidents", action: () => nav("/") },
      { label: "Go to Lookalikes", action: () => nav("/dismissed") },
      { label: "Go to Diagnostics", action: () => nav("/gaps") },
      { label: "Go to Decisions", action: () => nav("/decisions") },
    ];
    const findingItems: CmdItem[] = regs.map((f) => ({
      label: f.plain_summary,
      sub: `${f.tenant} · ${Object.values(f.cohort).join(" / ")}`,
      action: () => nav(`/finding/${f.id}`),
    }));
    const all = [...staticItems, ...findingItems];
    if (!q.trim()) return all;
    const query = q.trim().toLowerCase();
    return all.filter(
      (i) => i.label.toLowerCase().includes(query) || (i.sub ?? "").toLowerCase().includes(query),
    );
  }, [q, regs, nav]);

  useEffect(() => {
    setActiveIdx(0);
  }, [q]);

  function go(item: CmdItem) {
    item.action();
    setOpen(false);
  }

  if (!open) return null;

  return (
    <>
      <div className="cmdk-scrim" onClick={() => setOpen(false)} />
      <div className="cmdk-panel" role="dialog" aria-label="Command palette">
        <div className="cmdk-input-wrap">
          <SearchIcon size={16} />
          <input
            autoFocus
            className="cmdk-input"
            placeholder="Jump to an incident or screen&hellip;"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIdx((i) => Math.min(items.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIdx((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter" && items[activeIdx]) {
                go(items[activeIdx]);
              }
            }}
          />
          <kbd className="cmdk-esc">Esc</kbd>
        </div>
        <div className="cmdk-list">
          {items.length === 0 && <p className="cmdk-empty">No matches.</p>}
          {items.map((item, i) => (
            <button
              key={i}
              className={`cmdk-item${i === activeIdx ? " active" : ""}`}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => go(item)}
            >
              <span className="cmdk-item-label">{item.label}</span>
              {item.sub && <span className="cmdk-item-sub">{item.sub}</span>}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
