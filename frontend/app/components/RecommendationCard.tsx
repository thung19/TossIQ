"use client";

import EvidenceBlocks from "./EvidenceBlocks";
import { KIND_LABEL, type Recommendation } from "../../lib/api";

/**
 * One recommendation, collapsed to a card and expandable to its evidence.
 *
 * Collapsed, the card says what to do and what it is worth. Expanded, it
 * shows the observations behind it, the basis the rule measured, and the
 * caveat -- in that order, because the reader who opens a card is asking
 * "why should I believe this", and the answer is the data first and the
 * disclaimer second.
 *
 * The caveat is never hidden behind the expander alone when it qualifies the
 * headline number: a projection labelled only inside a panel nobody opens is
 * a projection presented as a fact.
 */
export default function RecommendationCard({
  recommendation,
  expanded,
  onToggle,
}: {
  recommendation: Recommendation;
  expanded: boolean;
  onToggle: () => void;
}) {
  const saving = recommendation.annual_saving;

  return (
    <article className={`card ${expanded ? "open" : ""}`}>
      <button className="head" onClick={onToggle} aria-expanded={expanded}>
        <span className="top">
          <span className={`kind ${recommendation.kind}`}>
            {KIND_LABEL[recommendation.kind] ?? recommendation.kind}
          </span>
          <span className={`confidence ${recommendation.confidence}`}>
            {recommendation.confidence} confidence
          </span>
          {saving != null && saving > 0 && (
            <span className="saving">
              ~${saving.toLocaleString(undefined, { maximumFractionDigits: 0 })}/yr
              <span className="proj">projected</span>
            </span>
          )}
          <span className={`chevron ${expanded ? "up" : ""}`} aria-hidden>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path
                d="M5 6.5L8 10l3-3.5"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </span>

        <h3>{recommendation.title}</h3>
        <p className="summary">{recommendation.summary}</p>

        <span className="action">
          <span className="arrow">→</span>
          {recommendation.action}
        </span>

        {!expanded && (
          <span className="peek">
            {recommendation.evidence.length} supporting observation
            {recommendation.evidence.length === 1 ? "" : "s"} · click to see the data
          </span>
        )}
      </button>

      {expanded && (
        <div className="body">
          <EvidenceBlocks evidence={recommendation.evidence} />

          <div className="provenance">
            <p>
              <b>How this was measured.</b> {recommendation.basis}
            </p>
            {recommendation.caveat && (
              <p className="caveat">
                <b>What it does not tell you.</b> {recommendation.caveat}
              </p>
            )}
            {saving != null && saving > 0 && (
              <p className="caveat">
                <b>The saving is a projection.</b> ${saving.toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })} is the last {recommendation.window_days} days scaled to a year. It
                assumes the next twelve months look like that window, which for a campus
                with a summer they will not exactly.
              </p>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .card {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 4px;
          min-width: 0;
          overflow: hidden;
          transition: border-color 0.1s ease;
        }
        .card:hover {
          border-color: var(--border-solid);
        }
        .card.open {
          border-color: var(--primary);
        }
        .head {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 11px 13px 12px;
          text-align: left;
          width: 100%;
        }
        .top {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }
        .kind {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          line-height: 15px;
          padding: 0 6px;
          border-radius: 2px;
          border: 1px solid currentColor;
          color: var(--text-muted);
        }
        .kind.procurement {
          color: var(--cat-recycling);
        }
        .kind.food {
          color: var(--cat-compost);
        }
        .kind.operations {
          color: var(--status-in-progress);
        }
        .kind.placement {
          color: var(--mention-text);
        }
        .kind.sustainability {
          color: var(--cat-unknown);
        }
        .confidence {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
        }
        .confidence.high {
          color: var(--status-done);
        }
        .confidence.low {
          color: var(--status-backlog);
        }
        .saving {
          margin-left: auto;
          display: inline-flex;
          align-items: baseline;
          gap: 4px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 13px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }
        /* The qualifier rides with the number everywhere it appears, not
           only inside the expanded panel. */
        .proj {
          font-size: 8.5px;
          color: var(--text-dim);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .chevron {
          display: inline-flex;
          color: var(--text-dim);
          transition: transform 0.12s ease;
        }
        .chevron.up {
          transform: rotate(180deg);
          color: var(--text-primary);
        }
        h3 {
          font-size: 13.5px;
          font-weight: 510;
          line-height: 18px;
          color: var(--text-primary);
        }
        .summary {
          font-size: 11.5px;
          line-height: 16px;
          color: var(--text-muted);
        }
        .action {
          display: flex;
          gap: 6px;
          font-size: 11.5px;
          line-height: 16px;
          color: var(--text-secondary);
          padding: 6px 8px;
          background: var(--overlay-02);
          border-radius: 3px;
        }
        .arrow {
          color: var(--primary);
          flex-shrink: 0;
        }
        .peek {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
        }
        .body {
          padding: 0 13px 13px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .provenance {
          display: flex;
          flex-direction: column;
          gap: 5px;
          padding: 9px 10px;
          background: var(--bg-card);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          font-size: 10.5px;
          line-height: 15px;
          color: var(--text-muted);
        }
        .provenance b {
          color: var(--text-secondary);
          font-weight: 510;
        }
        .caveat {
          color: var(--text-dim);
        }
      `}</style>
    </article>
  );
}
