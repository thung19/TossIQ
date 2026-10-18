"use client";

import BarList from "./BarList";
import { formatMeasure, type AnalyticsHotspots, type BinComposition, type Measure } from "../../lib/api";

/**
 * Where the waste is, and what is in each bin.
 *
 * The three hotspot lists share one scale bound, taken from the busiest
 * building, so a glance across them compares like with like instead of three
 * independently normalised charts that each look equally full.
 */
export default function HotspotPanel({
  hotspots,
  bins,
  measure,
  onSelectCan,
}: {
  hotspots: AnalyticsHotspots | null;
  bins: BinComposition[] | null;
  measure: Measure;
  onSelectCan?: (canCode: string) => void;
}) {
  return (
    <div className="wrap">
      <div className="col">
        <Panel title="by building" meta={`${hotspots?.by_building.length ?? 0} with activity`}>
          <BarList rows={hotspots?.by_building ?? []} measure={measure} maxRows={15} />
        </Panel>
        <Panel title="by campus area" meta="">
          <BarList rows={hotspots?.by_campus_area ?? []} measure={measure} />
        </Panel>
        <Panel title="by can" meta="busiest 15">
          <BarList
            rows={hotspots?.by_can ?? []}
            measure={measure}
            maxRows={15}
            onSelect={onSelectCan}
          />
        </Panel>
      </div>

      <Panel
        title="what is usually in each bin"
        meta={bins ? `${bins.length} can${bins.length === 1 ? "" : "s"}` : "loading…"}
        scroll
      >
        {!bins ? (
          <div className="empty">loading…</div>
        ) : bins.length === 0 ? (
          <div className="empty">no disposals attributed to a can in this scope</div>
        ) : (
          <div className="bins">
            {bins.map((can) => (
              <article key={can.can_id} className="can">
                <header className="canhead">
                  <button className="code" onClick={() => onSelectCan?.(can.can_code)}>
                    {can.can_code}
                  </button>
                  <span className="where">{can.building_name ?? "-"}</span>
                  <span className="total">{can.shown_items.toLocaleString()}</span>
                </header>
                <ul>
                  {can.items.map((item) => (
                    <li key={item.item}>
                      <span className={`dot ${item.category}`} />
                      <span className="item">{item.item}</span>
                      <span className="count">{item.count}</span>
                      <span className="cost">
                        {item.estimated_cost > 0
                          ? formatMeasure(item.estimated_cost, "cost")
                          : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <style jsx>{`
        .wrap {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 10px;
          align-items: start;
        }
        .col {
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-width: 0;
        }
        .empty {
          padding: 16px 10px;
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .bins {
          display: flex;
          flex-direction: column;
        }
        .can {
          border-bottom: 1px solid var(--border-05);
          padding: 6px 10px 7px;
        }
        .canhead {
          display: flex;
          align-items: baseline;
          gap: 7px;
          margin-bottom: 3px;
        }
        .code {
          color: var(--mention-text);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          font-weight: 510;
        }
        .code:hover {
          text-decoration: underline;
        }
        .where {
          color: var(--text-dim);
          font-size: 10px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .total {
          margin-left: auto;
          color: var(--text-primary);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          font-variant-numeric: tabular-nums;
        }
        ul {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 1px;
        }
        li {
          display: grid;
          grid-template-columns: 7px minmax(0, 1fr) 36px 54px;
          align-items: center;
          gap: 6px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--cat-unknown);
        }
        .dot.recycling {
          background: var(--cat-recycling);
        }
        .dot.compost {
          background: var(--cat-compost);
        }
        .dot.landfill {
          background: var(--cat-landfill);
        }
        .item {
          color: var(--text-secondary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .count,
        .cost {
          text-align: right;
          font-variant-numeric: tabular-nums;
          color: var(--text-muted);
        }
        .cost {
          color: var(--text-dim);
          font-size: 10px;
        }
        @media (max-width: 1240px) {
          .wrap {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}

function Panel({
  title,
  meta,
  scroll,
  children,
}: {
  title: string;
  meta?: string;
  scroll?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <header>
        <span className="title">{title}</span>
        <span className="spacer" />
        {meta && <span className="meta">{meta}</span>}
      </header>
      <div className={scroll ? "body scroll" : "body"}>{children}</div>
      <style jsx>{`
        .panel {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          min-width: 0;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          font-size: 11px;
        }
        .title {
          color: var(--text-primary);
          font-weight: 510;
        }
        .spacer {
          flex: 1;
        }
        .meta {
          color: var(--text-dim);
          font-size: 10px;
        }
        .body {
          padding: 4px 0 6px;
          min-width: 0;
        }
        .body.scroll {
          max-height: 720px;
          overflow-y: auto;
          padding: 0;
        }
      `}</style>
    </section>
  );
}
