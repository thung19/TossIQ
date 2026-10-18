"use client";

import type { FillSource } from "../../lib/api";

/**
 * Fill percentage with a visually distinct treatment for the two ways TossIQ
 * can know it.
 *
 * There are no weight sensors, so fill is never measured. An "observed" value
 * is counted from the disposal events attributed to the can since it was last
 * emptied -- real data, drawn solid. A "simulated" value belongs to a can that
 * does not physically exist and is drawn hatched, so a glance at the map never
 * mistakes the mock fleet for reporting hardware. Any other source means the
 * can has no fill signal, which is drawn as an empty track labelled as such
 * rather than as a 0% reading.
 */
export default function FillBar({
  percent,
  source,
  threshold,
  showLabel = true,
}: {
  percent: number | null;
  source: FillSource;
  threshold?: number;
  showLabel?: boolean;
}) {
  const known = percent != null && (source === "observed" || source === "simulated");
  const clamped = known ? Math.max(0, Math.min(100, percent)) : 0;
  const over = known && threshold != null && clamped >= threshold;

  return (
    <div className="fill">
      <div className="track">
        <div
          className={`bar ${source === "simulated" ? "simulated" : "observed"} ${over ? "over" : ""}`}
          style={{ width: `${clamped}%` }}
        />
        {threshold != null && <div className="threshold" style={{ left: `${threshold}%` }} />}
      </div>
      {showLabel && (
        <div className="meta">
          <span className="pct">{known ? `${clamped.toFixed(0)}%` : "—"}</span>
          <span className="src">
            {source === "observed" || source === "simulated" ? source : "no fill signal"}
          </span>
        </div>
      )}

      <style jsx>{`
        .fill {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
        }
        .track {
          position: relative;
          height: 6px;
          background: var(--overlay-05);
          border-radius: 3px;
          overflow: hidden;
        }
        .bar {
          height: 100%;
          border-radius: 3px;
          transition: width 0.3s ease;
        }
        .bar.observed {
          background: var(--status-done);
        }
        .bar.observed.over {
          background: var(--status-in-progress);
        }
        /* Hatched rather than solid: a simulated number is not an observation. */
        .bar.simulated {
          background: repeating-linear-gradient(
            135deg,
            var(--status-done) 0px,
            var(--status-done) 3px,
            transparent 3px,
            transparent 6px
          );
        }
        .bar.simulated.over {
          background: repeating-linear-gradient(
            135deg,
            var(--status-in-progress) 0px,
            var(--status-in-progress) 3px,
            transparent 3px,
            transparent 6px
          );
        }
        .threshold {
          position: absolute;
          top: 0;
          bottom: 0;
          width: 1px;
          background: var(--border-solid);
        }
        .meta {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 8px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .pct {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .src {
          color: var(--text-dim);
        }
      `}</style>
    </div>
  );
}
