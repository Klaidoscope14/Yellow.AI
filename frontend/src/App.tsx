import { Routes, Route, useLocation } from "react-router-dom";
import { useReport } from "./hooks/ReportContext";
import { useResizableSplit } from "./hooks/useResizableSplit";
import { needsDecisionCount } from "./lib/report";
import { ControlCenter } from "./screens/ControlCenter";
import { FindingDetail } from "./screens/FindingDetail";
import { Dismissed } from "./screens/Dismissed";
import { Gaps } from "./screens/Gaps";
import { Decisions } from "./screens/Decisions";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
import { Icon } from "./components/Icon";
import { CommandPalette } from "./components/CommandPalette";

function RightPaneEmpty() {
  return (
    <div className="right-empty">
      <div className="right-empty-badge">
        <Icon size={22} strokeWidth={1.5}>
          <path d="M9 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h4" />
          <path d="M9 4h9a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H9" />
          <path d="M9 4v16" />
          <path d="m14 9 3 3-3 3" />
        </Icon>
      </div>
      <p className="right-empty-title">Select an incident to see the full decision</p>
      <p className="right-empty-sub">
        Every number on the right traces back to this report &mdash; nothing here is invented.
      </p>
    </div>
  );
}

function RightPane() {
  const location = useLocation();
  return (
    <div className="right-pane">
      <div className="right-pane-inner pane-enter" key={location.pathname}>
        <Routes>
          <Route path="/" element={<RightPaneEmpty />} />
          <Route path="/finding/:id" element={<FindingDetail />} />
          <Route path="/dismissed" element={<Dismissed />} />
          <Route path="/gaps" element={<Gaps />} />
          <Route path="/decisions" element={<Decisions />} />
        </Routes>
      </div>
    </div>
  );
}

export function App() {
  const { report, loading, error } = useReport();
  const location = useLocation();

  if (loading) return <div className="loading">Loading report&hellip;</div>;
  if (error) return <div className="error">Failed to load report: {error}</div>;
  if (!report) return null;

  const pending = needsDecisionCount(report);
  const findingMatch = location.pathname.match(/^\/finding\/([^/]+)/);
  const selectedFindingId = findingMatch ? decodeURIComponent(findingMatch[1]) : null;

  const { containerRef, leftWidth, startDrag, resetSplit } = useResizableSplit();

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="content-area">
        <header className="topbar">
          <div className="wrap" style={{ maxWidth: "none" }}>
            <span className="brand"><span className="brand-mark" />NEXUS LOOP</span>
            <span className="brand-subtitle">{report.team}</span>
            <span
              className="topbar-status"
              style={
                pending > 0
                  ? { background: "var(--status-needs-bg)", color: "var(--status-needs-ink)" }
                  : { background: "var(--status-ok-bg)", color: "var(--status-ok-ink)" }
              }
            >
              {pending > 0 ? `${pending} awaiting decision` : "All clear"}
            </span>
          </div>
        </header>

        <div className="split-view" ref={containerRef}>
          <div
            className="left-pane"
            style={leftWidth != null ? { flex: `0 0 ${leftWidth}px` } : undefined}
          >
            <ControlCenter selectedId={selectedFindingId} />
          </div>

          <div
            className="gutter"
            onMouseDown={startDrag}
            onDoubleClick={resetSplit}
            role="separator"
            aria-orientation="vertical"
            title="Drag to resize · double-click to reset"
          >
            <span className="gutter-handle" />
          </div>

          <RightPane />
        </div>
      </div>

      <Chat pending={pending} />
      <CommandPalette />
    </div>
  );
}
