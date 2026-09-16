import { useEffect } from "react";
import { FindingDetailBody } from "./FindingDetailBody";
import type { Finding, Report } from "../api/types";

export function FindingSidePanel({
  report,
  finding,
  onClose,
}: {
  report: Report;
  finding: Finding | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!finding) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finding, onClose]);

  if (!finding) return null;

  return (
    <>
      <div className="side-panel-scrim" onClick={onClose} />
      <aside className="side-panel finding-side-panel">
        <button className="side-panel-close" onClick={onClose} aria-label="Close">&times;</button>
        <div className="side-panel-body finding-page">
          <FindingDetailBody report={report} finding={finding} showDiagnosis={false} />
        </div>
      </aside>
    </>
  );
}
