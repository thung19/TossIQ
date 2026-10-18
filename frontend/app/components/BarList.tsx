"use client";

import { formatMeasure, measureValue, type Bucket, type Measure } from "../../lib/api";

/**
 * A ranked horizontal bar list: the workhorse of the analytics page.
 *
 * A bar list rather than a pie or a donut, for every distribution on this
 * page. These breakdowns routinely run to twenty or forty buckets with a long
 * tail, and a pie of forty slices is unreadable at any size -- you cannot
 * compare two adjacent wedges, and the labels do not fit. Ranked bars sharing
 * one baseline make the ordering and the ratios directly legible, and the
 * long tail simply continues down the list.
 *
 * `matched_count` drives the hatched remainder on cost and mass bars: the
 * portion of a bar that rests on a class average rather than a specific
 * product match is drawn differently, so an estimate built on thin evidence
 * looks different from one built on a real match.
 */
export default function BarList({
  rows,
  measure,
  max,
  selected,
  onSelect,
  emptyLabel = "nothing in this scope",
  maxRows,
}: {
  rows: Bucket[];
  measure: Measure;
  /** Scale bound. Defaults to the largest row; pass it to hold the scale
   * steady while a filter narrows the data. */
  max?: number;
  selected?: string | null;
  onSelect?: (bucket: string) => void;
  emptyLabel?: string;
  maxRows?: number;
}) {
  const shown = maxRows ? rows.slice(0, maxRows) : rows;
  const bound = max ?? Math.max(1, ...shown.map((row) => measureValue(row, measure)));

  if (shown.length === 0) {
    return (
      <div className="empty">
        {emptyLabel}
        <style jsx>{`
          .empty {
            padding: 14px 12px;
            color: var(--text-dim);
            font-family: ui-monospace, Menlo, monospace;
            font-size: 11px;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="list">
      {shown.map((row) => {
        const value = measureValue(row, measure);
        const width = bound > 0 ? Math.max(1, (value / bound) * 100) : 0;
        // On a cost or mass bar, the share of the figure that came from a
        // specific product rather than a class average.
        const confident =
          measure === "count" || row.count === 0 ? 1 : row.matched_count / row.count;
        const isSelected = selected === row.bucket;
        const Row = onSelect ? "button" : "div";

        return (
          <Row
            key={row.bucket}
            className={`row ${isSelected ? "on" : ""} ${onSelect ? "clickable" : ""}`}
            onClick={onSelect ? () => onSelect(row.bucket) : undefined}
            title={
              measure === "count"
                ? `${row.bucket}, ${row.count} items`
                : `${row.bucket}, ${formatMeasure(value, measure)} across ${row.count} items; ` +
                  `${row.matched_count} matched to a specific product`
            }
          >
            <span className="label">{row.bucket}</span>
            <span className="track">
              <span className="bar" style={{ width: `${width}%` }}>
                <span className="solid" style={{ width: `${confident * 100}%` }} />
              </span>
            </span>
            <span className="value">{formatMeasure(value, measure)}</span>
            <span className="share">
              {row.share != null ? `${row.share.toFixed(1)}%` : ""}
            </span>
          </Row>
        );
      })}

      <style jsx>{`
        .list {
          display: flex;
          flex-direction: column;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .row {
          display: grid;
          grid-template-columns: minmax(90px, 1.5fr) minmax(0, 3fr) 76px 44px;
          align-items: center;
          gap: 8px;
          padding: 3px 10px;
          text-align: left;
          font-family: inherit;
          font-size: inherit;
          width: 100%;
          border: 1px solid transparent;
          border-radius: 2px;
        }
        .row.clickable:hover {
          background: var(--overlay-02);
        }
        .row.on {
          background: var(--overlay-05);
          border-color: var(--border-08);
        }
        .label {
          color: var(--text-secondary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .row.on .label {
          color: var(--text-primary);
        }
        .track {
          min-width: 0;
          height: 11px;
          background: var(--overlay-02);
          border-radius: 2px;
          overflow: hidden;
        }
        .bar {
          display: block;
          height: 100%;
          border-radius: 2px;
          /* The hatched ground shows through wherever the solid portion ends:
             that remainder is the part of this figure carried by a class
             average rather than a matched product. */
          background: repeating-linear-gradient(
            135deg,
            var(--primary) 0px,
            var(--primary) 2px,
            transparent 2px,
            transparent 5px
          );
        }
        .solid {
          display: block;
          height: 100%;
          background: var(--primary);
          border-radius: 2px;
        }
        .value {
          color: var(--text-primary);
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .share {
          color: var(--text-dim);
          text-align: right;
          font-variant-numeric: tabular-nums;
          font-size: 10px;
        }
      `}</style>
    </div>
  );
}
