"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AskuGrounding from "./AskuGrounding";
import { apiPost, type AskuAnswer } from "../../lib/api";

/**
 * The ASKU conversation, shared by the docked panel and the full page.
 *
 * One component rather than two implementations: the panel and the page ask
 * the same questions of the same endpoint and must show the same grounding,
 * and the quickest way to end up with two different sets of caveats is to
 * write the transcript twice. `compact` only changes density.
 *
 * Suggestions are PREFILLED TEXT, not hidden context. The panel knows which
 * page you are on and offers questions that suit it, but what gets sent is
 * exactly what is in the box and visible in the transcript -- quietly
 * appending "the user is looking at the campus map" would make the logged
 * question differ from the asked one.
 */

export type Turn = {
  id: number;
  question: string;
  answer: AskuAnswer | null;
  error: string | null;
};

export default function AskuConversation({
  turns,
  onTurns,
  compact = false,
  suggestions = [],
  placeholder = "Ask about this organization's waste data…",
}: {
  turns: Turn[];
  onTurns: (update: (previous: Turn[]) => Turn[]) => void;
  compact?: boolean;
  suggestions?: string[];
  placeholder?: string;
}) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  // The panel is short, so a new answer lands below the fold unless the
  // transcript follows it. The page is tall enough not to need this, but
  // doing it in both keeps one behaviour to reason about.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || pending) return;

      const id = nextId.current++;
      onTurns((previous) => [...previous, { id, question: trimmed, answer: null, error: null }]);
      setQuestion("");
      setPending(true);
      try {
        const answer = await apiPost<AskuAnswer>("/asku", { question: trimmed });
        onTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, answer } : turn))
        );
      } catch (e) {
        const message = e instanceof Error ? e.message : "Request failed";
        onTurns((previous) =>
          previous.map((turn) => (turn.id === id ? { ...turn, error: message } : turn))
        );
      } finally {
        setPending(false);
      }
    },
    [onTurns, pending]
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ask(question);
    }
  };

  return (
    <div className={`conversation ${compact ? "compact" : ""}`}>
      <div className="transcript">
        {turns.length === 0 && (
          <div className="empty">
            <p className="empty-label">
              Answers come only from what TossIQ has logged for this organization. Every
              figure is read from the recorded disposal events and product catalog shown
              under each answer.
            </p>
            {suggestions.length > 0 && (
              <>
                <span className="suggest-label">try asking</span>
                <div className="suggestions">
                  {suggestions.map((text) => (
                    <button key={text} className="suggestion" onClick={() => ask(text)}>
                      {text}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {turns.map((turn) => (
          <article key={turn.id} className="turn">
            <div className="q">
              <span className="q-mark">?</span>
              <span className="q-text">{turn.question}</span>
            </div>

            {turn.answer && (
              <div className="a">
                <p className="a-text">{turn.answer.answer}</p>
                <AskuGrounding sections={turn.answer.grounding} />
              </div>
            )}

            {turn.error && (
              <div className="a">
                <p className="a-error">{turn.error}</p>
              </div>
            )}

            {!turn.answer && !turn.error && (
              <div className="a-pending">reading logged analytics…</div>
            )}
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <section className="composer">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          rows={compact ? 2 : 3}
          disabled={pending}
        />
        <div className="composer-row">
          <span className="composer-note">
            {compact ? "each question stands alone" : "answered independently of earlier questions"}
          </span>
          <button
            type="button"
            className="ask"
            onClick={() => ask(question)}
            disabled={pending || !question.trim()}
          >
            {pending ? "asking…" : "ask"}
          </button>
        </div>
      </section>

      <style jsx>{`
        .conversation {
          display: flex;
          flex-direction: column;
          min-height: 0;
          flex: 1;
          gap: 10px;
        }
        .transcript {
          display: flex;
          flex-direction: column;
          gap: 18px;
          overflow-y: auto;
          flex: 1;
          min-height: 0;
        }
        .compact .transcript {
          gap: 14px;
          padding-right: 2px;
        }
        .empty {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .empty-label {
          font-size: 11.5px;
          line-height: 17px;
          color: var(--text-dim);
        }
        .suggest-label {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
          text-transform: uppercase;
          letter-spacing: 0.06em;
          margin-top: 4px;
        }
        .suggestions {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .suggestion {
          text-align: left;
          padding: 6px 9px;
          border: 1px solid var(--border-08);
          border-radius: 4px;
          font-size: 11.5px;
          line-height: 16px;
          color: var(--text-secondary);
        }
        .suggestion:hover {
          background: var(--overlay-05);
          border-color: var(--border-solid);
          color: var(--text-primary);
        }
        .turn {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 0;
        }
        .q {
          display: grid;
          grid-template-columns: 12px minmax(0, 1fr);
          align-items: baseline;
          column-gap: 8px;
        }
        .q-mark {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 12px;
          color: var(--text-dim);
        }
        .q-text {
          font-size: 13.5px;
          font-weight: 510;
          color: var(--text-primary);
          line-height: 20px;
          overflow-wrap: anywhere;
        }
        .compact .q-text {
          font-size: 12.5px;
          line-height: 18px;
        }
        .a {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding-left: 20px;
          min-width: 0;
        }
        .compact .a {
          padding-left: 0;
        }
        .a-text {
          font-size: 13px;
          line-height: 20px;
          color: var(--text-secondary);
          white-space: pre-wrap;
        }
        .compact .a-text {
          font-size: 12px;
          line-height: 18px;
        }
        .a-error {
          font-size: 12.5px;
          line-height: 19px;
          color: var(--status-bug);
          font-family: ui-monospace, Menlo, monospace;
          overflow-wrap: anywhere;
        }
        .a-pending {
          padding-left: 20px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          color: var(--text-dim);
        }
        .compact .a-pending {
          padding-left: 0;
        }
        .composer {
          border: 1px solid var(--border-08);
          border-radius: 4px;
          background: var(--bg-surface);
          padding: 8px 10px;
          display: flex;
          flex-direction: column;
          gap: 6px;
          flex-shrink: 0;
        }
        .composer textarea {
          width: 100%;
          resize: vertical;
          font-size: 13px;
          line-height: 19px;
          color: var(--text-primary);
        }
        .compact .composer textarea {
          font-size: 12px;
          line-height: 17px;
          resize: none;
        }
        .composer textarea::placeholder {
          color: var(--text-dim);
        }
        .composer-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .composer-note {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          color: var(--text-dim);
        }
        .compact .composer-note {
          font-size: 9.5px;
        }
        .ask {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          color: var(--text-primary);
          background: var(--overlay-08);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 4px 12px;
        }
        .ask:hover:not(:disabled) {
          background: var(--primary);
        }
        .ask:disabled {
          color: var(--text-dim);
          cursor: default;
        }
      `}</style>
    </div>
  );
}
