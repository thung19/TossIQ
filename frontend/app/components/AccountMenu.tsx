"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The signed-in account and its preferences, at the foot of the sidebar.
 *
 * MOCK ACCOUNT. TossIQ has no authentication yet, so there is no real session
 * to read: the identity below is a placeholder standing in for whatever
 * sign-in eventually lands, and the panel says so rather than letting a demo
 * audience assume the org and role are enforced somewhere. The preferences
 * are real to the extent that they persist per browser; only the ones marked
 * as wired actually change anything today.
 */

const ACCOUNT = {
  name: "Dana Whitfield",
  email: "facilities-ops@vanderbilt.edu",
  role: "Facilities analytics",
  org: "Vanderbilt University",
  initials: "DW",
};

const PREFERENCES_KEY = "tossiq.preferences";

type Preferences = {
  showSimulated: boolean;
  twentyFourHour: boolean;
  weeklyDigest: boolean;
};

const DEFAULT_PREFERENCES: Preferences = {
  showSimulated: true,
  twentyFourHour: false,
  weeklyDigest: true,
};

export default function AccountMenu() {
  const [open, setOpen] = useState(false);
  const [preferences, setPreferences] = useState<Preferences>(DEFAULT_PREFERENCES);
  const wrapRef = useRef<HTMLDivElement>(null);

  // After mount, never during render: the server has no localStorage and
  // seeding from it directly would hydrate a different tree than was sent.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(PREFERENCES_KEY);
      if (stored) setPreferences({ ...DEFAULT_PREFERENCES, ...JSON.parse(stored) });
    } catch {
      /* unreadable or absent -- the defaults stand */
    }
  }, []);

  const toggle = (key: keyof Preferences) => {
    setPreferences((previous) => {
      const next = { ...previous, [key]: !previous[key] };
      try {
        window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
      } catch {
        /* still applies for this session */
      }
      return next;
    });
  };

  // Close on an outside click or Escape, the two things anyone tries first.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="wrap" ref={wrapRef}>
      {open && (
        <div className="menu" role="menu">
          <div className="identity">
            <span className="avatar big">{ACCOUNT.initials}</span>
            <span className="who">
              <span className="name">{ACCOUNT.name}</span>
              <span className="email">{ACCOUNT.email}</span>
              <span className="org">
                {ACCOUNT.org} · {ACCOUNT.role}
              </span>
            </span>
          </div>

          <div className="section">preferences</div>
          <Toggle
            label="Show simulated cans"
            hint="wired"
            on={preferences.showSimulated}
            onClick={() => toggle("showSimulated")}
          />
          <Toggle
            label="24-hour time"
            on={preferences.twentyFourHour}
            onClick={() => toggle("twentyFourHour")}
          />
          <Toggle
            label="Weekly waste digest"
            on={preferences.weeklyDigest}
            onClick={() => toggle("weeklyDigest")}
          />

          <div className="section">shortcuts</div>
          <div className="shortcut">
            <span>Hide sidebar</span>
            <kbd>⌘B</kbd>
          </div>

          <div className="divider" />
          <button className="item" disabled>
            Organization settings
          </button>
          <button className="item" disabled>
            Catalog &amp; SKU import
          </button>
          <button className="item danger" disabled>
            Sign out
          </button>

          <p className="disclaimer">
            Mock account. TossIQ has no sign-in yet, so this identity is a placeholder and the
            greyed items do nothing. Preferences are stored in this browser only; just the one
            marked <b>wired</b> changes what the app shows today.
          </p>
        </div>
      )}

      <button
        className={`trigger ${open ? "on" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="avatar">{ACCOUNT.initials}</span>
        <span className="who">
          <span className="name">{ACCOUNT.name}</span>
          <span className="role">{ACCOUNT.role}</span>
        </span>
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d="M5 10.5L8 7l3 3.5"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      <style jsx>{`
        .wrap {
          position: relative;
          padding: 7px 8px 9px;
          border-top: 1px solid var(--border-05);
        }
        .trigger {
          display: grid;
          grid-template-columns: 22px minmax(0, 1fr) 10px;
          align-items: center;
          gap: 8px;
          width: 100%;
          padding: 5px 6px;
          border-radius: 4px;
          text-align: left;
          color: var(--text-muted);
        }
        .trigger:hover,
        .trigger.on {
          background: var(--overlay-05);
        }
        .avatar {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 22px;
          height: 22px;
          border-radius: 50%;
          background: var(--mention-bg);
          color: var(--mention-text);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          font-weight: 510;
          letter-spacing: 0.02em;
        }
        .avatar.big {
          width: 30px;
          height: 30px;
          font-size: 11.5px;
        }
        .who {
          display: flex;
          flex-direction: column;
          min-width: 0;
          gap: 1px;
        }
        .name {
          color: var(--text-primary);
          font-size: 12px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .role,
        .email,
        .org {
          color: var(--text-dim);
          font-size: 10px;
          line-height: 13px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .menu {
          position: absolute;
          left: 8px;
          right: 8px;
          bottom: calc(100% - 2px);
          z-index: 60;
          display: flex;
          flex-direction: column;
          padding: 4px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-solid);
          border-radius: 5px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
          /* The menu opens upward from the foot of the sidebar, so on a short
             window it would otherwise run off the top of the screen and take
             the sign-out item with it. */
          max-height: calc(100vh - 110px);
          overflow-y: auto;
        }
        .identity {
          display: grid;
          grid-template-columns: 30px minmax(0, 1fr);
          gap: 8px;
          align-items: center;
          padding: 7px 7px 9px;
        }
        .section {
          padding: 6px 7px 3px;
          margin-top: 2px;
          border-top: 1px solid var(--border-05);
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
        }
        .shortcut {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 4px 7px;
          font-size: 11.5px;
          color: var(--text-muted);
        }
        kbd {
          font-size: 10px;
          color: var(--text-dim);
          background: var(--overlay-05);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 0 4px;
        }
        .divider {
          height: 1px;
          background: var(--border-05);
          margin: 4px 0;
        }
        .item {
          display: block;
          width: 100%;
          padding: 5px 7px;
          border-radius: 3px;
          text-align: left;
          font-size: 11.5px;
          color: var(--text-secondary);
        }
        .item:hover:not(:disabled) {
          background: var(--overlay-05);
        }
        .item:disabled {
          color: var(--text-dim);
          cursor: not-allowed;
        }
        .item.danger:disabled {
          color: var(--text-dim);
        }
        .disclaimer {
          padding: 7px 7px 5px;
          margin-top: 4px;
          border-top: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 9.5px;
          line-height: 13px;
        }
        .disclaimer b {
          color: var(--text-muted);
          font-weight: 510;
        }
      `}</style>
    </div>
  );
}

function Toggle({
  label,
  hint,
  on,
  onClick,
}: {
  label: string;
  hint?: string;
  on: boolean;
  onClick: () => void;
}) {
  return (
    <button className="row" onClick={onClick} role="switch" aria-checked={on}>
      <span className="label">
        {label}
        {hint && <span className="hint">{hint}</span>}
      </span>
      <span className={`switch ${on ? "on" : ""}`}>
        <span className="knob" />
      </span>
      <style jsx>{`
        .row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          width: 100%;
          padding: 4px 7px;
          border-radius: 3px;
          text-align: left;
          font-size: 11.5px;
          color: var(--text-secondary);
        }
        .row:hover {
          background: var(--overlay-05);
        }
        .label {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          min-width: 0;
        }
        .hint {
          color: var(--status-done);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 8.5px;
          border: 1px solid currentColor;
          border-radius: 2px;
          padding: 0 3px;
          line-height: 12px;
        }
        .switch {
          position: relative;
          flex-shrink: 0;
          width: 24px;
          height: 14px;
          border-radius: 7px;
          background: var(--overlay-08);
          border: 1px solid var(--border-08);
          transition: background 0.12s ease;
        }
        .switch.on {
          background: var(--primary);
          border-color: var(--primary);
        }
        .knob {
          position: absolute;
          top: 1px;
          left: 1px;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--text-primary);
          transition: transform 0.12s ease;
        }
        .switch.on .knob {
          transform: translateX(10px);
        }
      `}</style>
    </button>
  );
}
