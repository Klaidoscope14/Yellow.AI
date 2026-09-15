import { Routes, Route, useLocation } from "react-router-dom";
import { useReport } from "./hooks/ReportContext";
import { needsDecisionCount } from "./lib/report";
import { ControlCenter } from "./screens/ControlCenter";
import { FindingDetail } from "./screens/FindingDetail";
import { Dismissed } from "./screens/Dismissed";
import { Gaps } from "./screens/Gaps";
import { Decisions } from "./screens/Decisions";
import { Chat } from "./components/Chat";
import { TopNav } from "./components/TopNav";
import { CommandPalette } from "./components/CommandPalette";

export function App() {
  const { report, loading, error } = useReport();
  const location = useLocation();

  if (loading) return <div className="loading">Loading report&hellip;</div>;
  if (error) return <div className="error">Failed to load report: {error}</div>;
  if (!report) return null;

  const pending = needsDecisionCount(report);

  return (
    <div className="app-shell">
      <TopNav team={report.team} pending={pending} />

      <main className="page-enter" key={location.pathname}>
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/finding/:id" element={<FindingDetail />} />
          <Route path="/dismissed" element={<Dismissed />} />
          <Route path="/gaps" element={<Gaps />} />
          <Route path="/decisions" element={<Decisions />} />
        </Routes>
      </main>

      <Chat pending={pending} />
      <CommandPalette />
    </div>
  );
}
