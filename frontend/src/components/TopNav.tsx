import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { CircleAlert, Users, Wrench, Lightbulb } from "lucide-react";
import nexusLogo from "../assets/nexus-logo.png";

const LINKS = [
  { to: "/", label: "Issues", end: true, icon: CircleAlert },
  { to: "/dismissed", label: "Lookalikes", end: false, icon: Users },
  { to: "/gaps", label: "Diagnostics", end: false, icon: Wrench },
  { to: "/decisions", label: "Decisions", end: false, icon: Lightbulb },
];

export function TopNav() {
  // While one tab is hovered, every other tab — including the active one —
  // collapses back to its icon circle, so only one is ever expanded at a time.
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <header className="topnav">
      <div className="topnav-inner">
        <Link to="/" className="topnav-brand" aria-label="Go to home">
          <img src={nexusLogo} alt="Nexus" className="nexus-logo" />
        </Link>

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
          <button type="button" className="topnav-live">
            <span className="topnav-live-dot" aria-hidden />
            Live
          </button>

        </div>
      </div>
    </header>
  );
}
