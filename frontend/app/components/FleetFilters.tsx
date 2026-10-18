"use client";

import type { Building, CanModel, CanStatus, FleetSummary } from "../../lib/api";

export type FleetFilterState = {
  status: CanStatus | "";
  buildingId: string;
  modelId: string;
  stream: string;
};

export const EMPTY_FILTERS: FleetFilterState = {
  status: "",
  buildingId: "",
  modelId: "",
  stream: "",
};

/**
 * Status, building, hardware version, and waste-stream filters.
 *
 * Every option set comes from the API (GET /buildings, GET /can-models,
 * GET /fleet/summary) rather than being hardcoded here, so a new building or a
 * new hardware revision appears in the filter without a frontend change. The
 * status counts come from /fleet/summary, which derives them with the same
 * fleet.py thresholds the pin colours use.
 */
export default function FleetFilters({
  value,
  onChange,
  buildings,
  models,
  summary,
}: {
  value: FleetFilterState;
  onChange: (next: FleetFilterState) => void;
  buildings: Building[];
  models: CanModel[];
  summary: FleetSummary | null;
}) {
  const set = (patch: Partial<FleetFilterState>) => onChange({ ...value, ...patch });
  const streams = Array.from(
    new Set(models.map((m) => m.stream_count).filter((s): s is number => s != null))
  ).sort((a, b) => a - b);
  const active = Object.values(value).some(Boolean);

  const statusOptions: [CanStatus, string][] = [
    ["needs_service", "needs service"],
    ["fault", "hardware fault"],
    ["offline", "offline"],
    ["ok", "ok"],
  ];

  return (
    <section className="filters">
      <div className="group">
        <span className="group-label">status</span>
        <div className="chips">
          <button
            className={`chip ${value.status === "" ? "on" : ""}`}
            onClick={() => set({ status: "" })}
          >
            all
            {summary && <span className="n">{summary.total}</span>}
          </button>
          {statusOptions.map(([status, label]) => (
            <button
              key={status}
              className={`chip ${status} ${value.status === status ? "on" : ""}`}
              onClick={() => set({ status: value.status === status ? "" : status })}
            >
              <span className={`dot ${status}`} />
              {label}
              {summary && <span className="n">{summary.by_status[status] ?? 0}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="group selects">
        <label className="select">
          <span className="group-label">building</span>
          <select value={value.buildingId} onChange={(e) => set({ buildingId: e.target.value })}>
            <option value="">all buildings</option>
            {buildings.map((b) => (
              <option key={b.building_id} value={String(b.building_id)}>
                {b.name} ({b.can_count})
              </option>
            ))}
          </select>
        </label>

        <label className="select">
          <span className="group-label">hardware version</span>
          <select value={value.modelId} onChange={(e) => set({ modelId: e.target.value })}>
            <option value="">all models</option>
            {models.map((m) => (
              <option key={m.model_id} value={String(m.model_id)}>
                {m.model_code} · fw {m.firmware_version ?? "—"}
              </option>
            ))}
          </select>
        </label>

        <label className="select">
          <span className="group-label">streams</span>
          <select value={value.stream} onChange={(e) => set({ stream: e.target.value })}>
            <option value="">any</option>
            {streams.map((s) => (
              <option key={s} value={String(s)}>
                {s}-stream
              </option>
            ))}
          </select>
        </label>

        {active && (
          <button className="clear" onClick={() => onChange(EMPTY_FILTERS)}>
            clear
          </button>
        )}
      </div>

      <style jsx>{`
        .filters {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 10px;
          padding: 8px 10px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .group {
          display: flex;
          flex-direction: column;
          gap: 5px;
          min-width: 0;
        }
        .group.selects {
          flex-direction: row;
          align-items: flex-end;
          gap: 8px;
          flex-wrap: wrap;
        }
        .group-label {
          font-size: 10px;
          color: var(--text-dim);
        }
        .chips {
          display: flex;
          gap: 4px;
          flex-wrap: wrap;
        }
        .chip {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 3px 8px;
          font-size: 11px;
          font-family: inherit;
          color: var(--text-muted);
          background: var(--overlay-02);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          white-space: nowrap;
        }
        .chip:hover {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.on {
          background: var(--overlay-08);
          border-color: var(--border-solid);
          color: var(--text-primary);
          font-weight: 510;
        }
        .chip .n {
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        .chip.on .n {
          color: var(--text-secondary);
        }
        .dot {
          width: 6px;
          height: 6px;
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
        .select {
          display: flex;
          flex-direction: column;
          gap: 5px;
          min-width: 0;
        }
        .select select {
          font-family: inherit;
          font-size: 11px;
          color: var(--text-secondary);
          background: var(--overlay-02);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          padding: 3px 6px;
          max-width: 190px;
        }
        .select select:hover {
          background: var(--overlay-05);
        }
        .clear {
          font-family: inherit;
          font-size: 11px;
          color: var(--text-muted);
          padding: 3px 8px;
          border: 1px solid var(--border-05);
          border-radius: 3px;
        }
        .clear:hover {
          color: var(--text-primary);
          background: var(--overlay-05);
        }
      `}</style>
    </section>
  );
}
