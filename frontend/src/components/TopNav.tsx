import { useState } from "react";
import { NavLink } from "react-router-dom";
import { CircleAlert, Users, Wrench, Lightbulb } from "lucide-react";
import { NexusWordmark } from "./NexusWordmark";

const LINKS = [
  { to: "/", label: "Incidents", end: true, icon: CircleAlert },
  { to: "/dismissed", label: "Lookalikes", end: false, icon: Users },
  { to: "/gaps", label: "Diagnostics", end: false, icon: Wrench },
  { to: "/decisions", label: "Decisions", end: false, icon: Lightbulb },
];

export function TopNav({ team, pending }: { team: string; pending: number }) {
  // While one tab is hovered, every other tab — including the active one —
  // collapses back to its icon circle, so only one is ever expanded at a time.
  const [hovered, setHovered] = useState<string | null>(null);

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

        <nav className="topnav-links" onMouseLeave={() => setHovered(null)}>
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              aria-label={l.label}
              onMouseEnter={() => setHovered(l.to)}
              className={({ isActive }) =>
                [
                  isActive ? "active" : "",
                  hovered === l.to ? "expanded" : hovered ? "minimized" : "",
                ]
                  .filter(Boolean)
                  .join(" ")
              }
            >
              <span className="tab-icon"><l.icon size={15} strokeWidth={2.2} aria-hidden /></span>
              <span className="tab-label">{l.label}</span>
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
