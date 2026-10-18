"use client";

import { CategoryDot } from "./CategoryDot";
import type { WasteEvent } from "../../lib/api";

export default function EventFilmstrip({ events }: { events: WasteEvent[] }) {
  const list = events.slice(0, 50);

  return (
    <section className="table">
      <header>
        <span className="title">events</span>
        <span className="meta">{events.length} · 24h</span>
      </header>

      <div className="col-head">
        <span className="h id">id</span>
        <span className="h dot" />
        <span className="h item">item</span>
        <span className="h cat">category</span>
        <span className="h num conf">conf</span>
        <span className="h loc">location</span>
        <span className="h num time">time</span>
      </div>

      {list.length === 0 ? (
        <div className="empty">no events</div>
      ) : (
        <div className="rows">
          {list.map((e) => (
            <div key={e.event_id} className="row">
              <span className="c id">{e.event_id.toString().padStart(4, "0")}</span>
              <span className="c dot"><CategoryDot category={e.category || "unknown"} size={5} /></span>
              <span className="c item">{e.detected_object || "unknown"}</span>
              <span className="c cat">{e.category || "unknown"}</span>
              <span className="c num conf">{formatConf(e.confidence)}</span>
              <span className="c loc">{e.location || "-"}</span>
              <span className="c num time">{shortTime(e.created_at)}</span>
            </div>
          ))}
        </div>
      )}

      <style jsx>{`
        .table {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          padding: 7px 12px;
          border-bottom: 1px solid var(--border-05);
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          font-size: 11px;
        }
        .title {
          color: var(--text-dim);
        }
        .meta {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .col-head,
        .row {
          display: grid;
          grid-template-columns: 50px 10px minmax(0, 1.3fr) 90px 60px minmax(0, 1fr) 70px;
          align-items: center;
          gap: 12px;
          padding: 4px 12px;
          font-size: 11.5px;
        }
        .col-head {
          color: var(--text-dim);
          padding-top: 5px;
          padding-bottom: 5px;
          border-bottom: 1px solid var(--border-05);
          font-size: 10.5px;
        }
        .h {
          text-transform: lowercase;
          font-weight: 400;
        }
        .row {
          border-bottom: 1px solid var(--border-05);
          color: var(--text-secondary);
        }
        .row:last-child {
          border-bottom: none;
        }
        .row:hover {
          background: var(--overlay-02);
        }
        .num {
          font-variant-numeric: tabular-nums;
          text-align: right;
        }
        .c.id {
          color: var(--text-dim);
        }
        .c.item {
          color: var(--text-primary);
          font-weight: 510;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .c.cat {
          color: var(--text-muted);
          text-transform: lowercase;
        }
        .c.conf {
          color: var(--text-secondary);
        }
        .c.loc {
          color: var(--text-dim);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .c.time {
          color: var(--text-dim);
        }
        .empty {
          padding: 10px 12px;
          color: var(--text-dim);
          font-size: 11px;
        }
      `}</style>
    </section>
  );
}

function formatConf(c: number | null): string {
  if (c == null) return "-";
  const v = c > 1 ? c : c * 100;
  return `${v.toFixed(0)}%`;
}

function shortTime(iso: string | null): string {
  if (!iso) return "-";
  const parts = iso.split(" ");
  return parts.length === 2 ? parts[1].slice(0, 8) : iso.slice(-8);
}
