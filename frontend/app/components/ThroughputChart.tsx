"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { WasteEvent } from "../../lib/api";

type Bucket = { label: string; ts: number; recycling: number; compost: number; landfill: number; unknown: number; total: number };

export default function ThroughputChart({
  events,
  now,
  windowHours = 12,
  bucketMinutes = 30,
}: {
  events: WasteEvent[];
  now: number;
  windowHours?: number;
  bucketMinutes?: number;
}) {
  const data = useMemo(() => bucketEvents(events, now, windowHours, bucketMinutes), [events, now, windowHours, bucketMinutes]);
  const total = data.reduce((acc, b) => acc + b.total, 0);
  const peak = data.reduce((max, b) => (b.total > max ? b.total : max), 0);

  return (
    <section className="card">
      <header>
        <div className="title-row">
          <span className="title">throughput</span>
          <span className="meta">{windowHours}h · {bucketMinutes}m</span>
        </div>
        <div className="stats-row">
          <span className="stat"><span className="l">n</span><span className="n">{total}</span></span>
          <span className="stat"><span className="l">peak</span><span className="n">{peak}</span></span>
        </div>
      </header>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--text-dim)", fontSize: 10, fontFamily: "ui-monospace, Menlo, monospace" }}
              axisLine={{ stroke: "var(--border-05)" }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={32}
            />
            <YAxis
              tick={{ fill: "var(--text-dim)", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={24}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-08)",
                borderRadius: 6,
                fontSize: 12,
                color: "var(--text-primary)",
                padding: "8px 10px",
              }}
              labelStyle={{ color: "var(--text-dim)", fontSize: 11, marginBottom: 4 }}
              itemStyle={{ color: "var(--text-secondary)", padding: "1px 0", textTransform: "capitalize" }}
              cursor={{ stroke: "var(--border-08)", strokeWidth: 1 }}
            />
            <Area type="monotone" dataKey="recycling" stackId="1" stroke="#3b82f6" strokeWidth={1} fill="#3b82f6" fillOpacity={0.08} />
            <Area type="monotone" dataKey="compost" stackId="1" stroke="#10b981" strokeWidth={1} fill="#10b981" fillOpacity={0.08} />
            <Area type="monotone" dataKey="landfill" stackId="1" stroke="#f87171" strokeWidth={1} fill="#f87171" fillOpacity={0.08} />
            <Area type="monotone" dataKey="unknown" stackId="1" stroke="#f5c842" strokeWidth={1} fill="#f5c842" fillOpacity={0.08} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <style jsx>{`
        .card {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          display: flex;
          flex-direction: column;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 10px;
        }
        .title-row {
          display: flex;
          align-items: baseline;
          gap: 8px;
        }
        .title {
          font-size: 11px;
          color: var(--text-dim);
        }
        .meta {
          font-size: 10.5px;
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        .stats-row {
          display: flex;
          gap: 12px;
          font-size: 11px;
        }
        .stat {
          display: inline-flex;
          align-items: baseline;
          gap: 4px;
        }
        .stat .n {
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .stat .l {
          color: var(--text-dim);
        }
        .chart {
          height: 120px;
          padding: 6px 4px 4px;
        }
      `}</style>
    </section>
  );
}

function bucketEvents(events: WasteEvent[], now: number, windowHours: number, bucketMinutes: number): Bucket[] {
  if (!now) return [];
  const windowMs = windowHours * 60 * 60 * 1000;
  const bucketMs = bucketMinutes * 60 * 1000;
  const start = now - windowMs;
  const bucketCount = Math.ceil(windowMs / bucketMs);
  const buckets: Bucket[] = [];
  for (let i = 0; i < bucketCount; i++) {
    const ts = start + i * bucketMs;
    const d = new Date(ts);
    const label = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    buckets.push({ label, ts, recycling: 0, compost: 0, landfill: 0, unknown: 0, total: 0 });
  }
  for (const e of events) {
    const t = parseEventTs(e.created_at);
    if (t == null || t < start || t > now) continue;
    const idx = Math.min(bucketCount - 1, Math.floor((t - start) / bucketMs));
    const bucket = buckets[idx];
    const cat = (e.category || "unknown") as keyof Bucket;
    if (cat === "recycling" || cat === "compost" || cat === "landfill") {
      bucket[cat]++;
    } else {
      bucket.unknown++;
    }
    bucket.total++;
  }
  return buckets;
}

function parseEventTs(raw: string | null): number | null {
  if (!raw) return null;
  const iso = raw.replace(" ", "T") + "Z";
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

function pad(n: number) {
  return n < 10 ? `0${n}` : `${n}`;
}
