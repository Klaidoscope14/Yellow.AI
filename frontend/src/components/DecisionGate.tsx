import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, XCircle } from "lucide-react";
import { postApproval } from "../api/client";
import { useReport } from "../hooks/ReportContext";
import type { Prescription } from "../api/types";

type Verdict = "accepted" | "rejected";

export function DecisionGate({ prescription }: { prescription: Prescription }) {
  const { applyApproval } = useReport();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const existing = prescription.approval;

  function close() {
    setVerdict(null);
    setReason("");
  }

  useEffect(() => {
    if (!verdict) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [verdict]);

  async function submit() {
    if (!verdict) return;
    setSubmitting(true);
    try {
      const res = await postApproval(prescription.id, verdict, reason);
      applyApproval(prescription.id, res.approval);
    } finally {
      setSubmitting(false);
    }
  }

  if (existing) {
    const cls = existing.verdict === "accepted" ? "approved" : "rejected";
    return (
      <div className={`decided ${cls}`}>
        <strong>{existing.verdict === "accepted" ? "Approved" : "Rejected"}</strong>
        {" · "}
        {existing.decided_by} &middot; {existing.reason}
        <span className="again">
          <button onClick={() => applyApproval(prescription.id, null)}>Change decision</button>
        </span>
      </div>
    );
  }

  return (
    <>
      <div className="decision-choices">
        <button
          type="button"
          className="decision-glass-btn decision-glass-btn--reject"
          onClick={() => setVerdict("rejected")}
        >
          <XCircle size={16} strokeWidth={2.4} />
          Reject
        </button>
        <button
          type="button"
          className="decision-glass-btn decision-glass-btn--approve"
          onClick={() => setVerdict("accepted")}
        >
          <CheckCircle2 size={16} strokeWidth={2.4} />
          Approve
        </button>
      </div>

      <AnimatePresence>
        {verdict && (
          <>
            <motion.div
              className="decision-modal-scrim"
              onClick={close}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            />
            <motion.div
              className={`decision-modal decision-modal--${verdict === "accepted" ? "approve" : "reject"}`}
              role="dialog"
              aria-label={verdict === "accepted" ? "Approve fix" : "Reject fix"}
              initial={{ opacity: 0, scale: 0.94, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 8 }}
              transition={{ type: "spring", stiffness: 380, damping: 32 }}
            >
              <h3 className="decision-modal-title">
                {verdict === "accepted" ? (
                  <><CheckCircle2 size={18} strokeWidth={2.4} /> Approve fix</>
                ) : (
                  <><XCircle size={18} strokeWidth={2.4} /> Reject fix</>
                )}
              </h3>
              <textarea
                autoFocus
                placeholder={
                  verdict === "accepted"
                    ? "Why are you approving this? (required)"
                    : "Why are you rejecting this? (required)"
                }
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <div className="decision-modal-btns">
                <button className="btn-confirm cancel" onClick={close}>
                  Cancel
                </button>
                <button
                  className={`btn-confirm ${verdict === "accepted" ? "approve" : "reject"}`}
                  disabled={!reason.trim() || submitting}
                  onClick={submit}
                >
                  {verdict === "accepted" ? "Confirm approval" : "Confirm rejection"}
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
