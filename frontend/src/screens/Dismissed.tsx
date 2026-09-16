import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useReport } from "../hooks/ReportContext";
import { dismissed } from "../lib/report";
import { pct } from "../lib/format";
import { ChevronRightIcon, Icon } from "../components/Icon";
import type { Finding } from "../api/types";

// Same stagger/spring the issues table uses, for visual parity.
const tbodyVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const rowVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 100, damping: 14 },
  },
} as const;

function LookalikeDrawer({ finding, onClose }: { finding: Finding; onClose: () => void }) {
  return (
    <>
      <motion.div
        className="lookalike-drawer-scrim"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18 }}
      />
      <motion.aside
        className="lookalike-drawer"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 34 }}
        aria-label="Lookalike details"
      >
        <div className="lookalike-drawer-header">
          <span className="lookalike-drawer-eyebrow">Cleared &middot; not a regression</span>
          <button className="lookalike-drawer-close" onClick={onClose} aria-label="Close">
            <Icon size={16} strokeWidth={2}>
              <path d="M6 6l12 12M18 6L6 18" />
            </Icon>
          </button>
        </div>

        <div className="lookalike-drawer-body">
          <h2 className="lookalike-drawer-title">{finding.plain_summary}</h2>
          <p className="lookalike-drawer-meta">
            {finding.tenant} &middot; day {finding.window.from_day}&ndash;{finding.window.to_day}
          </p>

          {finding.not_a_regression_because && (
            <section className="lookalike-drawer-section">
              <h3>Why not a regression</h3>
              <p>{finding.not_a_regression_because}</p>
            </section>
          )}

          {finding.observed != null && finding.expected != null && (
            <section className="lookalike-drawer-section">
              <h3>{finding.metric}</h3>
              <p>{pct(finding.expected)} &rarr; {pct(finding.observed)}</p>
            </section>
          )}

          {finding.evidence.length > 0 && (
            <section className="lookalike-drawer-section">
              <h3>Evidence</h3>
              <ul>
                {finding.evidence.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </section>
          )}
        </div>
      </motion.aside>
    </>
  );
}

export function Dismissed() {
  const { report } = useReport();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (!report) return null;

  const items = dismissed(report);
  const selected = items.find((f) => f.id === selectedId) ?? null;

  return (
    <div className="page-container page-container-wide">
      <div className="page-header">
        <h1>Lookalikes</h1>
        <p>
          {items.length} pattern{items.length !== 1 ? "s" : ""} looked like regressions and weren&rsquo;t.
          Here&rsquo;s why each one was cleared.
        </p>
      </div>

      {items.length > 0 ? (
        <div className="issues-table-wrap">
          <div className="issues-table-scroll">
            <table className="issues-table">
              <colgroup>
                <col style={{ width: "auto" }} />
                <col style={{ width: 220 }} />
                <col style={{ width: 36 }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Issues</th>
                  <th>Tenant &middot; Intent</th>
                  <th aria-hidden />
                </tr>
              </thead>
              <motion.tbody variants={tbodyVariants} initial="hidden" animate="visible">
                {items.map((f) => (
                  <motion.tr
                    key={f.id}
                    variants={rowVariants}
                    className={selectedId === f.id ? "lookalike-row--selected" : ""}
                    onClick={() => setSelectedId(f.id)}
                  >
                    <td className="title-cell">{f.plain_summary}</td>
                    <td className="muted">
                      {f.tenant} &middot; day {f.window.from_day}&ndash;{f.window.to_day}
                    </td>
                    <td className="chevron-cell"><ChevronRightIcon size={15} /></td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="muted" style={{ padding: 40, textAlign: "center" }}>
          No patterns were examined and dismissed.
        </p>
      )}

      <AnimatePresence>
        {selected && <LookalikeDrawer finding={selected} onClose={() => setSelectedId(null)} />}
      </AnimatePresence>
    </div>
  );
}
