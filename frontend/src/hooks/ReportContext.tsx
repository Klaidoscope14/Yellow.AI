// Loads the report once and shares it. applyApproval mutates the matching
// prescription in place (the backend has already persisted it) so every screen
// reflects a decision immediately without a refetch.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getReport } from "../api/client";
import type { Approval, Report } from "../api/types";

interface ReportState {
  report: Report | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  applyApproval: (prescriptionId: string, approval: Approval | null) => void;
}

const Ctx = createContext<ReportState | undefined>(undefined);

export function ReportProvider({ children }: { children: ReactNode }) {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    getReport()
      .then((r) => setReport(r))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  const applyApproval = useCallback((prescriptionId: string, approval: Approval | null) => {
    setReport((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        prescriptions: prev.prescriptions.map((p) =>
          p.id === prescriptionId ? { ...p, approval } : p,
        ),
      };
    });
  }, []);

  return (
    <Ctx.Provider value={{ report, loading, error, reload, applyApproval }}>
      {children}
    </Ctx.Provider>
  );
}

export function useReport(): ReportState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useReport must be used within ReportProvider");
  return v;
}
