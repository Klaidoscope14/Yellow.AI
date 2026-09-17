import { useState } from "react";
import { postApproval } from "../api/client";
import { useReport } from "../hooks/ReportContext";
import type { Prescription } from "../api/types";

export function DecisionGate({ prescription }: { prescription: Prescription }) {
  const { applyApproval } = useReport();
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const existing = prescription.approval;

  async function submit(verdict: "accepted" | "rejected") {
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
    <div className="decision">
      <textarea
        placeholder="Reason for your decision (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="btns">
        <button
          className="btn reject"
          disabled={!reason.trim() || submitting}
          onClick={() => submit("rejected")}
        >
          Reject
        </button>
        <button
          className="btn approve"
          disabled={!reason.trim() || submitting}
          onClick={() => submit("accepted")}
        >
          Approve Fix
        </button>
      </div>
    </div>
  );
}
