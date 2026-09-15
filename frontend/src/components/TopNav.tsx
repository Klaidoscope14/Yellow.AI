import { NavLink } from "react-router-dom";
import { NexusWordmark } from "./NexusWordmark";

const LINKS = [
  { to: "/", label: "Incidents", end: true },
  { to: "/dismissed", label: "Lookalikes", end: false },
  { to: "/gaps", label: "Diagnostics", end: false },
  { to: "/decisions", label: "Decisions", end: false },
];

export function TopNav({ team, pending }: { team: string; pending: number }) {
  return (
    <header className="topnav">
      <div className="topnav-inner">
        <div className="topnav-brand">
          <span className="nexus-wordmark"><NexusWordmark height={24} /></span>
          <div className="topnav-brand-text">
            <span className="topnav-title">Loop</span>
            <span className="topnav-subtitle">{team}</span>
          </div>
        </div>

        <nav className="topnav-links">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="topnav-right">
          <span className={`topnav-status ${pending > 0 ? "needs" : "ok"}`}>
            {pending > 0 ? `${pending} awaiting decision` : "All clear"}
          </span>
          <div className="topnav-shortcuts">
            <span><kbd>j</kbd><kbd>k</kbd> navigate</span>
            <span><kbd>&#9166;</kbd> open</span>
            <span><kbd>&#8984;K</kbd> search</span>
          </div>
        </div>
      </div>
    </header>
  );
}
