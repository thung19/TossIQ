"use client";

import { CategoryDot } from "./CategoryDot";
import { StatusRing } from "./StatusRing";
import CodeChip from "./CodeChip";
import type { Detection } from "../../lib/api";

const CATEGORY_RULE: Record<string, string> = {
  recycling: "Clean, dry, single-material item meeting curbside recycling guidance.",
  compost: "Organic matter suitable for compost stream.",
  landfill: "Plastic-lined, contaminated, or non-recyclable item.",
  unknown: "Uncertain classification. Flagged for manual review.",
};

export default function DetectionCard({
  detection,
  updatedAt,
}: {
  detection: Detection | null;
  updatedAt: number | null;
}) {
  const empty = !detection;
  const category = detection?.category || "unknown";
  const confidence = detection?.confidence ?? 0;
  const confPct = Math.round(confidence * 100);
  const rule = CATEGORY_RULE[category];
  const ago = null;

  return (
    <section className="detection">
      <header>
        <span className="toolbar-title">Current detection</span>
        <span className="toolbar-right">
          <StatusRing variant="in-progress" size={12} />
          <span>{empty ? "Waiting" : "Classifying"}</span>
        </span>
      </header>

      <div className="body">
        {empty ? (
          <div className="empty">
            <span className="title">Nothing in frame</span>
            <span className="sub">Place an item in view of the camera.</span>
          </div>
        ) : (
          <>
            <div className="title-row">
              <h2 className="title">{detection.label}</h2>
              <span className="conf">{confPct}%</span>
            </div>
            <div className="meta-row">
              <CategoryDot category={category} size={8} />
              <span className="cat-text">{category}</span>
              <span className="sep">·</span>
              <CodeChip>YOLOe</CodeChip>
              {ago && <><span className="sep">·</span><span className="ago">{ago}</span></>}
            </div>

            <div className="divider" />

            <div className="prop-group">
              <PropertyRow label="Destination" value={<DestinationBadge category={category} />} />
              <PropertyRow label="Material" value={<span className="mono">{detection.label}</span>} />
              <PropertyRow label="Confidence" value={<span className="mono">{confidence.toFixed(3)}</span>} />
              <PropertyRow label="Reasoning" value={<span className="reasoning">{rule}</span>} />
            </div>

            <div className="actions">
              <button className="btn primary">Confirm</button>
              <button className="btn secondary">Correct label</button>
            </div>
          </>
        )}
      </div>

      <style jsx>{`
        .detection {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 10px;
          display: flex;
          flex-direction: column;
          height: 100%;
          min-height: 420px;
        }
        header {
          padding: 10px 16px;
          border-bottom: 1px solid var(--border-05);
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 12.5px;
        }
        .toolbar-title {
          font-weight: 510;
          color: var(--text-secondary);
        }
        .toolbar-right {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          color: var(--text-dim);
        }
        .body {
          padding: 20px 20px 16px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          flex: 1;
        }
        .empty {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 48px 0;
          align-items: center;
          text-align: center;
          color: var(--text-dim);
        }
        .empty .title {
          font-size: 15px;
          font-weight: 510;
          color: var(--text-secondary);
        }
        .empty .sub {
          font-size: 13px;
          color: var(--text-dim);
        }
        .title-row {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 12px;
        }
        .title {
          font-size: 22px;
          font-weight: 590;
          color: var(--text-primary);
          letter-spacing: -0.4px;
          line-height: 28px;
          text-transform: capitalize;
        }
        .conf {
          font-size: 15px;
          font-weight: 510;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }
        .meta-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: var(--text-muted);
        }
        .cat-text {
          text-transform: capitalize;
          color: var(--text-secondary);
        }
        .sep {
          color: var(--text-dim);
        }
        .ago {
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        .divider {
          height: 1px;
          background: var(--border-05);
          margin: 2px 0;
        }
        .prop-group {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .mono {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 12.5px;
          color: var(--text-secondary);
        }
        .reasoning {
          color: var(--text-muted);
          font-size: 13px;
          line-height: 18px;
        }
        .actions {
          display: flex;
          gap: 8px;
          margin-top: auto;
          padding-top: 14px;
          border-top: 1px solid var(--border-05);
        }
        .btn {
          padding: 7px 14px;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 510;
          transition: background 0.08s ease;
        }
        .btn.primary {
          background: #e6e6e6;
          color: #08090a;
        }
        .btn.primary:hover {
          background: #f4f5f8;
        }
        .btn.secondary {
          background: var(--overlay-02);
          color: var(--text-secondary);
          border: 1px solid var(--border-08);
        }
        .btn.secondary:hover {
          background: var(--overlay-05);
        }
      `}</style>
    </section>
  );
}

function PropertyRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="prop-row">
      <span className="prop-label">{label}</span>
      <span className="prop-value">{value}</span>
      <style jsx>{`
        .prop-row {
          display: grid;
          grid-template-columns: 100px 1fr;
          gap: 12px;
          align-items: baseline;
          font-size: 13px;
        }
        .prop-label {
          color: var(--text-dim);
          letter-spacing: 0.1px;
          font-size: 11px;
          font-weight: 510;
          padding-top: 2px;
        }
        .prop-value {
          color: var(--text-secondary);
        }
      `}</style>
    </div>
  );
}

function DestinationBadge({ category }: { category: string }) {
  const map: Record<string, { text: string; color: string }> = {
    recycling: { text: "Recycling bin", color: "var(--cat-recycling)" },
    compost: { text: "Compost bin", color: "var(--cat-compost)" },
    landfill: { text: "Landfill bin", color: "var(--cat-landfill)" },
    unknown: { text: "Review queue", color: "var(--cat-unknown)" },
  };
  const dest = map[category] || map.unknown;
  return (
    <span className="dest">
      <span className="dot" style={{ background: dest.color }} />
      <span>{dest.text}</span>
      <style jsx>{`
        .dest {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-weight: 510;
          color: var(--text-primary);
        }
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
      `}</style>
    </span>
  );
}
