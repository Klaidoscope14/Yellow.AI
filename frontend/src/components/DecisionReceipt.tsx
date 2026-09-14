import type { Approval, Finding, Prescription } from "../api/types";

/** A clean, printable record of one decision — headline, fix, verdict,
 * reason, timestamp. Experiment #4. Print via window.print(); @media print
 * in global.css hides everything else on the page. */
export function DecisionReceipt({
  finding,
  prescription,
  approval,
  onClose,
}: {
  finding: Finding;
  prescription: Prescription;
  approval: Approval;
  onClose: () => void;
}) {
  return (
    <>
      <div className="receipt-scrim no-print" onClick={onClose} />
      <div className="receipt-panel" role="dialog" aria-label="Decision receipt">
        <div className="receipt-header no-print">
          <span>Decision receipt</span>
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            <button className="linkbtn" onClick={() => window.print()}>
              Print
            </button>
            <button className="chat-close" onClick={onClose}>
              &times;
            </button>
          </div>
        </div>

        <div className="receipt-body">
          <p className="receipt-eyebrow">Nexus Loop &middot; Decision Record</p>
          <h2 className="receipt-title">{finding.plain_summary}</h2>
          <p className="breadcrumb">
            {finding.tenant}
            <span className="sep">&middot;</span>
            {Object.values(finding.cohort).join(" / ")}
            <span className="sep">&middot;</span>
            Day {finding.window.from_day}&ndash;{finding.window.to_day}
          </p>

          <div className="receipt-row">
            <span className="receipt-label">Fix</span>
            <span>
              {prescription.change_type} &rarr; {prescription.target}
            </span>
          </div>
          <div className="receipt-row">
            <span className="receipt-label">Verdict</span>
            <span
              style={{
                fontWeight: 700,
                color: approval.verdict === "accepted" ? "var(--status-ok-ink)" : "var(--status-rej-ink)",
              }}
            >
              {approval.verdict.toUpperCase()}
            </span>
          </div>
          <div className="receipt-row">
            <span className="receipt-label">Decided by</span>
            <span>{approval.decided_by}</span>
          </div>
          <div className="receipt-row">
            <span className="receipt-label">Date</span>
            <span>{new Date(approval.at).toLocaleString()}</span>
          </div>
          <div className="receipt-row">
            <span className="receipt-label">Reason</span>
            <span>&ldquo;{approval.reason}&rdquo;</span>
          </div>

          <hr className="divider" />
          <p className="receipt-sig">
            Recorded automatically by Nexus Loop at the moment of decision. This receipt is a read-only
            summary of that record.
          </p>
        </div>
      </div>
    </>
  );
}
