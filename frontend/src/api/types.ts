// TypeScript models for loop-report.json (the one deliverable) plus the
// product-specific fields the backend adds (plain_summary) and the chat API.

export type Verdict = "accepted" | "rejected" | "deferred";
export type Severity = "low" | "medium" | "high" | "critical";
export type Audience = "agent_builder" | "business_owner" | "platform_owner";

export interface Coverage {
  value: number;
  basis: string;
  excluded?: string[];
}

export interface Calibration {
  agreement: number;
  n: number;
  judge_version?: string;
}

export interface Metric {
  id: string;
  name?: string;
  ask_id: string;
  grain?: string;
  fidelity: "measured" | "judged" | "derived";
  coverage: Coverage;
  calibration: Calibration | null;
  plan: Record<string, unknown>;
}

export interface Window {
  from_day: number;
  to_day: number;
}

export interface Downstream {
  would_have_resolved_at_baseline?: number;
  deficit?: number;
  silent_empty_responses?: number;
  extra_turns_total?: number;
  extra_cost_usd?: number;
  [k: string]: number | undefined;
}

export interface Impact {
  conversations_affected: number;
  share_of_traffic: number;
  days_running: number;
  derivation: string;
  cost_usd?: number | null;
  downstream?: Downstream;
}

export interface Finding {
  id: string;
  tenant: string;
  cohort: Record<string, string>;
  metric: string;
  window: Window;
  is_regression: boolean;
  severity: Severity;
  evidence: string[];
  plain_summary: string;
  observed?: number;
  expected?: number;
  impact?: Impact;
  audience?: Audience[];
  if_nothing_changes?: string;
  not_a_regression_because?: string;
}

export interface AttributedChange {
  kind: string;
  day: number;
}

export interface Diagnosis {
  id: string;
  finding_id: string;
  cause_class: string;
  confidence: number;
  attributed_change: AttributedChange | null;
  evidence: string[];
}

export interface Decision {
  asking_approval_for: string;
  risk_if_diagnosis_wrong: string;
  would_not_ship_if: string;
}

export interface Approval {
  verdict: Verdict;
  decided_by: string;
  reason: string;
  at: string;
}

export interface PredictedDelta {
  metric: string;
  from: number;
  to: number;
}

export interface Prescription {
  id: string;
  diagnosis_id: string;
  change_type: string;
  target: string;
  description: string;
  autonomy_rung?: string;
  predicted_delta: PredictedDelta;
  decision: Decision;
  approval?: Approval | null;
}

export interface Verification {
  prescription_id: string;
  replay_run_id: string;
  metric: string;
  before: number;
  after: number;
  golden_set_pass: boolean | null;
  verdict: "improved" | "no_effect" | "regressed";
  prediction_error?: number | null;
}

export interface RequiredEvent {
  name: string;
  grain: string;
  fields: string[];
  owner: string;
}

export interface Gap {
  ask_id: string;
  verdict: "NOT_MEASURABLE" | "REQUIRES_NEW_JUDGE" | "COVERAGE_TOO_LOW" | "CARDINALITY_REFUSED";
  why: string;
  nearest_proxy?: string;
  why_the_proxy_misleads?: string;
  required_event?: RequiredEvent;
}

export interface Standard {
  tenant: string;
  cohort: Record<string, string>;
  metric: string;
  best: number;
  median: number;
  deficit?: number;
  exemplar_n?: number;
}

export interface Report {
  team: string;
  corpus: string;
  generated_at: string;
  system_notes: string;
  metrics: Metric[];
  standard: Standard[];
  findings: Finding[];
  diagnoses: Diagnosis[];
  prescriptions: Prescription[];
  verifications: Verification[];
  gaps: Gap[];
  self_assessment: Record<string, unknown>;
}

export type ChatScreen = "finding" | "refusals" | "dismissed";

export interface ChatLink {
  screen: ChatScreen;
  id?: string;
}

export interface ChatResponse {
  answer: string;
  based_on: string[];
  link: ChatLink | null;
  refusal: boolean;
  intent: string;
}
