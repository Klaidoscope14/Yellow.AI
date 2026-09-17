import { Routes, Route, useLocation } from "react-router-dom";
import { useReport } from "./hooks/ReportContext";
import { ControlCenter } from "./screens/ControlCenter";
import { FindingDetail } from "./screens/FindingDetail";
import { Dismissed } from "./screens/Dismissed";
import { Gaps } from "./screens/Gaps";
import { Decisions } from "./screens/Decisions";
import { TopNav } from "./components/TopNav";
import { CommandPalette } from "./components/CommandPalette";

export function App() {
  const { report, loading, error, booting, bootAttempt, bootMaxAttempts, reload } = useReport();
  const location = useLocation();

  if (booting || (loading && !report && !error)) {
    return (
      <div className="loading loading--boot">
        <div className="spinner" aria-hidden="true" />
        <p>{booting ? "Starting services…" : "Loading report…"}</p>
        {booting && (
          <p className="loading__hint">
            First boot can take up to ~30s (backend is loading data and computing metrics).
            Attempt {bootAttempt}/{bootMaxAttempts}&hellip;
          </p>
        )}
      </div>
    );
  }
  if (error) {
    return (
      <div className="error">
        <p>Failed to load report: {error}</p>
        <button type="button" onClick={reload}>
          Retry
        </button>
      </div>
    );
  }
  if (!report) return null;

  return (
    <div className="app-shell">
      <TopNav />

      <main className="page-enter" key={location.pathname}>
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/finding/:id" element={<FindingDetail />} />
          <Route path="/dismissed" element={<Dismissed />} />
          <Route path="/gaps" element={<Gaps />} />
          <Route path="/decisions" element={<Decisions />} />
        </Routes>
      </main>

      <CommandPalette />
    </div>
  );
}
