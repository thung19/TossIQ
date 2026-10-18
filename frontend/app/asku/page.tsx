"use client";

import { useRef, useState } from "react";
import PageHeader from "../components/PageHeader";
import AskuGrounding from "../components/AskuGrounding";
import { apiPost, type AskuAnswer } from "../../lib/api";

type Turn = {
  id: number;
  question: string;
  answer: AskuAnswer | null;
  error: string | null;
};

export default function AskuPage() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const nextId = useRef(1);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || pending) return;

    const id = nextId.current++;
    setTurns((prev) => [...prev, { id, question: trimmed, answer: null, error: null }]);
    setQuestion("");
    setPending(true);
    try {
      const answer = await apiPost<AskuAnswer>("/asku", { question: trimmed });
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, answer } : t)));
    } catch (e) {
      const message = e instanceof Error ? e.message : "Request failed";
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, error: message } : t)));
    } finally {
      setPending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  };

  const lastModel = [...turns].reverse().find((t) => t.answer)?.answer?.model_id;

  return (
    <>
      <PageHeader
        breadcrumb="Intelligence"
        title="ASKU assistant"
        right={<span className="header-meta">{lastModel || "OCI Generative AI"}</span>}
      />

      <div className="page">
        <p className="preamble">
          Answers come only from what TossIQ has logged for this organization. Every figure is
          read from the recorded disposal events and product catalog shown under each answer; the
          assistant says so plainly when the data does not cover a question.
        </p>
        <p className="preamble">
          Each question is answered on its own. Earlier questions and answers below are a log,
          not a conversation: nothing from them is sent with the next question, so name what you
          mean rather than referring back to &ldquo;that bin&rdquo; or &ldquo;it&rdquo;.
        </p>

        <section className="transcript">
          {turns.length === 0 && (
            <div className="empty">
              <span className="empty-label">no questions asked yet</span>
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

              {!turn.answer && !turn.error && <div className="a-pending">reading logged analytics…</div>}
            </article>
          ))}
        </section>

        <section className="composer">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about this organization's waste data…"
            rows={2}
            disabled={pending}
          />
          <div className="composer-row">
            <span className="composer-note">answered independently of earlier questions</span>
            <button type="button" className="ask" onClick={() => ask(question)} disabled={pending || !question.trim()}>
              {pending ? "asking…" : "ask"}
            </button>
          </div>
        </section>
      </div>

      <style jsx>{`
        .header-meta {
          font-size: 11px;
          color: var(--text-muted);
        }
        .page {
          padding: 16px 24px 24px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          max-width: 860px;
          width: 100%;
          min-width: 0;
        }
        .preamble {
          font-size: 12.5px;
          line-height: 19px;
          color: var(--text-muted);
        }
        .transcript {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .empty {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .empty-label {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          color: var(--text-dim);
          text-transform: lowercase;
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
        .a {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding-left: 20px;
          min-width: 0;
        }
        .a-text {
          font-size: 13px;
          line-height: 20px;
          color: var(--text-secondary);
          white-space: pre-wrap;
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
        .composer {
          border: 1px solid var(--border-08);
          border-radius: 4px;
          background: var(--bg-surface);
          padding: 8px 10px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .composer textarea {
          width: 100%;
          resize: vertical;
          font-size: 13px;
          line-height: 19px;
          color: var(--text-primary);
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
    </>
  );
}
