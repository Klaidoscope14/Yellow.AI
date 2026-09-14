import { NavLink, useLocation } from "react-router-dom";
import { Icon } from "./Icon";
import "../styles/global.css"; // Ensure styles are applied

const ShieldAlertIcon = () => (
  <Icon size={21}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="M12 8v4" />
    <path d="M12 16h.01" />
  </Icon>
);

const CheckCircleIcon = () => (
  <Icon size={21}>
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </Icon>
);

const ActivityIcon = () => (
  <Icon size={21}>
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </Icon>
);

const ClipboardCheckIcon = () => (
  <Icon size={21}>
    <rect x="8" y="2" width="8" height="4" rx="1" />
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <path d="m9 14 2 2 4-4" />
  </Icon>
);

export function Sidebar() {
  const location = useLocation();
  // Incidents is the permanent left pane, so it reads "active" for every
  // route except the three that take over the right pane explicitly.
  const onOtherSection = ["/dismissed", "/gaps", "/decisions"].some((p) =>
    location.pathname.startsWith(p),
  );

  return (
    <nav className="sidebar">
      <div className="sidebar-top">
        <div className="sidebar-avatar top-avatar">A</div>

        <NavLink to="/" className={`sidebar-link ${!onOtherSection ? "active" : ""}`}>
          <div className="icon-container">
            <ShieldAlertIcon />
            <span className="tooltip">Control Center</span>
          </div>
          <span className="label">Incidents</span>
        </NavLink>

        <NavLink to="/dismissed" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <div className="icon-container">
            <CheckCircleIcon />
            <span className="tooltip">Dismissed</span>
          </div>
          <span className="label">Lookalikes</span>
        </NavLink>

        <NavLink to="/gaps" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <div className="icon-container">
            <ActivityIcon />
            <span className="tooltip">Gaps</span>
          </div>
          <span className="label">Diagnostics</span>
        </NavLink>

        <NavLink to="/decisions" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <div className="icon-container">
            <ClipboardCheckIcon />
            <span className="tooltip">Decisions</span>
          </div>
          <span className="label">Decisions</span>
        </NavLink>
      </div>

      <div className="sidebar-bottom">
        <div className="sidebar-avatar bottom-avatar">K</div>
        <span className="label" style={{ marginTop: '4px' }}>Khanak</span>
      </div>
    </nav>
  );
}
