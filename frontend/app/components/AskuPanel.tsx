"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import AskuConversation, { type Turn } from "./AskuConversation";

/**
 * ASKU as a dockable right-hand panel, available on every page.
 *
 * The point of docking it is that a question usually arrives while you are
 * looking at something -- a hot can on the map, a surprising SKU on the
 * supplies tab -- and routing to a separate page to ask it means leaving
 * the thing that prompted it. The transcript lives in AppShell, above the
 * router, so it survives navigation: ask on the map, walk to analytics, the
 * answer is still there.
 *
 * Suggestions follow the current route. They are prefilled text and nothing
 * more: what is sent is what is in the box, so the question in the
 * transcript is exactly the question that was asked.
 */

const SUGGESTIONS: { match: (path: string) => boolean; questions: string[] }[] = [
  {
    match: (path) => path.startsWith("/map"),
    questions: [
      "Which building throws away the most per can?",
      "Which cans have needed service most often?",
      "What is usually thrown into the Rand Hall bins?",
    ],
  },
  {
    match: (path) => path.startsWith("/analytics"),
    questions: [
      "What material makes up most of what we throw away?",
      "Which supplier's products end up in the bin most often?",
      "How much edible food was thrown away this month?",
    ],
  },
  {
    match: (path) => path.startsWith("/recommendations"),
    questions: [
      "What is the most expensive thing we throw away?",
      "How much bottled water went in the bin last month?",
      "Which buildings waste the most food?",
    ],
  },
  {
    match: (path) => path === "/",
    questions: [
      "What has been thrown away in the last 24 hours?",
      "What share of items are we diverting from landfill?",
      "Which items is the classifier least sure about?",
    ],
  },
];

const FALLBACK_QUESTIONS = [
  "What are the top items thrown away this month?",
  "How much have we spent on things that ended up in the bin?",
  "Which bin sees the most contamination?",
];

export const ASKU_MIN_WIDTH = 300;
export const ASKU_MAX_WIDTH = 680;

export default function AskuPanel({
  turns,
  onTurns,
  onClose,
  width,
  onWidthChange,
}: {
  turns: Turn[];
  onTurns: (update: (previous: Turn[]) => Turn[]) => void;
  onClose: () => void;
  width: number;
  onWidthChange: (width: number) => void;
}) {
  const pathname = usePathname();
  const draggingRef = useRef(false);

  const suggestions =
    SUGGESTIONS.find((entry) => entry.match(pathname))?.questions ?? FALLBACK_QUESTIONS;

  // Drag to resize. Listeners go on the document rather than the handle so a
  // fast drag that outruns the pointer does not drop the gesture, and the
  // body's cursor and text selection are locked for the duration so the page
  // underneath does not highlight as you pull.
  const startResize = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      draggingRef.current = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (move: PointerEvent) => {
        if (!draggingRef.current) return;
        const next = Math.min(
          ASKU_MAX_WIDTH,
          Math.max(ASKU_MIN_WIDTH, window.innerWidth - move.clientX - 8)
        );
        onWidthChange(next);
      };
      const onUp = () => {
        draggingRef.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
      };
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    },
    [onWidthChange]
  );

  useEffect(
    () => () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    },
    []
  );

  return (
    <aside className="panel" style={{ width }}>
      <div
        className="resize"
        onPointerDown={startResize}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize assistant panel"
      />

      <header>
        <span className="title">ASKU</span>
        <span className="sub">grounded in logged data</span>
        <span className="spacer" />
        {turns.length > 0 && (
          <button className="icon" onClick={() => onTurns(() => [])} title="Clear transcript">
            clear
          </button>
        )}
        <button className="icon close" onClick={onClose} title="Hide assistant (⌘I)">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path
              d="M4.5 4.5l7 7M11.5 4.5l-7 7"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>

      <div className="body">
        <AskuConversation
          turns={turns}
          onTurns={onTurns}
          compact
          suggestions={suggestions}
          placeholder="Ask about what you're looking at…"
        />
      </div>

      <style jsx>{`
        /* Sticky to the viewport, not stretched to the frame. The app frame
           is min-height rather than height, so a long page makes it taller
           than the window -- and a panel that simply filled it would put its
           composer at the bottom of the analytics page rather than in front
           of you. Pinned, the transcript scrolls inside the panel and the
           box to type in never leaves the screen. */
        .panel {
          position: sticky;
          top: 0;
          align-self: flex-start;
          height: calc(100vh - 16px);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          min-width: 0;
          border-left: 1px solid var(--border-solid);
          background: var(--bg-surface);
        }
        /* Sits astride the border so there is a few pixels of grab either
           side of a one-pixel line. */
        .resize {
          position: absolute;
          left: -3px;
          top: 0;
          bottom: 0;
          width: 7px;
          cursor: col-resize;
          z-index: 20;
        }
        .resize:hover {
          background: var(--primary);
          opacity: 0.35;
        }
        header {
          display: flex;
          align-items: baseline;
          gap: 7px;
          padding: 8px 10px;
          border-bottom: 1px solid var(--border-05);
          font-family: ui-monospace, Menlo, monospace;
          flex-shrink: 0;
        }
        .title {
          font-size: 12px;
          font-weight: 510;
          color: var(--text-primary);
          letter-spacing: 0.02em;
        }
        .sub {
          font-size: 9.5px;
          color: var(--text-dim);
        }
        .spacer {
          flex: 1;
        }
        .icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 2px 6px;
          border-radius: 3px;
          color: var(--text-dim);
          font-family: inherit;
          font-size: 9.5px;
          align-self: center;
        }
        .icon:hover {
          background: var(--overlay-05);
          color: var(--text-primary);
        }
        .close {
          padding: 3px;
        }
        .body {
          display: flex;
          flex-direction: column;
          flex: 1;
          min-height: 0;
          padding: 10px;
        }
      `}</style>
    </aside>
  );
}
