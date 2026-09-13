// Thin fetch wrappers over the backend API. Same origin in production (served
// from /app); proxied to :8801 in dev (see vite.config.ts).
import type { Approval, ChatResponse, Report, Verdict } from "./types";

const BASE = "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export function getReport(): Promise<Report> {
  return json<Report>("/report");
}

export function postChat(question: string): Promise<ChatResponse> {
  return json<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export function getChatSuggestions(): Promise<string[]> {
  return json<string[]>("/chat/suggestions");
}

export function postApproval(
  prescriptionId: string,
  verdict: Verdict,
  reason: string,
): Promise<{ prescription_id: string; approval: Approval }> {
  return json("/approvals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prescription_id: prescriptionId, verdict, reason }),
  });
}
