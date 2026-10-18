"use client";

import { useCallback, useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import { apiFetch, type CameraStats } from "../../lib/api";

// Remembered per browser so the choice survives a reload. Deliberately not
// server state: which chrome one person hides on their own screen is not
// something the organization needs to know.
const COLLAPSE_KEY = "tossiq.sidebar.collapsed";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [stats, setStats] = useState<CameraStats | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  // Read after mount, never during render: the server has no localStorage, so
  // seeding state from it directly would hydrate to a different tree than it
  // rendered. The first paint is always the expanded sidebar; a collapsed
  // preference applies a frame later.
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* private mode, or site data blocked -- the default stands */
    }
  }, []);

  const toggleSidebar = useCallback(() => {
    setCollapsed((previous) => {
      const next = !previous;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* the toggle still works for this session */
      }
      return next;
    });
  }, []);

  // Cmd/Ctrl-B, the convention every editor and chat app uses for this.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar]);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await apiFetch<CameraStats>("/camera/stats");
        if (alive) setStats(s);
      } catch {
        if (alive) setStats(null);
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const online = Boolean(stats?.camera_opened && stats.running);

  return (
    <div className="app-root">
      <div className="app-frame">
        {!collapsed && (
          <Sidebar
            cameraOnline={online}
            lastInferenceMs={stats?.last_inference_ms ?? null}
            onCollapse={toggleSidebar}
          />
        )}
        <main className={`main-area ${collapsed ? "collapsed" : ""}`}>
          {/* With the sidebar gone there is no visible way back to it, so the
              toggle leaves a small anchored button behind rather than relying
              on the keyboard shortcut alone. */}
          {collapsed && (
            <button className="reveal" onClick={toggleSidebar} title="Show sidebar (⌘B)">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
                <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.1" />
                <path d="M6 3v10" stroke="currentColor" strokeWidth="1.1" />
              </svg>
            </button>
          )}
          {children}
        </main>
      </div>
      <style jsx>{`
        .app-root {
          min-height: 100vh;
          background: var(--bg);
          padding: 8px;
        }
        .app-frame {
          display: flex;
          min-height: calc(100vh - 16px);
          border: 1px solid var(--border-solid);
          border-radius: 4px;
          overflow: hidden;
          background: var(--bg);
        }
        .main-area {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
          overflow-y: auto;
          position: relative;
        }
        /* Only the header indents to make room for the reveal button. Padding
           the whole main area would push every panel in from the edge, which
           is the opposite of what collapsing the sidebar is for. */
        .main-area.collapsed :global(.page-header) {
          padding-left: 40px;
        }
        .reveal {
          position: absolute;
          top: 9px;
          left: 8px;
          z-index: 30;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border-radius: 4px;
          color: var(--text-dim);
          background: var(--bg-card);
          border: 1px solid var(--border-08);
        }
        .reveal:hover {
          color: var(--text-primary);
          background: var(--bg-elevated);
        }
      `}</style>
    </div>
  );
}
