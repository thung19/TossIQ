"use client";

import { useState } from "react";
import type { AskuObservationSection } from "../../lib/api";

/** The observations an ASKU answer was produced from.
 *
 * These are the exact lines the model was shown -- nothing else was in its
 * context -- so an operator can check every figure in an answer against the
 * data it came from, per the PRD's rule that observed data stay
 * distinguishable from model output. */
export default function AskuGrounding({ sections }: { sections: AskuObservationSection[] }) {
  const [open, setOpen] = useState(false);
  const lineCount = sections.reduce((acc, s) => acc + s.lines.length, 0);

  return (
    <section className="grounding">
      <button type="button" className="toggle" onClick={() => setOpen((v) => !v)}>
        <span className="chev">{open ? "−" : "+"}</span>
        <span className="label">observations this answer was grounded in</span>
        <span className="count">{lineCount}</span>
      </button>

      {open && (
        <div className="body">
          {sections.map((section) => (
            <article key={section.title} className="section">
              <h4>{section.title}</h4>
              <ul>
                {section.lines.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}

      <style jsx>{`
        .grounding {
          border: 1px solid var(--border-08);
          border-radius: 3px;
          background: var(--bg-surface);
          font-family: ui-monospace, Menlo, monospace;
        }
        .toggle {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          padding: 6px 10px;
          font-size: 11px;
          color: var(--text-dim);
          text-align: left;
        }
        .toggle:hover {
          color: var(--text-secondary);
          background: var(--overlay-02);
        }
        .chev {
          width: 10px;
          color: var(--text-muted);
        }
        .label {
          flex: 1;
        }
        .count {
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }
        .body {
          border-top: 1px solid var(--border-05);
          padding: 8px 10px 10px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          max-height: 340px;
          overflow-y: auto;
        }
        .section h4 {
          font-size: 10.5px;
          font-weight: 400;
          color: var(--text-dim);
          text-transform: lowercase;
          margin-bottom: 3px;
        }
        .section ul {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 1px;
        }
        .section li {
          font-size: 11.5px;
          line-height: 17px;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
          overflow-wrap: anywhere;
        }
      `}</style>
    </section>
  );
}
