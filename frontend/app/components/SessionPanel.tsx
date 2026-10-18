"use client";

import { useMemo } from "react";
import { CategoryDot } from "./CategoryDot";
import type { CameraStats, WasteEvent } from "../../lib/api";

export default function SessionPanel({
  cameraStats,
  events,
  sessionStart,
  now,
}: {
  cameraStats: CameraStats | null;
  events: WasteEvent[];
  sessionStart: number;
  now: number;
}) {
  const stats = useMemo(() => computeSessionStats(cameraStats, events, sessionStart, now), [cameraStats, events, sessionStart, now]);
  const stream = useMemo(() => computeStreamSplit(events), [events]);

  return (
    <aside className="panel">
      <header className="panel-header">
        <span className="title">session</span>
        <span className="meta">{stats.sessionDuration}</span>
      </header>

      <div className="bar-strip" title="category share">
        {stream.map((s) => (
          <span key={s.category} className="seg" style={{ flex: s.count || 0.05, background: s.color }} title={`${s.category} ${s.count}`} />
        ))}
      </div>

      <dl className="kv">
        <KV k="frames" v={stats.frames.toLocaleString()} />
        <KV k="items" v={stats.itemsPersisted.toLocaleString()} />
        <KV k="uncertain" v={stats.uncertain.toLocaleString()} />
        <KV k="inference" v={cameraStats?.last_inference_ms != null ? `${cameraStats.last_inference_ms}ms` : "—"} />
        <KV k="camera" v={cameraStats?.camera_opened ? "open" : "closed"} />
      </dl>

      <div className="group-label">activity</div>
      <div className="feed">
        {events.slice(0, 8).map((e) => (
          <div key={e.event_id} className="feed-row">
            <CategoryDot category={e.category || "unknown"} size={5} />
            <span className="feed-name">{e.detected_object || "unknown"}</span>
            <span className="feed-time">{shortTime(e.created_at)}</span>
          </div>
        ))}
        {events.length === 0 && <div className="feed-empty">no events</div>}
      </div>

      <style jsx>{`
        .panel {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 10px 12px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          min-width: 0;
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        .panel-header {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          padding-bottom: 6px;
          border-bottom: 1px solid var(--border-05);
        }
        .title {
          font-size: 11px;
          color: var(--text-dim);
          font-weight: 400;
        }
        .meta {
          font-size: 12px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .bar-strip {
          display: flex;
          height: 3px;
          background: var(--overlay-05);
          overflow: hidden;
          gap: 0;
        }
        .seg {
          display: block;
          height: 100%;
          transition: flex 0.3s ease;
        }
        .kv {
          display: flex;
          flex-direction: column;
          gap: 0;
          margin: 0;
        }
        .group-label {
          font-size: 10.5px;
          color: var(--text-dim);
          padding: 6px 0 2px;
          border-top: 1px solid var(--border-05);
          margin-top: 2px;
        }
        .feed {
          display: flex;
          flex-direction: column;
          gap: 0;
        }
        .feed-row {
          display: grid;
          grid-template-columns: 5px 1fr auto;
          align-items: center;
          gap: 8px;
          padding: 3px 0;
          font-size: 11.5px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .feed-name {
          color: var(--text-secondary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .feed-time {
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        .feed-empty {
          color: var(--text-dim);
          font-size: 11px;
          padding: 6px 0;
        }
      `}</style>
    </aside>
  );
}

function KV({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="kv-row">
      <span className="k">{k}</span>
      <span className="dots" />
      <span className="v">{v}</span>
      <style jsx>{`
        .kv-row {
          display: grid;
          grid-template-columns: auto 1fr auto;
          align-items: baseline;
          gap: 6px;
          padding: 2px 0;
          font-size: 11.5px;
        }
        .k {
          color: var(--text-dim);
        }
        .dots {
          height: 1px;
          background: repeating-linear-gradient(
            to right,
            var(--border-05) 0,
            var(--border-05) 2px,
            transparent 2px,
            transparent 5px
          );
          align-self: center;
          margin-top: 2px;
        }
        .v {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
      `}</style>
    </div>
  );
}

function computeStreamSplit(events: WasteEvent[]) {
  const counts: Record<string, number> = { recycling: 0, compost: 0, landfill: 0, unknown: 0 };
  for (const e of events) {
    const c = (e.category && counts[e.category] !== undefined ? e.category : "unknown") as string;
    counts[c]++;
  }
  const palette: Record<string, string> = {
    recycling: "#3b82f6",
    compost: "#10b981",
    landfill: "#f87171",
    unknown: "#f5c842",
  };
  return (["recycling", "compost", "landfill", "unknown"] as const).map((category) => ({
    category,
    count: counts[category] || 0,
    color: palette[category],
  }));
}

function computeSessionStats(cam: CameraStats | null, events: WasteEvent[], sessionStart: number, now: number) {
  const sessionMs = Math.max(0, now - sessionStart);
  const sessionMin = Math.floor(sessionMs / 60000);
  const sessionSec = Math.floor((sessionMs % 60000) / 1000);
  const sessionDuration = `${pad(sessionMin)}:${pad(sessionSec)}`;
  const uncertain = events.filter((e) => !e.category || e.category === "unknown").length;
  return {
    sessionDuration,
    frames: cam?.frames || 0,
    itemsPersisted: events.length,
    uncertain,
  };
}

function pad(n: number) {
  return n < 10 ? `0${n}` : `${n}`;
}

function shortTime(raw: string | null): string {
  if (!raw) return "—";
  const parts = raw.split(" ");
  return parts.length === 2 ? parts[1].slice(0, 5) : raw.slice(-5);
}
