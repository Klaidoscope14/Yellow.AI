// Loads the report once and shares it. applyApproval mutates the matching
// prescription in place (the backend has already persisted it) so every screen
// reflects a decision immediately without a refetch.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getReport } from "../api/client";
import type { Approval, Report } from "../api/types";

// On a fresh `run_all.py` start, the backend takes ~20-30s to import DuckDB
// and compute the first metrics pass. Rather than flashing a hard error the
// moment the very first request fails, we quietly retry for a while and only
// surface an error once we're confident the backend isn't just still booting.
const BOOT_RETRY_INTERVAL_MS = 2000;
const BOOT_RETRY_MAX_ATTEMPTS = 20; // ~40s of retrying

interface ReportState {
  report: Report | null;
  loading: boolean;
  error: string | null;
  booting: boolean;
  bootAttempt: number;
  bootMaxAttempts: number;
  reload: () => void;
  applyApproval: (prescriptionId: string, approval: Approval | null) => void;
}

const Ctx = createContext<ReportState | undefined>(undefined);

export function ReportProvider({ children }: { children: ReactNode }) {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(false);
  const [bootAttempt, setBootAttempt] = useState(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearRetryTimer = () => {
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const attempt = useCallback((attemptNumber: number) => {
    setLoading(true);
    getReport()
      .then((r) => {
        setReport(r);
        setError(null);
        setBooting(false);
        setBootAttempt(0);
      })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : String(e);
        if (attemptNumber < BOOT_RETRY_MAX_ATTEMPTS) {
          // Still likely booting (services starting up / port cleanup in
          // progress) — keep the spinner up and retry quietly.
          setBooting(true);
          setBootAttempt(attemptNumber);
          setError(null);
          retryTimer.current = setTimeout(() => attempt(attemptNumber + 1), BOOT_RETRY_INTERVAL_MS);
        } else {
          setBooting(false);
          setError(message);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const reload = useCallback(() => {
    clearRetryTimer();
    setError(null);
    setBootAttempt(0);
    attempt(1);
  }, [attempt]);

  useEffect(() => {
    reload();
    return clearRetryTimer;
  }, [reload]);

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
    <Ctx.Provider
      value={{
        report,
        loading,
        error,
        booting,
        bootAttempt,
        bootMaxAttempts: BOOT_RETRY_MAX_ATTEMPTS,
        reload,
        applyApproval,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useReport(): ReportState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useReport must be used within ReportProvider");
  return v;
}
