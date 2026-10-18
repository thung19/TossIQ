"use client";

import { useState } from "react";
import PageHeader from "../components/PageHeader";
import AskuConversation, { type Turn } from "../components/AskuConversation";

/**
 * ASKU as a full page, for a longer sitting.
 *
 * The same assistant is docked on the right of every page (⌘I), which is
 * where most questions get asked -- they arrive while you are looking at
 * something. This page exists for the other case: a reading session where
 * the grounding tables under each answer want room, and the panel's 380
 * pixels do not give it to them.
 *
 * Both render the same AskuConversation, so there is one transcript
 * implementation and one set of caveats. Their histories are separate,
 * though: the panel's lives in the app shell above the router, this one's
 * lives here.
 */
export default function AskuPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const lastModel = [...turns].reverse().find((turn) => turn.answer)?.answer?.model_id;

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
          read from the recorded disposal events and product catalog shown under each answer;
          the assistant says so plainly when the data does not cover a question.
        </p>
        <p className="preamble">
          Each question is answered on its own. Earlier questions and answers below are a log,
          not a conversation: nothing from them is sent with the next question, so name what you
          mean rather than referring back to &ldquo;that bin&rdquo; or &ldquo;it&rdquo;.
        </p>
        <p className="preamble dim">
          The same assistant is docked on the right of every page, press{" "}
          <kbd>⌘I</kbd> to ask without leaving what you are looking at. That panel keeps its own
          transcript.
        </p>

        <AskuConversation
          turns={turns}
          onTurns={(update) => setTurns(update)}
          suggestions={[
            "What are the top items thrown away this month?",
            "Which building throws away the most food?",
            "How much have we spent on things that ended up in the bin?",
          ]}
        />
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
          flex: 1;
          min-height: 0;
        }
        .preamble {
          font-size: 12.5px;
          line-height: 19px;
          color: var(--text-muted);
        }
        .preamble.dim {
          color: var(--text-dim);
        }
        kbd {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          color: var(--text-secondary);
          background: var(--overlay-05);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 0 4px;
        }
      `}</style>
    </>
  );
}
