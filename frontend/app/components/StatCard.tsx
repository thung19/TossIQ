"use client";

export default function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string | number;
  delta?: string;
  suffix?: string;
}) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value-row">
        <span className="value">{value}</span>
        {suffix && <span className="suffix">{suffix}</span>}
      </div>
      <style jsx>{`
        .stat-card {
          background: var(--overlay-02);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          padding: 7px 10px;
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .label {
          font-size: 10.5px;
          font-weight: 400;
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
        }
        .value-row {
          display: flex;
          align-items: baseline;
          gap: 2px;
        }
        .value {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 16px;
          font-weight: 510;
          color: var(--text-primary);
          letter-spacing: -0.2px;
          line-height: 1;
          font-variant-numeric: tabular-nums;
        }
        .suffix {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          font-weight: 400;
          color: var(--text-dim);
        }
      `}</style>
    </div>
  );
}
