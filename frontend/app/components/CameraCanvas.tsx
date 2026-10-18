"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, WS_BASE, type Detection, type DetectionEvent } from "../../lib/api";
import { CATEGORY_COLOR } from "./CategoryDot";

export default function CameraCanvas({
  onDetection,
}: {
  onDetection?: (ev: DetectionEvent) => void;
}) {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [streamOk, setStreamOk] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const url = `${WS_BASE}/ws/detections`;
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as DetectionEvent;
          setDetections(ev.detections);
          onDetection?.(ev);
        } catch {}
      };
      ws.onclose = () => {
        if (!closed) {
          retryTimer = setTimeout(connect, 2000);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, [onDetection]);

  return (
    <div ref={containerRef} className="camera-wrap">
      <img
        src={`${API_BASE}/camera/stream`}
        alt="Live camera"
        onError={() => setStreamOk(false)}
        onLoad={() => setStreamOk(true)}
      />
      <svg className="overlay" viewBox="0 0 1 1" preserveAspectRatio="none">
        {detections.map((d, i) => {
          const color = CATEGORY_COLOR[d.category || "unknown"];
          const w = d.x2 - d.x1;
          const h = d.y2 - d.y1;
          return (
            <g key={i}>
              <rect
                x={d.x1}
                y={d.y1}
                width={w}
                height={h}
                fill="none"
                stroke={color}
                strokeWidth="0.0025"
                vectorEffect="non-scaling-stroke"
                style={{ strokeWidth: "1.5px" } as React.CSSProperties}
              />
            </g>
          );
        })}
      </svg>

      <div className="overlay-labels">
        {detections.map((d, i) => (
          <div
            key={i}
            className="label-chip"
            style={{
              left: `${d.x1 * 100}%`,
              top: `${d.y1 * 100}%`,
              transform: "translate(0, -100%)",
              borderColor: CATEGORY_COLOR[d.category || "unknown"],
            }}
          >
            <span className="dot" style={{ background: CATEGORY_COLOR[d.category || "unknown"] }} />
            <span className="label">{d.label}</span>
            <span className="conf">{(d.confidence * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>

      {!streamOk && (
        <div className="camera-fallback">
          <span className="title">No feed</span>
          <span className="hint">{API_BASE}</span>
        </div>
      )}

      <style jsx>{`
        .camera-wrap {
          position: relative;
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #0b0c0d;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          overflow: hidden;
        }
        .camera-wrap img {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .overlay {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        .overlay-labels {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }
        .label-chip {
          position: absolute;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 2px 6px;
          background: rgba(8, 9, 10, 0.88);
          border: 1px solid;
          border-radius: 3px;
          font-size: 11px;
          font-weight: 510;
          color: var(--text-primary);
          white-space: nowrap;
          margin-top: -2px;
        }
        .label-chip .dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
        }
        .label-chip .label {
          color: var(--text-primary);
        }
        .label-chip .conf {
          color: var(--text-dim);
          font-weight: 400;
          font-variant-numeric: tabular-nums;
        }
        .camera-fallback {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          background: #0b0c0d;
          color: var(--text-muted);
          font-size: 13px;
        }
        .camera-fallback .title {
          color: var(--text-secondary);
          font-weight: 510;
        }
        .camera-fallback .hint {
          color: var(--text-dim);
          font-size: 12px;
        }
      `}</style>
    </div>
  );
}
