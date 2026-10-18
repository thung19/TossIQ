"use client";

import { useCallback, useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import AskuPanel, { ASKU_MAX_WIDTH, ASKU_MIN_WIDTH } from "./AskuPanel";
import type { Turn } from "./AskuConversation";
import { apiFetch, type CameraStats } from "../../lib/api";

// Remembered per browser so the choice survives a reload. Deliberately not
// server state: which chrome one person hides on their own screen is not
// something the organization needs to know.
const COLLAPSE_KEY = "tossiq.sidebar.collapsed";
const ASKU_OPEN_KEY = "tossiq.asku.open";
const ASKU_WIDTH_KEY = "tossiq.asku.width";
const ASKU_DEFAULT_WIDTH = 380;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [stats, setStats] = useState<CameraStats | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [askuOpen, setAskuOpen] = useState(false);
  const [askuWidth, setAskuWidth] = useState(ASKU_DEFAULT_WIDTH);
  // The transcript lives here, above the router, so asking a question on the
  // map and then walking to analytics does not throw the answer away. That
  // is most of the value of docking the assistant rather than giving it a
  // page of its own.
  const [askuTurns, setAskuTurns] = useState<Turn[]>([]);

  // Read after mount, never during render: the server has no localStorage, so
  // seeding state from it directly would hydrate to a different tree than it
  // rendered. The first paint is always the expanded sidebar; a collapsed
  // preference applies a frame later.
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
      setAskuOpen(window.localStorage.getItem(ASKU_OPEN_KEY) === "1");
      const storedWidth = Number(window.localStorage.getItem(ASKU_WIDTH_KEY));
      if (Number.isFinite(storedWidth) && storedWidth >= ASKU_MIN_WIDTH) {
        setAskuWidth(Math.min(ASKU_MAX_WIDTH, storedWidth));
      }
    } catch {
      /* private mode, or site data blocked -- the defaults stand */
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

  const toggleAsku = useCallback(() => {
    setAskuOpen((previous) => {
      const next = !previous;
      try {
        window.localStorage.setItem(ASKU_OPEN_KEY, next ? "1" : "0");
      } catch {
        /* the toggle still works for this session */
      }
      return next;
    });
  }, []);

  const resizeAsku = useCallback((width: number) => {
    setAskuWidth(width);
    try {
      window.localStorage.setItem(ASKU_WIDTH_KEY, String(Math.round(width)));
    } catch {
      /* the drag still works for this session */
    }
  }, []);

  // Cmd/Ctrl-B for the sidebar and Cmd/Ctrl-I for the assistant, the
  // conventions editors and chat apps already use for a left and a right
  // dock.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!event.metaKey && !event.ctrlKey) return;
      const key = event.key.toLowerCase();
      if (key === "b") {
        event.preventDefault();
        toggleSidebar();
      } else if (key === "i") {
        event.preventDefault();
        toggleAsku();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar, toggleAsku]);

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

          {/* The launcher only exists while the panel is hidden, so there is
              never a button on screen for the thing already on screen. */}
          {!askuOpen && (
            <button className="asku-launch" onClick={toggleAsku} title="Ask ASKU (⌘I)">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path
                  d="M3 3.5h10v7H8.5L5.5 13v-2.5H3v-7z"
                  stroke="currentColor"
                  strokeWidth="1.2"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Ask</span>
            </button>
          )}
        </main>

        {askuOpen && (
          <AskuPanel
            turns={askuTurns}
            onTurns={(update) => setAskuTurns(update)}
            onClose={toggleAsku}
            width={askuWidth}
            onWidthChange={resizeAsku}
          />
        )}
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
        /* Anchored to the viewport, not the scroll container, so it stays
           reachable however far down a long analytics page you are. */
        .asku-launch {
          position: fixed;
          right: 18px;
          bottom: 18px;
          z-index: 40;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 7px 12px;
          border-radius: 18px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          color: var(--text-secondary);
          background: var(--bg-elevated);
          border: 1px solid var(--border-solid);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
        }
        .asku-launch:hover {
          color: var(--text-primary);
          border-color: var(--primary);
        }
      `}</style>
    </div>
  );
}
