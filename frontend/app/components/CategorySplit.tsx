"use client";

import { CategoryDot, CATEGORY_COLOR } from "./CategoryDot";

type Row = { category: string; count: number };

export default function CategorySplit({
  rows,
  totalLabel = "items",
}: {
  rows: Row[];
  totalLabel?: string;
}) {
  const total = rows.reduce((acc, r) => acc + r.count, 0) || 1;
  const sorted = [...rows].sort((a, b) => b.count - a.count);

  return (
    <section className="card">
      <header>
        <span className="title">categories</span>
        <span className="meta">
          <span className="n">{total}</span>
          <span className="l">{totalLabel}</span>
        </span>
      </header>

      <div className="rows">
        {sorted.length === 0 && <div className="empty">no detections</div>}
        {sorted.map((r) => {
          const pct = (r.count / total) * 100;
          const color = CATEGORY_COLOR[r.category] || "var(--cat-unknown)";
          return (
            <div key={r.category} className="row">
              <CategoryDot category={r.category} size={5} />
              <span className="name">{r.category || "unknown"}</span>
              <div className="bar"><div className="fill" style={{ width: `${pct}%`, background: color }} /></div>
              <span className="pct">{pct.toFixed(0)}%</span>
              <span className="count">{r.count}</span>
            </div>
          );
        })}
      </div>

      <style jsx>{`
        .card {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          display: flex;
          align-items: baseline;
          justify-content: space-between;
        }
        .title {
          font-size: 11px;
          color: var(--text-dim);
        }
        .meta {
          display: inline-flex;
          align-items: baseline;
          gap: 4px;
          font-size: 11px;
        }
        .meta .n {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .meta .l {
          color: var(--text-dim);
        }
        .rows {
          padding: 6px 10px 8px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .empty {
          padding: 8px 0;
          color: var(--text-dim);
          font-size: 11px;
        }
        .row {
          display: grid;
          grid-template-columns: 5px 1fr 100px 36px 36px;
          align-items: center;
          column-gap: 8px;
          font-size: 11.5px;
          padding: 2px 0;
        }
        .name {
          color: var(--text-secondary);
          text-transform: lowercase;
        }
        .bar {
          height: 2px;
          background: var(--overlay-05);
          overflow: hidden;
        }
        .fill {
          height: 100%;
          transition: width 0.3s ease;
        }
        .pct {
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
          text-align: right;
        }
        .count {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          text-align: right;
          font-weight: 510;
        }
      `}</style>
    </section>
  );
}
