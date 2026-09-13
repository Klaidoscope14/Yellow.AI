// Pure selectors over a Report. Keeping these out of components makes the
// screens thin and the relationships (finding -> diagnosis -> prescription ->
// verification) testable in one place.
import type { Diagnosis, Finding, Prescription, Report, Verification } from "../api/types";

export const regressions = (r: Report): Finding[] => r.findings.filter((f) => f.is_regression);
export const dismissed = (r: Report): Finding[] => r.findings.filter((f) => !f.is_regression);

export const diagnosisFor = (r: Report, f: Finding): Diagnosis | undefined =>
  r.diagnoses.find((d) => d.finding_id === f.id);

export const prescriptionFor = (r: Report, f: Finding): Prescription | undefined => {
  const diag = diagnosisFor(r, f);
  if (!diag) return undefined;
  return r.prescriptions.find((p) => p.diagnosis_id === diag.id);
};

export const verificationFor = (r: Report, rx: Prescription): Verification | undefined =>
  r.verifications.find((v) => v.prescription_id === rx.id);

export interface Status {
  label: string;
  cls: "approved" | "rejected" | "needs";
}

export function statusOf(r: Report, f: Finding): Status {
  const rx = prescriptionFor(r, f);
  const verdict = rx?.approval?.verdict;
  if (verdict === "accepted") return { label: "Approved", cls: "approved" };
  if (verdict === "rejected") return { label: "Rejected", cls: "rejected" };
  return { label: "Needs decision", cls: "needs" };
}

export const needsDecisionCount = (r: Report): number =>
  regressions(r).filter((f) => statusOf(r, f).cls === "needs").length;

const CAUSE_PLAIN: Record<string, string> = {
  "kb.gap":
    "The knowledge base has no confident answer for these questions, so the assistant falls back to a generic reply and the conversation doesn’t resolve.",
  "tool.contract_break":
    "A tool is returning an empty result while reporting success, so the assistant has nothing to answer with and the user isn’t helped.",
  "prompt.regression":
    "A prompt change made the assistant over-confirm and re-ask, adding turns and cost without improving whether it resolves.",
};

export const plainCause = (cause: string | undefined): string =>
  (cause && CAUSE_PLAIN[cause]) || "See the evidence below for how this was determined.";
