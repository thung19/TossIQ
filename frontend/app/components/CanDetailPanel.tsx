"use client";

import { useEffect, useState } from "react";
import CategorySplit from "./CategorySplit";
import CodeChip from "./CodeChip";
import EventFilmstrip from "./EventFilmstrip";
import FillBar from "./FillBar";
import StatCard from "./StatCard";
import { CategoryDot } from "./CategoryDot";
import { apiFetch, apiPost, type CanContents, type CanDetail } from "../../lib/api";

const STATUS_LABEL: Record<string, string> = {
  ok: "ok",
  needs_service: "needs service",
  fault: "hardware fault",
  offline: "offline",
};

/**
 * Right-hand slide-over for one can: hardware version and capacity, why it has
 * the status it has, what it currently contains, its telemetry tail and its
 * service history -- plus the action that resolves a service need.
 *
 * Reuses the existing StatCard / CategorySplit / EventFilmstrip / CodeChip /
 * CategoryDot components rather than restyling equivalents, so a can's
 * contents read the same way as the live sorting page's event feed.
 */
export default function CanDetailPanel({
  canId,
  serviceThreshold,
  onClose,
  onServiced,
}: {
  canId: number;
  serviceThreshold: number | undefined;
  onClose: () => void;
  onServiced: () => void;
}) {
  const [can, setCan] = useState<CanDetail | null>(null);
  const [contents, setContents] = useState<CanContents | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const [detail, canContents] = await Promise.all([
          apiFetch<CanDetail>(`/cans/${canId}`),
          apiFetch<CanContents>(`/cans/${canId}/contents`),
        ]);
        if (!alive) return;
        setCan(detail);
        setContents(canContents);
      } catch {
        /* backend may be booting; the loop will retry */
      }
    };
    setCan(null);
    setContents(null);
    refresh();
    const id = setInterval(refresh, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [canId]);

  const recordService = async (serviceType: string) => {
    setBusy(true);
    setActionError(null);
    try {
      await apiPost(`/cans/${canId}/service`, {
        service_type: serviceType,
        performed_by: "dashboard operator",
        notes: null,
      });
      const [detail, canContents] = await Promise.all([
        apiFetch<CanDetail>(`/cans/${canId}`),
        apiFetch<CanContents>(`/cans/${canId}/contents`),
      ]);
      setCan(detail);
      setContents(canContents);
      onServiced();
    } catch {
      setActionError("Could not record the service event.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="panel">
      <header>
        <div className="title-row">
          <span className={`dot ${can?.status ?? "offline"}`} />
          <span className="code">{can?.can_code ?? "loading…"}</span>
          {can && <span className="status">{STATUS_LABEL[can.status]}</span>}
        </div>
        <button className="close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>

      {!can ? (
        <div className="empty">loading can…</div>
      ) : (
        <div className="body">
          <section className="block">
            <div className="where">
              {can.building_name}
              {can.floor ? ` · floor ${can.floor}` : ""}
              {can.placement_note ? ` · ${can.placement_note}` : ""}
            </div>
            <div className="chips">
              <CodeChip>{can.model_code}</CodeChip>
              <CodeChip>fw {can.firmware_version ?? "—"}</CodeChip>
              <CodeChip>{can.stream_count ?? "?"}-stream</CodeChip>
              {can.is_simulated ? <CodeChip>simulated</CodeChip> : <CodeChip>live unit</CodeChip>}
            </div>
          </section>

          <section className="block">
            <span className="block-label">fill</span>
            <FillBar
              percent={can.fill_percent}
              source={can.fill_source}
              threshold={serviceThreshold}
            />
            <p className="note">
              {can.fill_source === "observed"
                ? `Counted from ${can.events_since_emptied} item${
                    can.events_since_emptied === 1 ? "" : "s"
                  } logged since this can was last emptied, against a ${can.capacity_items}-item capacity. There are no weight sensors, so this is a count, not a measured weight.`
                : can.fill_source === "simulated"
                  ? "Simulated value for a can that does not physically exist. Not an observation."
                  : "No fill signal for this can."}
            </p>
          </section>

          {can.status_reasons.length > 0 && (
            <section className="block">
              <span className="block-label">why</span>
              <ul className="reasons">
                {can.status_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="kpis">
            <StatCard label="capacity" value={can.capacity_liters ?? "—"} suffix="L" />
            <StatCard label="items cap" value={can.capacity_items} />
            <StatCard label="battery" value={can.battery_percent ?? "—"} suffix="%" />
            <StatCard label="camera" value={can.camera_ok === 0 ? "down" : "ok"} />
            <StatCard label="actuator" value={can.has_actuator === 0 ? "none" : can.actuator_ok === 0 ? "down" : "ok"} />
            <StatCard label="in can" value={contents?.total_items ?? "—"} />
          </section>

          <section className="block">
            <span className="block-label">actions</span>
            <div className="actions">
              <button disabled={busy} onClick={() => recordService("emptied")}>
                record emptied
              </button>
              <button disabled={busy} onClick={() => recordService("inspected")}>
                record inspected
              </button>
              <button disabled={busy} onClick={() => recordService("repaired")}>
                record repaired
              </button>
            </div>
            {actionError && <p className="error">{actionError}</p>}
            <p className="note">
              {can.fill_source === "observed"
                ? "Recording an emptying moves the derived-fill window forward, so this can's counted fill resets to 0%."
                : "This can's fill is a seeded value, not a count, so emptying it is recorded in the service history but does not move the fill number."}{" "}
              A hardware fault clears only when the unit itself reports healthy telemetry again,
              not when a repair is logged.
            </p>
          </section>

          {contents && (
            <section className="block">
              <span className="block-label">contents</span>
              <CategorySplit
                rows={contents.by_category}
                totalLabel={contents.since ? "items since emptied" : `items (${contents.window_days}d)`}
              />
              {contents.estimated_value != null && (
                <p className="note">
                  Estimated ${contents.estimated_value.toFixed(2)} of catalog-priced items in this
                  can, from matched PRODUCTS unit costs. An estimate over matched items only, not a
                  total value of the contents.
                </p>
              )}
            </section>
          )}

          {contents && contents.top_items.length > 0 && (
            <section className="block">
              <span className="block-label">top items</span>
              <div className="items">
                {contents.top_items.map((item) => (
                  <div key={`${item.detected_object}-${item.matched_product}`} className="item">
                    <span className="name">{item.detected_object}</span>
                    {item.matched_product && <span className="matched">{item.matched_product}</span>}
                    <span className="count">{item.count}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="block">
            <span className="block-label">fill history</span>
            <ReadingSparkline can={can} />
          </section>

          <section className="block">
            <span className="block-label">service history</span>
            <div className="history">
              {can.service_events.length === 0 && <div className="empty-row">no service recorded</div>}
              {can.service_events.map((event) => (
                <div key={event.service_id} className="history-row">
                  <span className="type">{event.service_type}</span>
                  <span className="when">{event.performed_at ?? "—"}</span>
                  <span className="who">{event.performed_by ?? "—"}</span>
                </div>
              ))}
            </div>
          </section>

          {contents && contents.events.length > 0 && (
            <section className="block">
              <span className="block-label">recent disposals</span>
              <EventFilmstrip events={contents.events} />
            </section>
          )}

          <section className="block">
            <span className="block-label">position</span>
            <div className="coords">
              <CategoryDot category={null} size={5} />
              <span>
                {can.latitude?.toFixed(6)}, {can.longitude?.toFixed(6)}
              </span>
            </div>
            <p className="note">
              Coordinates are approximate placements around the building, not surveyed positions.
            </p>
          </section>
        </div>
      )}

      <style jsx>{`
        .panel {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          min-width: 0;
          overflow: hidden;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          padding: 8px 10px;
          border-bottom: 1px solid var(--border-05);
          flex-shrink: 0;
        }
        .title-row {
          display: flex;
          align-items: center;
          gap: 7px;
          min-width: 0;
        }
        .dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .dot.ok {
          background: var(--status-done);
        }
        .dot.needs_service {
          background: var(--status-in-progress);
        }
        .dot.fault {
          background: var(--status-bug);
        }
        .dot.offline {
          background: var(--status-backlog);
        }
        .code {
          font-size: 12.5px;
          font-weight: 510;
          color: var(--text-primary);
        }
        .status {
          font-size: 10.5px;
          color: var(--text-dim);
        }
        .close {
          color: var(--text-dim);
          font-size: 12px;
          padding: 2px 4px;
        }
        .close:hover {
          color: var(--text-primary);
        }
        .body {
          overflow-y: auto;
          padding: 10px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          min-width: 0;
        }
        .empty {
          padding: 16px 10px;
          color: var(--text-dim);
          font-size: 11px;
        }
        .block {
          display: flex;
          flex-direction: column;
          gap: 6px;
          min-width: 0;
        }
        .block-label {
          font-size: 10px;
          color: var(--text-dim);
        }
        .where {
          font-size: 11.5px;
          color: var(--text-secondary);
          line-height: 16px;
        }
        .chips {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
        }
        .note {
          font-size: 10.5px;
          color: var(--text-dim);
          line-height: 15px;
        }
        .error {
          font-size: 10.5px;
          color: var(--status-bug);
        }
        .reasons {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .reasons li {
          font-size: 11px;
          color: var(--text-secondary);
          line-height: 15px;
          padding-left: 9px;
          position: relative;
        }
        .reasons li::before {
          content: "";
          position: absolute;
          left: 0;
          top: 6px;
          width: 3px;
          height: 3px;
          border-radius: 50%;
          background: var(--text-dim);
        }
        .kpis {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 5px;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 5px;
        }
        .actions button {
          font-family: inherit;
          font-size: 11px;
          color: var(--text-secondary);
          background: var(--overlay-02);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          padding: 4px 8px;
        }
        .actions button:hover:not(:disabled) {
          background: var(--overlay-08);
          color: var(--text-primary);
        }
        .actions button:disabled {
          color: var(--text-dim);
          cursor: default;
        }
        .items {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .item {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, auto) 34px;
          align-items: baseline;
          gap: 8px;
          font-size: 11px;
          padding: 2px 0;
          border-bottom: 1px solid var(--border-05);
        }
        .item .name {
          color: var(--text-primary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .item .matched {
          color: var(--mention-text);
          font-size: 10px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .item .count {
          color: var(--text-secondary);
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .history {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .history-row {
          display: grid;
          grid-template-columns: 90px minmax(0, 1fr) minmax(0, 1fr);
          gap: 8px;
          font-size: 10.5px;
          padding: 2px 0;
          border-bottom: 1px solid var(--border-05);
        }
        .history-row .type {
          color: var(--text-primary);
        }
        .history-row .when,
        .history-row .who {
          color: var(--text-dim);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .empty-row {
          font-size: 10.5px;
          color: var(--text-dim);
        }
        .coords {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }
      `}</style>
    </aside>
  );
}

/**
 * Fill over time from the can's reading tail.
 *
 * Hand-drawn SVG rather than a charting dependency: it is one polyline, and
 * the existing ThroughputChart sets the precedent of a small inline chart in
 * the palette. A real reporting can has no fill history to draw -- its
 * hardware cannot measure fullness -- and says so rather than drawing a flat
 * line that looks like data.
 */
function ReadingSparkline({ can }: { can: CanDetail }) {
  const points = can.readings
    .filter((r) => r.fill_percent != null && r.reported_at)
    .slice()
    .reverse();

  if (points.length < 2) {
    return (
      <>
        <p className="sparkline-empty">
          {can.fill_source === "observed"
            ? "This unit reports hardware health but not fullness, so there is no measured fill history to chart. Its fill is counted from disposal events instead."
            : "Not enough readings to chart."}
        </p>
        <style jsx>{`
          .sparkline-empty {
            font-size: 10.5px;
            color: var(--text-dim);
            line-height: 15px;
          }
        `}</style>
      </>
    );
  }

  const width = 100;
  const height = 28;
  const path = points
    .map((reading, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - (Math.max(0, Math.min(100, reading.fill_percent as number)) / 100) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="sparkline">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
        <path d={path} fill="none" stroke="var(--status-done)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="axis">
        <span>{points[0].reported_at?.slice(5, 10)}</span>
        <span>{points.length} readings</span>
        <span>{points[points.length - 1].reported_at?.slice(5, 10)}</span>
      </div>

      <style jsx>{`
        .sparkline {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        svg {
          width: 100%;
          height: 34px;
          background: var(--overlay-02);
          border: 1px solid var(--border-05);
          border-radius: 3px;
        }
        .axis {
          display: flex;
          justify-content: space-between;
          font-size: 10px;
          color: var(--text-dim);
        }
      `}</style>
    </div>
  );
}
