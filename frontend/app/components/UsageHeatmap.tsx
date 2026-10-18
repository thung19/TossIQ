"use client";

import { Fragment, useMemo } from "react";
import { HEAT_RAMP, bucketLabel, heatColor, hourLabel } from "../../lib/heatScale";
import type { FleetActivity, TimeBucket } from "../../lib/api";

/**
 * When the fleet gets used: a 7 x 24 grid of disposal counts, weekday down,
 * hour of day across.
 *
 * The grid is the control as well as the chart. Clicking a cell, a day label,
 * or an hour label selects that slice and recolours the map beside it, so
 * "where do the busy cans sit at 6pm on a Friday" is one click rather than a
 * filter form. Clicking the active selection again clears it.
 *
 * Counts are logged disposal events -- usage frequency. There are no weight
 * sensors, so this is deliberately not presented as how full anything gets.
 */
export default function UsageHeatmap({
  activity,
  error,
  bucket,
  onBucketChange,
  windowDays,
  onWindowDaysChange,
  selectionHint = "click a cell, day, or hour to filter the map",
}: {
  activity: FleetActivity | null;
  /** Last fetch failure, if the panel has no data to show yet. The page keeps
   * retrying, so this is a status line rather than a dead end. */
  error?: string | null;
  bucket: TimeBucket;
  onBucketChange: (bucket: TimeBucket) => void;
  windowDays: number;
  onWindowDaysChange: (days: number) => void;
  /** What selecting a bucket does here. The grid is reused on the campus map,
   * where a selection recolours the pins, and on the analytics page, where it
   * does not -- so the hint cannot be hardcoded to either. */
  selectionHint?: string;
}) {
  const dayNames = activity?.day_names ?? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const grid = activity?.day_hour ?? Array.from({ length: 7 }, () => new Array(24).fill(0));
  const scaleMax = activity?.scale_max_cell ?? 1;

  const dayTotals = useMemo(() => grid.map((row) => row.reduce((a, b) => a + b, 0)), [grid]);
  const hourTotals = activity?.by_hour ?? new Array(24).fill(0);

  // The absolute peak is worth showing, but only as a labelled outlier: it is
  // a single bucket, and one burst of captures can own it outright. The
  // headline is the server's median-per-hour figure, which is the hour that
  // is busy most days.
  const outlier =
    activity?.peak != null && activity.peak.count > activity.scale_max_cell * 3
      ? activity.peak
      : null;

  const toggleCell = (day: number, hour: number) =>
    onBucketChange(
      bucket.day === day && bucket.hour === hour ? { day: null, hour: null } : { day, hour }
    );
  const toggleDay = (day: number) =>
    onBucketChange(bucket.day === day && bucket.hour == null ? { day: null, hour: null } : { day, hour: null });
  const toggleHour = (hour: number) =>
    onBucketChange(bucket.hour === hour && bucket.day == null ? { day: null, hour: null } : { day: null, hour });

  const selected = bucket.day != null || bucket.hour != null;

  return (
    <section className="heat">
      <header>
        <span className="title">usage by hour</span>
        <span className="spacer" />
        {[7, 14, 30].map((days) => (
          <button
            key={days}
            className={`chip ${windowDays === days ? "on" : ""}`}
            onClick={() => onWindowDaysChange(days)}
          >
            {days}d
          </button>
        ))}
      </header>

      <div className="readout">
        {activity === null ? (
          <span className="dim">{error ? `usage data unavailable (${error}) — retrying` : "loading…"}</span>
        ) : activity.total_events === 0 ? (
          <span className="dim">no disposals logged in this window</span>
        ) : (
          <>
            <span>
              busiest hour{" "}
              <b>
                {activity.typical_peak ? hourLabel(activity.typical_peak.hour_of_day) : "—"}
              </b>
              {activity.typical_peak != null && (
                <span className="dim"> ({activity.typical_peak.count}/h median)</span>
              )}
            </span>
            <span className="dim">·</span>
            <span>
              quietest{" "}
              <b>{hourLabel(hourTotals.indexOf(Math.min(...hourTotals)))}</b>
            </span>
            <span className="dim">·</span>
            <span>
              <b>{activity.total_events.toLocaleString()}</b> items / {activity.window_days}d
            </span>
            {outlier && (
              <>
                <span className="dim">·</span>
                <span className="dim">
                  one-off spike {outlier.day_name} {hourLabel(outlier.hour_of_day)} ({outlier.count})
                </span>
              </>
            )}
          </>
        )}
      </div>

      <div className="grid" role="group" aria-label="Disposals by weekday and hour">
        <span className="corner" />
        {Array.from({ length: 24 }, (_, hour) => (
          <button
            key={hour}
            className={`axis hour ${bucket.day == null && bucket.hour === hour ? "on" : ""}`}
            onClick={() => toggleHour(hour)}
            title={`${hourLabel(hour)} across every day — ${hourTotals[hour]} items`}
          >
            {hour % 3 === 0 ? hourLabel(hour) : ""}
          </button>
        ))}
        <span className="axis total-head">tot</span>

        {grid.map((row, day) => (
          <Fragment key={day}>
            <button
              className={`axis day ${bucket.day === day && bucket.hour == null ? "on" : ""}`}
              onClick={() => toggleDay(day)}
              title={`${dayNames[day]} — ${dayTotals[day]} items`}
            >
              {dayNames[day]}
            </button>
            {row.map((count, hour) => {
              const active = bucket.day === day && bucket.hour === hour;
              const over = activity != null && count > scaleMax;
              return (
                <button
                  key={hour}
                  className={`cell ${active ? "on" : ""} ${over ? "over" : ""} ${count === 0 ? "zero" : ""}`}
                  style={{ background: heatColor(count, scaleMax) }}
                  onClick={() => toggleCell(day, hour)}
                  title={`${dayNames[day]} ${hourLabel(hour)} — ${count} item${count === 1 ? "" : "s"}${
                    over ? " (over the colour scale)" : ""
                  }`}
                  aria-label={`${dayNames[day]} ${hourLabel(hour)}, ${count} items`}
                />
              );
            })}
            <span className="total">{dayTotals[day] || ""}</span>
          </Fragment>
        ))}
      </div>

      <footer>
        <span className="legend">
          <span className="dim">less</span>
          {HEAT_RAMP.map((stop) => (
            <span key={stop} className="stop" style={{ background: stop }} />
          ))}
          <span className="dim">{activity ? `${activity.scale_max_cell}+` : "more"}</span>
        </span>
        <span className="spacer" />
        {selected ? (
          <button className="chip clear" onClick={() => onBucketChange({ day: null, hour: null })}>
            showing {bucketLabel(bucket.day, bucket.hour, dayNames)} — clear
          </button>
        ) : (
          <span className="dim hint">{selectionHint}</span>
        )}
      </footer>

      <style jsx>{`
        .heat {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          min-width: 0;
        }
        header,
        footer {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 7px 10px;
          font-size: 11px;
        }
        header {
          border-bottom: 1px solid var(--border-05);
        }
        footer {
          border-top: 1px solid var(--border-05);
        }
        .title {
          color: var(--text-dim);
        }
        .spacer {
          flex: 1;
        }
        .chip {
          padding: 2px 7px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          color: var(--text-muted);
          font-family: inherit;
          font-size: 10.5px;
          line-height: 15px;
        }
        .chip:hover {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.on {
          background: var(--overlay-08);
          color: var(--text-primary);
          border-color: var(--border-solid);
        }
        .chip.clear {
          color: var(--text-secondary);
        }
        .readout {
          display: flex;
          flex-wrap: wrap;
          align-items: baseline;
          gap: 5px;
          padding: 7px 10px 2px;
          color: var(--text-muted);
          font-size: 10.5px;
        }
        .readout b {
          color: var(--text-primary);
          font-weight: 510;
          font-variant-numeric: tabular-nums;
        }
        .dim {
          color: var(--text-dim);
        }
        .grid {
          display: grid;
          grid-template-columns: 30px repeat(24, minmax(0, 1fr)) 28px;
          gap: 2px;
          padding: 6px 10px 8px;
          min-width: 0;
        }
        .axis {
          color: var(--text-dim);
          font-family: inherit;
          font-size: 9px;
          line-height: 12px;
          text-align: center;
          padding: 0;
          border-radius: 2px;
          overflow: hidden;
        }
        .axis:hover {
          color: var(--text-primary);
          background: var(--overlay-05);
        }
        .axis.on {
          color: var(--text-primary);
          background: var(--overlay-08);
        }
        .axis.day {
          text-align: left;
          font-size: 10px;
        }
        .total-head,
        .total {
          color: var(--text-dim);
          font-size: 9px;
          text-align: right;
          font-variant-numeric: tabular-nums;
          align-self: center;
        }
        .cell {
          aspect-ratio: 1;
          min-width: 0;
          border-radius: 2px;
          padding: 0;
          border: 1px solid transparent;
        }
        .cell.zero {
          background: var(--overlay-02) !important;
        }
        .cell:hover {
          border-color: var(--text-secondary);
        }
        .cell.on {
          border-color: var(--text-primary);
          box-shadow: 0 0 0 1px var(--text-primary);
        }
        /* A bucket above the percentile bound is already painted the top stop,
           so it needs a non-colour mark to stay distinguishable from one that
           merely reaches the bound. */
        .cell.over {
          border-color: var(--text-primary);
          border-style: dashed;
        }
        .legend {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          font-size: 9.5px;
        }
        .stop {
          width: 11px;
          height: 8px;
          border-radius: 1px;
        }
        .hint {
          font-size: 10px;
        }
      `}</style>
    </section>
  );
}
