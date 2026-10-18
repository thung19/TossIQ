"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import {
  SEVERITY_RANK,
  apiFetch,
  apiPost,
  type HazardEvent,
  type HazardSeverity,
  type HazardSummary,
} from "../../lib/api";

/**
 * Hazardous disposals: what was thrown away that should not have been,
 * where, and what to do about it.
 *
 * The page opens on outstanding work rather than the archive, worst first.
 * Severity here is about RESPONSE TIME -- critical means it can start a
 * fire in a compacted load or injure whoever reaches into the bag -- so the
 * ordering is an operational one, not a ranking of how unpleasant things
 * are.
 *
 * Two alert shapes, because they need different responses. An overdue item
 * is one hazard nobody has collected inside its window: somebody goes and
 * gets it. A recurrence is the same hazard arriving in the same building
 * over and over: collecting each one will not stop the next, and that
 * building needs a collection point.
 */

const WINDOWS = [7, 30, 90];
const SEVERITIES: HazardSeverity[] = ["critical", "high", "medium", "unclassified"];

// Who the demo acknowledges as. Real sign-in would supply this; until then
// it is a named placeholder rather than a blank field, so the audit trail
// is at least consistent.
const ACKNOWLEDGED_BY = "facilities-ops@vanderbilt.edu";

export default function HazardsPage() {
  const [summary, setSummary] = useState<HazardSummary | null>(null);
  const [events, setEvents] = useState<HazardEvent[]>([]);
  const [days, setDays] = useState(30);
  const [severity, setSeverity] = useState<HazardSeverity | "all">("all");
  const [outstandingOnly, setOutstandingOnly] = useState(true);
  const [openId, setOpenId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const query = useMemo(() => {
    const params = new URLSearchParams({ days: String(days), limit: "200" });
    if (severity !== "all") params.set("severity", severity);
    if (outstandingOnly) params.set("outstanding_only", "true");
    return params.toString();
  }, [days, severity, outstandingOnly]);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const [list, totals] = await Promise.all([
          apiFetch<HazardEvent[]>(`/hazards?${query}`),
          apiFetch<HazardSummary>(`/hazards/summary?days=${days}`),
        ]);
        if (!alive) return;
        setEvents(list);
        setSummary(totals);
        setError(null);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "request failed");
        retry = setTimeout(load, 4000);
      }
    };
    load();
    return () => {
      alive = false;
      if (retry) clearTimeout(retry);
    };
  }, [query, days, refreshToken]);

  const acknowledge = useCallback(async (event: HazardEvent) => {
    setBusyId(event.event_id);
    try {
      await apiPost(`/hazards/${event.event_id}/acknowledge`, {
        acknowledged_by: ACKNOWLEDGED_BY,
        note: "Collected and routed to the hazardous waste contractor.",
      });
      setRefreshToken((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not acknowledge");
    } finally {
      setBusyId(null);
    }
  }, []);

  const criticalOutstanding =
    summary?.by_severity.find((row) => row.severity === "critical")?.outstanding ?? 0;

  return (
    <>
      <PageHeader
        breadcrumb="Safety"
        title="Hazards"
        right={
          <span className="header-meta">
            {summary ? (
              <>
                <span className={summary.outstanding > 0 ? "alarm" : ""}>
                  {summary.outstanding} outstanding
                </span>
                <span className="dim">· {summary.total} flagged in {days}d</span>
              </>
            ) : (
              <span className="dim">{error ? "unavailable, retrying" : "loading…"}</span>
            )}
          </span>
        }
      />

      <div className="page">
        <section className="kpis">
          <StatCard
            label="critical outstanding"
            value={criticalOutstanding}
            delta={criticalOutstanding > 0 ? "fire or injury risk" : "none open"}
          />
          <StatCard label="all outstanding" value={summary?.outstanding ?? "-"} />
          <StatCard
            label="past response window"
            value={summary?.overdue.length ?? "-"}
            delta="unacknowledged too long"
          />
          <StatCard
            label="recurring locations"
            value={summary?.recurring.length ?? "-"}
            delta="same hazard, same building"
          />
          <StatCard label="flagged total" value={summary?.total ?? "-"} suffix="" />
        </section>

        {summary && (summary.overdue.length > 0 || summary.recurring.length > 0) && (
          <section className="alerts">
            {summary.overdue.slice(0, 4).map((item) => (
              <article key={`overdue-${item.event_id}`} className={`alert ${item.severity}`}>
                <span className="alert-kind">past response window</span>
                <span className="alert-title">
                  {item.display_name} in {item.building_name ?? "an unattributed bin"}
                </span>
                <span className="alert-detail">
                  {item.can_code ? `${item.can_code} · ` : ""}
                  logged {item.hours_open.toFixed(0)}h ago, {item.hours_overdue.toFixed(0)}h past
                  the {item.response_hours}h window for {item.severity} hazards
                </span>
              </article>
            ))}
            {summary.recurring.slice(0, 3).map((item) => (
              <article
                key={`recur-${item.building_name}-${item.hazard_class}`}
                className={`alert recurring ${item.severity}`}
              >
                <span className="alert-kind">recurring</span>
                <span className="alert-title">
                  {item.display_name} × {item.count} at {item.building_name}
                </span>
                <span className="alert-detail">
                  across {item.cans} can{item.cans === 1 ? "" : "s"}. Collecting each one will
                  not stop the next, this building needs a collection point or signage.
                </span>
              </article>
            ))}
          </section>
        )}

        <section className="controls">
          <span className="k">window</span>
          {WINDOWS.map((option) => (
            <button
              key={option}
              className={`chip ${days === option ? "on" : ""}`}
              onClick={() => setDays(option)}
            >
              {option}d
            </button>
          ))}
          <span className="divider" />
          <button
            className={`chip ${severity === "all" ? "on" : ""}`}
            onClick={() => setSeverity("all")}
          >
            all
          </button>
          {SEVERITIES.map((option) => {
            const row = summary?.by_severity.find((entry) => entry.severity === option);
            if (!row) return null;
            return (
              <button
                key={option}
                className={`chip sev-${option} ${severity === option ? "on" : ""}`}
                onClick={() => setSeverity(option)}
              >
                {option} {row.count}
              </button>
            );
          })}
          <span className="divider" />
          <button
            className={`chip ${outstandingOnly ? "on" : ""}`}
            onClick={() => setOutstandingOnly((value) => !value)}
          >
            {outstandingOnly ? "outstanding only" : "including handled"}
          </button>
          <span className="spacer" />
          {error && <span className="err">{error}</span>}
        </section>

        <section className="grid">
          <div className="list">
            {events.length === 0 ? (
              <p className="empty">
                {outstandingOnly
                  ? "Nothing hazardous is outstanding in this window. Switch to “including handled” to see what has been dealt with."
                  : "No hazardous disposals were flagged in this window."}
              </p>
            ) : (
              events.map((event) => {
                const open = openId === event.event_id;
                return (
                  <article
                    key={event.event_id}
                    className={`row ${event.hazard_severity ?? "unclassified"} ${
                      event.acknowledged_at ? "done" : ""
                    } ${open ? "open" : ""}`}
                  >
                    <button
                      className="row-head"
                      onClick={() => setOpenId(open ? null : event.event_id)}
                    >
                      <span className={`sev ${event.hazard_severity ?? "unclassified"}`}>
                        {event.hazard_severity ?? "unclassified"}
                      </span>
                      <span className="what">
                        <span className="name">{event.display_name}</span>
                        <span className="object">{event.detected_object ?? "unidentified"}</span>
                      </span>
                      <span className="where">
                        <span className="building">{event.building_name ?? "unattributed"}</span>
                        <span className="spot">
                          {event.can_code ?? event.location ?? "-"}
                          {event.placement_note ? ` · ${event.placement_note}` : ""}
                        </span>
                      </span>
                      <span className="when">{event.created_at ?? "-"}</span>
                      <span className="state">
                        {event.acknowledged_at ? (
                          <span className="ok">handled</span>
                        ) : (
                          <span className="open-tag">open</span>
                        )}
                      </span>
                    </button>

                    {open && (
                      <div className="detail">
                        <p className="reason">
                          <b>What the camera saw.</b>{" "}
                          {event.hazard_reason ?? "No description recorded."}
                          {event.confidence != null && (
                            <span className="dim"> ({event.confidence.toFixed(0)}% confidence)</span>
                          )}
                        </p>
                        <p className="handling">
                          <b>Handling.</b> {event.handling}
                        </p>
                        <p className="dim">
                          Response window for {event.hazard_severity ?? "unclassified"} hazards
                          is {event.response_hours}h from the time it was logged.
                        </p>

                        {event.image_url && (
                          /* eslint-disable-next-line @next/next/no-img-element */
                          <img src={event.image_url} alt={event.detected_object ?? "hazard"} />
                        )}

                        {event.acknowledged_at ? (
                          <p className="ack">
                            Handled by {event.acknowledged_by} at {event.acknowledged_at}.
                            {event.hazard_note ? ` ${event.hazard_note}` : ""}
                          </p>
                        ) : (
                          <button
                            className="ack-btn"
                            onClick={() => acknowledge(event)}
                            disabled={busyId === event.event_id}
                          >
                            {busyId === event.event_id ? "recording…" : "mark as handled"}
                          </button>
                        )}
                      </div>
                    )}
                  </article>
                );
              })
            )}
          </div>

          <aside className="side">
            <section className="panel">
              <header>by type</header>
              {(summary?.by_class ?? []).map((row) => (
                <button
                  key={row.hazard_class}
                  className="class-row"
                  onClick={() => setSeverity(row.severity)}
                  title={row.handling}
                >
                  <span className={`dot ${row.severity}`} />
                  <span className="class-name">{row.display_name}</span>
                  <span className="class-count">{row.count}</span>
                  <span className={`class-open ${row.outstanding > 0 ? "warn" : ""}`}>
                    {row.outstanding > 0 ? `${row.outstanding} open` : "clear"}
                  </span>
                </button>
              ))}
            </section>

            <section className="panel">
              <header>where they turn up</header>
              {(summary?.by_location ?? []).slice(0, 12).map((row) => (
                <div key={`${row.building_name}-${row.hazard_class}`} className="loc-row">
                  <span className={`dot ${row.severity}`} />
                  <span className="loc-name">{row.building_name}</span>
                  <span className="loc-class">{row.hazard_class.replace(/_/g, " ")}</span>
                  <span className="loc-count">{row.count}</span>
                </div>
              ))}
            </section>

            {summary && (
              <p className="footnote">{summary.note}</p>
            )}
          </aside>
        </section>
      </div>

      <style jsx>{`
        .header-meta {
          display: inline-flex;
          align-items: baseline;
          gap: 5px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          color: var(--text-muted);
        }
        .alarm {
          color: var(--status-bug);
        }
        .dim {
          color: var(--text-dim);
        }
        .page {
          padding: 10px 12px 18px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .kpis {
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: 6px;
        }
        .alerts {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 6px;
        }
        .alert {
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 8px 10px;
          border-radius: 3px;
          border: 1px solid var(--border-08);
          border-left-width: 3px;
          background: var(--bg-surface);
        }
        .alert.critical {
          border-left-color: var(--status-bug);
        }
        .alert.high {
          border-left-color: var(--status-in-progress);
        }
        .alert.medium,
        .alert.unclassified {
          border-left-color: var(--text-dim);
        }
        .alert-kind {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--text-dim);
        }
        .alert-title {
          font-size: 12.5px;
          font-weight: 510;
          color: var(--text-primary);
        }
        .alert-detail {
          font-size: 10.5px;
          line-height: 15px;
          color: var(--text-muted);
        }
        .controls {
          display: flex;
          align-items: center;
          gap: 5px;
          flex-wrap: wrap;
          padding: 8px 10px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .k {
          color: var(--text-dim);
          font-size: 10px;
        }
        .divider {
          width: 1px;
          height: 15px;
          background: var(--border-08);
          margin: 0 4px;
        }
        .spacer {
          flex: 1;
        }
        .err {
          color: var(--status-bug);
          font-size: 10px;
        }
        .chip {
          padding: 2px 8px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          color: var(--text-muted);
          font-family: inherit;
          font-size: 10.5px;
          line-height: 16px;
        }
        .chip:hover {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.on {
          background: var(--overlay-08);
          border-color: var(--border-solid);
          color: var(--text-primary);
        }
        .chip.sev-critical.on {
          color: var(--status-bug);
          border-color: var(--status-bug);
        }
        .chip.sev-high.on {
          color: var(--status-in-progress);
          border-color: var(--status-in-progress);
        }
        .grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 320px;
          gap: 10px;
          align-items: start;
        }
        .list {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
        }
        .empty {
          padding: 20px 12px;
          color: var(--text-dim);
          font-size: 12px;
          line-height: 18px;
          max-width: 560px;
        }
        .row {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-left-width: 3px;
          border-radius: 3px;
          overflow: hidden;
        }
        .row.critical {
          border-left-color: var(--status-bug);
        }
        .row.high {
          border-left-color: var(--status-in-progress);
        }
        .row.medium {
          border-left-color: var(--cat-recycling);
        }
        .row.unclassified {
          border-left-color: var(--text-dim);
        }
        .row.done {
          opacity: 0.6;
        }
        .row.open {
          border-color: var(--primary);
        }
        .row-head {
          display: grid;
          grid-template-columns: 76px minmax(0, 1.4fr) minmax(0, 1.3fr) 140px 62px;
          align-items: center;
          gap: 10px;
          width: 100%;
          padding: 7px 10px;
          text-align: left;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .row-head:hover {
          background: var(--overlay-02);
        }
        .sev {
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--text-dim);
        }
        .sev.critical {
          color: var(--status-bug);
        }
        .sev.high {
          color: var(--status-in-progress);
        }
        .what,
        .where {
          display: flex;
          flex-direction: column;
          min-width: 0;
        }
        .name {
          color: var(--text-primary);
          font-weight: 510;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .object,
        .spot {
          color: var(--text-dim);
          font-size: 9.5px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .building {
          color: var(--text-secondary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .when {
          color: var(--text-dim);
          font-size: 10px;
          font-variant-numeric: tabular-nums;
        }
        .state {
          text-align: right;
        }
        .ok {
          color: var(--status-done);
          font-size: 9.5px;
        }
        .open-tag {
          color: var(--status-in-progress);
          font-size: 9.5px;
        }
        .detail {
          display: flex;
          flex-direction: column;
          gap: 7px;
          padding: 9px 12px 12px;
          border-top: 1px solid var(--border-05);
          font-size: 11.5px;
          line-height: 17px;
          color: var(--text-muted);
        }
        .detail b {
          color: var(--text-secondary);
          font-weight: 510;
        }
        .handling {
          padding: 8px 10px;
          background: var(--bg-card);
          border-radius: 3px;
          border-left: 2px solid var(--status-in-progress);
        }
        .detail img {
          max-width: 260px;
          border-radius: 3px;
          border: 1px solid var(--border-08);
        }
        .ack {
          color: var(--status-done);
          font-size: 11px;
        }
        .ack-btn {
          align-self: flex-start;
          padding: 5px 12px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          background: var(--overlay-08);
          color: var(--text-primary);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .ack-btn:hover:not(:disabled) {
          background: var(--primary);
        }
        .ack-btn:disabled {
          color: var(--text-dim);
          cursor: default;
        }
        .side {
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-width: 0;
        }
        .panel {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .panel header {
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 10px;
        }
        .class-row,
        .loc-row {
          display: grid;
          grid-template-columns: 7px minmax(0, 1fr) 28px 52px;
          align-items: center;
          gap: 7px;
          width: 100%;
          padding: 4px 10px;
          text-align: left;
          font-family: inherit;
          font-size: 10.5px;
          border-top: 1px solid var(--border-05);
        }
        .class-row:hover {
          background: var(--overlay-02);
        }
        .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--text-dim);
        }
        .dot.critical {
          background: var(--status-bug);
        }
        .dot.high {
          background: var(--status-in-progress);
        }
        .dot.medium {
          background: var(--cat-recycling);
        }
        .class-name,
        .loc-name {
          color: var(--text-secondary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .loc-row {
          grid-template-columns: 7px minmax(0, 1fr) minmax(0, 0.9fr) 24px;
        }
        .loc-class {
          color: var(--text-dim);
          font-size: 9.5px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .class-count,
        .loc-count {
          text-align: right;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }
        .class-open {
          text-align: right;
          color: var(--text-dim);
          font-size: 9.5px;
        }
        .class-open.warn {
          color: var(--status-in-progress);
        }
        .footnote {
          padding: 8px 10px;
          color: var(--text-dim);
          font-size: 10px;
          line-height: 14px;
        }
        @media (max-width: 1240px) {
          .grid {
            grid-template-columns: 1fr;
          }
          .kpis {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
          .row-head {
            grid-template-columns: 70px minmax(0, 1fr) 56px;
          }
          .where,
          .when {
            display: none;
          }
        }
      `}</style>
    </>
  );
}
