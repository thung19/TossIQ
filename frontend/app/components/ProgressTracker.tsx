"use client";

import { useMemo } from "react";
import { CategoryDot } from "./CategoryDot";
import type { CameraStats, Detection } from "../../lib/api";

type Stage = {
  key: string;
  label: string;
  value: string;
  done: boolean;
};

export default function ProgressTracker({
  detection,
  updatedAt,
  cameraStats,
  now,
}: {
  detection: Detection | null;
  updatedAt: number | null;
  cameraStats: CameraStats | null;
  now: number;
}) {
  const stages = useMemo(() => buildStages(detection, cameraStats), [detection, cameraStats]);

  return (
    <section className="tracker">
      <header>
        <div className="left">
          <span className="prompt">pipeline</span>
          <span className="arrow">›</span>
          {detection ? (
            <>
              <CategoryDot category={detection.category || "unknown"} size={5} />
              <span className="object">{detection.label}</span>
              <span className="conf">{(detection.confidence * 100).toFixed(1)}%</span>
            </>
          ) : (
            <span className="object dim">none</span>
          )}
        </div>
        <span className="right">
          {cameraStats?.last_inference_ms != null && (
            <span className="meta-item">
              <span className="k">lat</span>
              <span className="v">{cameraStats.last_inference_ms}ms</span>
            </span>
          )}
          {updatedAt && now > 0 && (
            <span className="meta-item">
              <span className="k">upd</span>
              <span className="v">{Math.max(0, Math.floor((now - updatedAt) / 1000))}s</span>
            </span>
          )}
        </span>
      </header>

      <div className="stages">
        {stages.map((s, i) => (
          <div key={s.key} className={`stage ${s.done ? "done" : ""}`}>
            <span className="n">{(i + 1).toString().padStart(2, "0")}</span>
            <span className="label">{s.label}</span>
            <span className="value">{s.value}</span>
          </div>
        ))}
      </div>

      <style jsx>{`
        .tracker {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 8px 12px 10px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding-bottom: 6px;
          border-bottom: 1px solid var(--border-05);
        }
        .left {
          display: flex;
          align-items: center;
          gap: 6px;
          min-width: 0;
          font-size: 11.5px;
        }
        .prompt {
          color: var(--text-dim);
        }
        .arrow {
          color: var(--text-dim);
        }
        .object {
          color: var(--text-primary);
          font-weight: 510;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .object.dim {
          color: var(--text-dim);
          font-weight: 400;
        }
        .conf {
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }
        .right {
          display: flex;
          gap: 10px;
        }
        .meta-item {
          display: inline-flex;
          gap: 4px;
          font-size: 11px;
        }
        .meta-item .k {
          color: var(--text-dim);
        }
        .meta-item .v {
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
          font-weight: 510;
        }
        .stages {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 0;
        }
        .stage {
          display: grid;
          grid-template-rows: auto auto;
          grid-template-columns: auto 1fr;
          column-gap: 6px;
          row-gap: 2px;
          padding: 4px 10px 4px 0;
          border-right: 1px solid var(--border-05);
          font-size: 11.5px;
        }
        .stage:last-child {
          border-right: none;
        }
        .stage .n {
          grid-row: 1 / span 2;
          align-self: start;
          color: var(--text-dim);
          font-size: 10px;
          padding-top: 2px;
        }
        .stage.done .n {
          color: var(--status-done);
        }
        .label {
          color: var(--text-dim);
          font-size: 10.5px;
        }
        .stage.done .label {
          color: var(--text-muted);
        }
        .value {
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
          text-transform: lowercase;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .stage.done .value {
          color: var(--text-primary);
          font-weight: 510;
        }
      `}</style>
    </section>
  );
}

function buildStages(d: Detection | null, cam: CameraStats | null): Stage[] {
  const captured = !!cam?.camera_opened;
  const classified = !!d;
  const routed = !!d && !!d.category;
  const logged = routed && (d?.confidence || 0) >= 0.55;
  return [
    { key: "capture", label: "capture", value: captured ? `${(cam?.frames ?? 0).toLocaleString()} fr` : "—", done: captured },
    { key: "classify", label: "classify", value: d?.label || "—", done: classified },
    { key: "route", label: "route", value: d?.category || "—", done: routed },
    { key: "log", label: "log", value: logged ? "ok" : classified ? "<thr" : "—", done: logged },
    { key: "latency", label: "latency", value: cam?.last_inference_ms != null ? `${cam.last_inference_ms}ms` : "—", done: !!cam?.last_inference_ms },
  ];
}
