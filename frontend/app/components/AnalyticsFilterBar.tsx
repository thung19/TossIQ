"use client";

import {
  EMPTY_ANALYTICS_FILTERS,
  activeAnalyticsFilterCount,
  type AnalyticsFilterOptions,
  type AnalyticsFilterState,
  type Building,
  type Can,
} from "../../lib/api";

const WINDOWS = [7, 30, 90, 365];

/**
 * The one filter bar for the whole analytics page.
 *
 * Every section reads the same state, so narrowing to a building narrows the
 * composition, the hotspots, the supplies table and the accuracy sample
 * together. Two filters that would otherwise contradict each other are
 * linked: choosing a can clears the building, because a can already implies
 * one, and the can list is narrowed to the chosen building so the dropdown
 * cannot offer a combination that yields nothing.
 *
 * Options come from the API rather than a hardcoded list -- they are the
 * values actually present in the window, so no choice here can produce an
 * empty page.
 */
export default function AnalyticsFilterBar({
  value,
  onChange,
  options,
  buildings,
  cans,
}: {
  value: AnalyticsFilterState;
  onChange: (next: AnalyticsFilterState) => void;
  options: AnalyticsFilterOptions | null;
  buildings: Building[];
  cans: Can[];
}) {
  const set = (patch: Partial<AnalyticsFilterState>) => onChange({ ...value, ...patch });
  const activeCount = activeAnalyticsFilterCount(value);

  const cansInScope = value.buildingId
    ? cans.filter((can) => String(can.building_id) === value.buildingId)
    : cans;

  return (
    <section className="bar">
      <div className="group">
        <span className="k">window</span>
        {WINDOWS.map((days) => (
          <button
            key={days}
            className={`chip ${value.days === days ? "on" : ""}`}
            onClick={() => set({ days })}
          >
            {days === 365 ? "1y" : `${days}d`}
          </button>
        ))}
      </div>

      <Select
        label="building"
        value={value.buildingId}
        onChange={(buildingId) => set({ buildingId, canId: "" })}
        options={buildings.map((b) => ({ value: String(b.building_id), label: b.name }))}
        allLabel="all buildings"
      />

      <Select
        label="can"
        value={value.canId}
        // A can implies its building, so selecting one clears the building
        // filter rather than leaving two overlapping scopes on screen.
        onChange={(canId) => set({ canId, buildingId: "" })}
        options={cansInScope.map((c) => ({ value: String(c.can_id), label: c.can_code }))}
        allLabel="all cans"
      />

      <Select
        label="bin"
        value={value.category}
        onChange={(category) => set({ category })}
        options={(options?.categories ?? []).map((c) => ({ value: c, label: c }))}
        allLabel="all bins"
      />

      <Select
        label="material"
        value={value.material}
        onChange={(material) => set({ material })}
        options={(options?.materials ?? []).map((m) => ({ value: m, label: m }))}
        allLabel="all materials"
      />

      <Select
        label="item"
        value={value.detectedObject}
        onChange={(detectedObject) => set({ detectedObject })}
        options={(options?.objects ?? []).map((o) => ({ value: o, label: o }))}
        allLabel="all items"
      />

      <Select
        label="supplier"
        value={value.supplier}
        onChange={(supplier) => set({ supplier })}
        options={(options?.suppliers ?? []).map((s) => ({ value: s, label: s }))}
        allLabel="all suppliers"
      />

      {activeCount > 0 && (
        <button
          className="chip clear"
          onClick={() => onChange({ ...EMPTY_ANALYTICS_FILTERS, days: value.days })}
        >
          clear {activeCount}
        </button>
      )}

      <style jsx>{`
        .bar {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          padding: 8px 10px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .group {
          display: inline-flex;
          align-items: center;
          gap: 3px;
        }
        .k {
          color: var(--text-dim);
          font-size: 10px;
          margin-right: 2px;
        }
        .chip {
          padding: 2px 7px;
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
        .chip.clear {
          color: var(--mention-text);
          border-color: var(--mention-bg);
          margin-left: auto;
        }
      `}</style>
    </section>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  allLabel: string;
}) {
  return (
    <label className={`sel ${value ? "on" : ""}`}>
      <span className="k">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <style jsx>{`
        .sel {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 1px 5px 1px 7px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
        }
        .sel.on {
          border-color: var(--border-solid);
          background: var(--overlay-05);
        }
        .k {
          color: var(--text-dim);
          font-size: 10px;
        }
        select {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          line-height: 18px;
          color: var(--text-secondary);
          max-width: 148px;
          cursor: pointer;
        }
        .sel.on select {
          color: var(--text-primary);
        }
        option {
          background: var(--bg-elevated);
          color: var(--text-primary);
        }
      `}</style>
    </label>
  );
}
