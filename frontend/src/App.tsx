import { Routes, Route, NavLink, useLocation } from "react-router-dom";
import { useReport } from "./hooks/ReportContext";
import { needsDecisionCount } from "./lib/report";
import { ControlCenter } from "./screens/ControlCenter";
import { FindingDetail } from "./screens/FindingDetail";
import { Dismissed } from "./screens/Dismissed";
import { Gaps } from "./screens/Gaps";
import { Decisions } from "./screens/Decisions";
import { Chat } from "./components/Chat";

export function App() {
  const { report, loading, error } = useReport();
  const location = useLocation();

  if (loading) return <div className="loading">Loading report&hellip;</div>;
  if (error) return <div className="error">Failed to load report: {error}</div>;
  if (!report) return null;

  const pending = needsDecisionCount(report);

  return (
    <>
      <header className="topbar">
        <div className="wrap" style={{ justifyContent: "space-between" }}>
          <span className="brand">NEXUS LOOP</span>
          <nav style={{ display: "flex", gap: 18, fontSize: 14 }}>
            <NavLink to="/" end className={({ isActive }) => (isActive ? "linkbtn" : "linkbtn muted")}>
              Control Center
            </NavLink>
            <NavLink to="/dismissed" className={({ isActive }) => (isActive ? "linkbtn" : "linkbtn muted")}>
              Dismissed
            </NavLink>
            <NavLink to="/gaps" className={({ isActive }) => (isActive ? "linkbtn" : "linkbtn muted")}>
              Gaps
            </NavLink>
            <NavLink to="/decisions" className={({ isActive }) => (isActive ? "linkbtn" : "linkbtn muted")}>
              Decisions
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="wrap">
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/finding/:id" element={<FindingDetail />} />
          <Route path="/dismissed" element={<Dismissed />} />
          <Route path="/gaps" element={<Gaps />} />
          <Route path="/decisions" element={<Decisions />} />
        </Routes>
      </main>

      {!location.pathname.startsWith("/finding") && <Chat pending={pending} />}
    </>
  );
}
