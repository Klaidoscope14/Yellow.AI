import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";

/** Collapsible "receipts" card (How we computed this / Evidence chain) —
 * a controlled disclosure instead of native <details>, so the open/close
 * can actually animate instead of snapping instantly. */
export function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className={`finding-card inline-receipts${open ? " inline-receipts--open" : ""}`}>
      <button
        type="button"
        className="inline-receipts-summary"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="inline-receipts-panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            style={{ overflow: "hidden" }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
