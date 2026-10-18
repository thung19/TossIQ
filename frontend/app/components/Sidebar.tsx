"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

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
  { href: "/operations", label: "Operator insights", icon: Icon.user },
  { href: "/asku", label: "ASKU assistant", icon: Icon.ask },
];

export default function Sidebar({
  cameraOnline,
  lastInferenceMs,
}: {
  cameraOnline: boolean;
  lastInferenceMs: number | null;
}) {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="workspace-row">
        <span className="workspace-mark">tossiq</span>
        <span className="workspace-sep">/</span>
        <span className="workspace-env">ops</span>
      </div>

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
        <div className="nav-row static">
          <span className="rail" />
          <span className="nav-icon">{Icon.hex}</span>
          <span className="nav-label">Initiatives</span>
        </div>
        <div className="nav-row static">
          <span className="rail" />
          <span className="nav-icon">{Icon.sq}</span>
          <span className="nav-label">Projects</span>
        </div>
      </nav>

      <div className="sidebar-footer">
        <div className="footer-row">
          <span className={`live-dot ${cameraOnline ? "online" : "offline"}`} />
          <span className="k">cam</span>
          <span className="v">{cameraOnline ? "online" : "offline"}</span>
        </div>
        <div className="footer-row">
          <span className="k">lat</span>
          <span className="v">{lastInferenceMs != null ? `${lastInferenceMs}ms` : "—"}</span>
        </div>
      </div>

      <style jsx>{`
        .sidebar {
          width: 212px;
          padding: 10px 0 0;
          border-right: 1px solid var(--border-05);
          display: flex;
          flex-direction: column;
          background: var(--bg);
          flex-shrink: 0;
        }
        .workspace-row {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 3px 12px 10px;
          border-bottom: 1px solid var(--border-05);
          margin-bottom: 6px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 12px;
        }
        .workspace-mark {
          color: var(--text-primary);
          font-weight: 510;
        }
        .workspace-sep {
          color: var(--text-dim);
        }
        .workspace-env {
          color: var(--text-muted);
        }
        .nav-group {
          display: flex;
          flex-direction: column;
          gap: 0;
          margin-bottom: 10px;
        }
        .nav-row {
          position: relative;
          display: grid;
          grid-template-columns: 2px 16px 1fr;
          align-items: center;
          column-gap: 10px;
          padding: 5px 12px 5px 0;
          font-size: 12.5px;
          font-weight: 400;
          color: var(--text-muted);
          cursor: pointer;
          transition: background 0.08s ease, color 0.08s ease;
        }
        .nav-row:hover {
          background: var(--overlay-02);
          color: var(--text-secondary);
        }
        .nav-row:hover .nav-icon {
          color: var(--text-secondary);
        }
        .nav-row.active {
          background: var(--overlay-05);
          color: var(--text-primary);
          font-weight: 510;
        }
        .nav-row.active .nav-icon {
          color: var(--text-primary);
        }
        .nav-row.static {
          cursor: default;
        }
        .rail {
          width: 2px;
          height: 16px;
          background: transparent;
          margin-left: 0;
        }
        .nav-row.active .rail {
          background: var(--text-primary);
        }
        .nav-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 16px;
          height: 16px;
          color: var(--text-dim);
        }
        .nav-label {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .group-label {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10px;
          font-weight: 400;
          color: var(--text-dim);
          padding: 2px 12px 4px;
          text-transform: lowercase;
        }
        .sidebar-footer {
          margin-top: auto;
          padding: 8px 12px;
          border-top: 1px solid var(--border-05);
          display: flex;
          flex-direction: column;
          gap: 3px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .footer-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
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
      `}</style>
    </aside>
  );
}
