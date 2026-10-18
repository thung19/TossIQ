"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AccountMenu from "./AccountMenu";

type NavItem = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

const Icon = {
  camera: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="2" y="4" width="12" height="9" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="8" cy="8.5" r="2.2" stroke="currentColor" strokeWidth="1.1" fill="none" />
    </svg>
  ),
  chart: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M2.5 13V3M2.5 13h11" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      <path d="M5.5 10V8M8 10V6M10.5 10V9" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  ),
  dataset: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <ellipse cx="8" cy="4" rx="5" ry="1.6" stroke="currentColor" strokeWidth="1.1" />
      <path d="M3 4v4M3 8v4c0 .9 2.2 1.6 5 1.6s5-.7 5-1.6V4M3 8c0 .9 2.2 1.6 5 1.6s5-.7 5-1.6" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  user: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="6" r="2.3" stroke="currentColor" strokeWidth="1.1" />
      <path d="M3.5 13.5c0-2.2 2-4 4.5-4s4.5 1.8 4.5 4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  ),
  ask: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M3 3.5h10v7H8.5L5.5 13v-2.5H3v-7z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M6.6 6.1a1.4 1.4 0 012.8.2c0 .9-1.2 1-1.3 1.8" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  ),
  hex: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 2l5 3v6l-5 3-5-3V5l5-3z" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  sq: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="3" y="3" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  hazard: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 2.2l5.6 10.2a.8.8 0 01-.7 1.2H3.1a.8.8 0 01-.7-1.2L8 2.2z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <path d="M8 6.4v3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="8" cy="11.4" r="0.7" fill="currentColor" />
    </svg>
  ),
  bulb: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M6 11.5a4 4 0 114 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-1z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <path d="M6.6 13.8h2.8" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  ),
  collapse: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.1" />
      <path d="M6 3v10" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  pin: (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 14s4.2-4.3 4.2-7.3A4.2 4.2 0 008 2.5a4.2 4.2 0 00-4.2 4.2C3.8 9.7 8 14 8 14z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="6.6" r="1.5" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
};

const PRIMARY: NavItem[] = [
  { href: "/", label: "Live sorting", icon: Icon.camera },
  { href: "/map", label: "Campus map", icon: Icon.pin },
  { href: "/analytics", label: "Analytics", icon: Icon.chart },
  { href: "/dataset", label: "Dataset", icon: Icon.dataset },
  { href: "/recommendations", label: "Recommendations", icon: Icon.bulb },
  { href: "/hazards", label: "Hazards", icon: Icon.hazard },
  { href: "/asku", label: "ASKU assistant", icon: Icon.ask },
];

// The workspace group: goals, and the work that moves them. Separated from
// the monitoring pages above because they are the only part of the product
// somebody writes to rather than reads.
const WORKSPACE: NavItem[] = [
  { href: "/initiatives", label: "Initiatives", icon: Icon.hex },
  { href: "/projects", label: "Projects", icon: Icon.sq },
];


export default function Sidebar({
  cameraOnline,
  lastInferenceMs,
  onCollapse,
}: {
  cameraOnline: boolean;
  lastInferenceMs: number | null;
  onCollapse?: () => void;
}) {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="workspace-row">
        <span className="workspace-mark">TossIQ</span>
        {onCollapse && (
          <button className="collapse" onClick={onCollapse} title="Hide sidebar (⌘B)">
            {Icon.collapse}
          </button>
        )}
      </div>

      <div className="group-label">monitor</div>
      <nav className="nav-group">
        {PRIMARY.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className={`nav-row ${active ? "active" : ""}`}>
              <span className="rail" />
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="group-label">workspace</div>
      <nav className="nav-group">
        {WORKSPACE.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className={`nav-row ${active ? "active" : ""}`}>
              <span className="rail" />
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="status">
          <div className="footer-row">
            <span className={`live-dot ${cameraOnline ? "online" : "offline"}`} />
            <span className="k">camera</span>
            <span className="v">{cameraOnline ? "online" : "offline"}</span>
          </div>
          <div className="footer-row">
            <span className="live-dot spacer" />
            <span className="k">inference</span>
            <span className="v">{lastInferenceMs != null ? `${lastInferenceMs} ms` : "-"}</span>
          </div>
        </div>
        <AccountMenu />
      </div>

      <style jsx>{`
        .sidebar {
          width: 228px;
          padding: 11px 0 0;
          border-right: 1px solid var(--border-05);
          display: flex;
          flex-direction: column;
          background: var(--bg);
          flex-shrink: 0;
        }
        .workspace-row {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 2px 10px 11px;
          border-bottom: 1px solid var(--border-05);
          margin-bottom: 12px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 12px;
        }
        .collapse {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 22px;
          height: 22px;
          margin-left: auto;
          border-radius: 4px;
          color: var(--text-dim);
        }
        .collapse:hover {
          color: var(--text-primary);
          background: var(--overlay-05);
        }
        .workspace-mark {
          color: var(--text-primary);
          font-weight: 510;
          letter-spacing: 0.01em;
        }
        /* The nav was a solid block of six rows with no gap, which reads as
           one object rather than six destinations. Each row is now a
           separately rounded, separately hoverable target with air around it,
           so the list scans as six things rather than one paragraph.

           These rules are :global() on purpose. The rows are next/link
           Link elements, and styled-jsx only adds its scoping class to host
           elements it can see statically -- a custom component gets nothing,
           so a plain .nav-row rule compiles to .nav-row.jsx-HASH and
           silently matches none of them. That is why this nav was unstyled
           until now: the rules existed and never applied. Scoping them under
           .nav-group, which is a real div and does carry the hash, keeps
           them from leaking past this component. */
        .nav-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 0 8px;
          margin-bottom: 24px;
        }
        .nav-group :global(.nav-row) {
          position: relative;
          display: grid;
          grid-template-columns: 3px 16px 1fr;
          align-items: center;
          column-gap: 11px;
          padding: 9px 10px 9px 0;
          border-radius: 5px;
          font-size: 12.5px;
          font-weight: 400;
          color: var(--text-muted);
          cursor: pointer;
          transition: background 0.1s ease, color 0.1s ease;
        }
        /* Hover was --overlay-02, i.e. 2% white: technically a highlight,
           invisible in practice against this background. It needs to be
           obvious which row the cursor is on. Static rows are excluded --
           they are not destinations, so offering the affordance would lie. */
        .nav-group :global(.nav-row:not(.static):hover) {
          background: var(--overlay-08);
          color: var(--text-primary);
        }
        .nav-group :global(.nav-row:not(.static):hover .nav-icon) {
          color: var(--text-primary);
        }
        .nav-group :global(.nav-row:not(.static):hover .rail) {
          background: var(--text-dim);
        }
        /* Active is a different colour, not merely a stronger one, so the
           page you are on never looks like the row you happen to be over. */
        .nav-group :global(.nav-row.active),
        .nav-group :global(.nav-row.active:hover) {
          background: var(--mention-bg);
          color: var(--text-primary);
          font-weight: 510;
        }
        .nav-group :global(.nav-row.active .nav-icon) {
          color: var(--mention-text);
        }
        .nav-group :global(.nav-row.active .rail) {
          background: var(--primary);
        }
        .nav-group :global(.nav-row.static) {
          cursor: default;
          color: var(--text-dim);
        }
        .nav-group :global(.rail) {
          width: 3px;
          height: 17px;
          border-radius: 2px;
          background: transparent;
          transition: background 0.1s ease;
        }
        .nav-group :global(.nav-icon) {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 16px;
          height: 16px;
          color: var(--text-dim);
          transition: color 0.1s ease;
        }
        .nav-group :global(.nav-label) {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .group-label {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          font-weight: 400;
          letter-spacing: 0.08em;
          color: var(--text-dim);
          padding: 0 18px 9px;
          text-transform: uppercase;
        }
        .sidebar-footer {
          margin-top: auto;
          display: flex;
          flex-direction: column;
        }
        .status {
          padding: 9px 14px 10px;
          border-top: 1px solid var(--border-05);
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .footer-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 10.5px;
        }
        .k {
          color: var(--text-dim);
          flex: 1;
        }
        .v {
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }
        .live-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .live-dot.online {
          background: var(--status-done);
        }
        .live-dot.offline {
          background: var(--status-backlog);
        }
        /* Keeps the second row's label aligned with the first, which has a
           status dot in front of it. */
        .live-dot.spacer {
          background: transparent;
        }
      `}</style>
    </aside>
  );
}
