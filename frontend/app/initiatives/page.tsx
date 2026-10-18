"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import InitiativeCard from "../components/InitiativeCard";
import {
  API_BASE,
  apiFetch,
  apiPost,
  formatMetric,
  type AnalyticsFilterOptions,
  type Building,
  type InitiativeReport,
  type MetricSpec,
} from "../../lib/api";

/**
 * Goals, measured against the data rather than tracked by hand.
 *
 * The thing this page is careful about is the difference between a measured
 * figure and a claimed one. Progress comes from recomputing each goal's
 * metric over its own scope every time the page loads; project impact is
 * what the work says it will contribute and is shown separately, never
 * added. A goal is met when the disposals say so.
 *
 * Creating a goal does not let you supply a baseline. The server measures
 * it, because a starting point you can type is a starting point you can
 * flatter.
 */

const DEFAULT_FORM = {
  name: "",
  description: "",
  owner: "sustainability@vanderbilt.edu",
  metric: "items",
  direction: "reduce",
  scope_building_id: "",
  scope_category: "",
  scope_material: "",
  scope_object: "",
  target_value: "",
  target_date: "",
  baseline_window_days: "30",
};

export default function InitiativesPage() {
  const [report, setReport] = useState<InitiativeReport | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [options, setOptions] = useState<AnalyticsFilterOptions | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ ...DEFAULT_FORM });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const next = await apiFetch<InitiativeReport>("/initiatives");
        if (!alive) return;
        setReport(next);
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
  }, [refreshToken]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [buildingList, filterOptions] = await Promise.all([
          apiFetch<Building[]>("/buildings"),
          apiFetch<AnalyticsFilterOptions>("/analytics/filters?days=90"),
        ]);
        if (!alive) return;
        setBuildings(buildingList);
        setOptions(filterOptions);
      } catch {
        /* the form still works with free-text scope left empty */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const metrics = report?.metrics ?? {};
  const spec: MetricSpec | undefined = metrics[form.metric];

  // Direction follows the metric's natural sense when the metric changes,
  // but stays editable: a campus might want its compost tonnage up.
  const onMetric = (metric: string) => {
    const next = metrics[metric];
    setForm((f) => ({
      ...f,
      metric,
      direction: next ? (next.lower_is_better ? "reduce" : "increase") : f.direction,
    }));
  };

  const submit = useCallback(async () => {
    // A deadline is required, not optional: an open-ended goal is the
    // "cut it sometime over the next decade" problem.
    if (!form.name.trim() || !form.target_value || !form.target_date) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost("/initiatives", {
        name: form.name.trim(),
        description: form.description.trim() || null,
        owner: form.owner.trim() || null,
        metric: form.metric,
        direction: form.direction,
        scope_building_id: form.scope_building_id ? Number(form.scope_building_id) : null,
        scope_category: form.scope_category || null,
        scope_material: form.scope_material || null,
        scope_object: form.scope_object || null,
        target_value: Number(form.target_value),
        target_date: form.target_date,
        baseline_window_days: Number(form.baseline_window_days),
      });
      setForm({ ...DEFAULT_FORM });
      setCreating(false);
      setRefreshToken((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not create the goal");
    } finally {
      setBusy(false);
    }
  }, [form]);

  const setProjectStatus = useCallback(async (projectId: number, status: string) => {
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setRefreshToken((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not update the project");
    }
  }, []);

  const initiatives = report?.initiatives ?? [];
  const activeCount = initiatives.filter((item) => item.status === "active").length;

  const metricEntries = useMemo(() => Object.entries(metrics), [metrics]);

  return (
    <>
      <PageHeader
        breadcrumb="Workspace"
        title="Initiatives"
        right={
          <span className="header-meta">
            {report ? (
              <>
                <span>{activeCount} active</span>
                <span className="dim">· {report.total} total</span>
              </>
            ) : (
              <span className="dim">{error ? "unavailable — retrying" : "loading…"}</span>
            )}
          </span>
        }
      />

      <div className="page">
        <section className="kpis">
          <StatCard label="active goals" value={activeCount || "—"} />
          <StatCard label="achieved" value={report?.achieved ?? "—"} />
          <StatCard
            label="losing ground"
            value={report?.regressing ?? "—"}
            delta={report && report.regressing > 0 ? "worse than baseline" : undefined}
          />
          <StatCard
            label="no projects yet"
            value={report?.unbacked.length ?? "—"}
            delta="goals with no work behind them"
          />
          <StatCard
            label="behind pace"
            value={report?.behind_pace.length ?? "—"}
            delta="won't land on current rate"
          />
        </section>

        <section className="controls">
          <button className="chip primary" onClick={() => setCreating((v) => !v)}>
            {creating ? "cancel" : "+ new goal"}
          </button>
          <span className="spacer" />
          {error && <span className="err">{error}</span>}
        </section>

        {creating && (
          <section className="form">
            <div className="form-grid">
              <label className="wide">
                <span>Goal</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Cut bottled water in the Library"
                />
              </label>
              <label className="wide">
                <span>Why</span>
                <input
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="What this is for, and how you will know it worked"
                />
              </label>

              <label>
                <span>Measure</span>
                <select value={form.metric} onChange={(e) => onMetric(e.target.value)}>
                  {metricEntries.map(([key, value]) => (
                    <option key={key} value={key}>
                      {value.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Direction</span>
                <select
                  value={form.direction}
                  onChange={(e) => setForm({ ...form, direction: e.target.value })}
                >
                  <option value="reduce">reduce it</option>
                  <option value="increase">increase it</option>
                </select>
              </label>
              <label>
                <span>Target {spec ? `(${spec.unit})` : ""}</span>
                <input
                  type="number"
                  value={form.target_value}
                  onChange={(e) => setForm({ ...form, target_value: e.target.value })}
                  placeholder="0"
                />
              </label>
              <label>
                <span>By when (required)</span>
                <input
                  type="date"
                  value={form.target_date}
                  onChange={(e) => setForm({ ...form, target_date: e.target.value })}
                />
              </label>
              <label>
                <span>Measured over</span>
                <select
                  value={form.baseline_window_days}
                  onChange={(e) =>
                    setForm({ ...form, baseline_window_days: e.target.value })
                  }
                >
                  <option value="7">a rolling 7 days</option>
                  <option value="30">a rolling 30 days</option>
                  <option value="90">a rolling 90 days</option>
                </select>
              </label>

              <label>
                <span>Building</span>
                <select
                  value={form.scope_building_id}
                  onChange={(e) => setForm({ ...form, scope_building_id: e.target.value })}
                >
                  <option value="">campus-wide</option>
                  {buildings.map((b) => (
                    <option key={b.building_id} value={b.building_id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Stream</span>
                <select
                  value={form.scope_category}
                  onChange={(e) => setForm({ ...form, scope_category: e.target.value })}
                >
                  <option value="">any</option>
                  {(options?.categories ?? []).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Material</span>
                <select
                  value={form.scope_material}
                  onChange={(e) => setForm({ ...form, scope_material: e.target.value })}
                >
                  <option value="">any</option>
                  {(options?.materials ?? []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Item</span>
                <select
                  value={form.scope_object}
                  onChange={(e) => setForm({ ...form, scope_object: e.target.value })}
                >
                  <option value="">any</option>
                  {(options?.objects ?? []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {spec && <p className="help">{spec.help}</p>}
            <p className="help dim">
              The baseline is measured from the last 30 days when you save, not entered here.
              A starting point you can type is a starting point you can flatter. If the slice
              you pick turns out to produce almost nothing, the goal is flagged rather than
              shown as a tidy percentage &mdash; a target that noise can hit is not a target.
            </p>
            <p className="help dim">
              Every figure is a rate over the window you choose: a target of 120 means 120 per
              30 days, not 120 ever. The deadline is required, because without one a goal is
              permanently on track and never finished.
            </p>

            <div className="form-actions">
              <button
                className="chip primary"
                onClick={submit}
                disabled={busy || !form.name.trim() || !form.target_value || !form.target_date}
              >
                {busy ? "measuring baseline…" : "create goal"}
              </button>
            </div>
          </section>
        )}

        {report && report.undated.length > 0 && (
          <p className="nudge">
            {report.undated.length} goal{report.undated.length === 1 ? " has" : "s have"} no
            target date: {report.undated.map((item) => item.name).join(", ")}. Without a
            deadline a goal is permanently on track and never finished.
          </p>
        )}

        {report && report.immaterial.length > 0 && (
          <p className="nudge">
            {report.immaterial.length} goal
            {report.immaterial.length === 1 ? " measures" : "s measure"} a slice too small
            for a target to mean anything:{" "}
            {report.immaterial.map((item) => item.name).join(", ")}. Widen the scope or
            pick a measure with more behind it.
          </p>
        )}

        {report && report.unbacked.length > 0 && (
          <p className="nudge">
            {report.unbacked.length} active goal
            {report.unbacked.length === 1 ? "" : "s"} have no project behind them:{" "}
            {report.unbacked.map((item) => item.name).join(", ")}. A target with no action
            will not move on its own.
          </p>
        )}

        {!report ? (
          <p className="empty">
            {error ? `Could not reach the service (${error}). Retrying.` : "Measuring goals…"}
          </p>
        ) : initiatives.length === 0 ? (
          <p className="empty">
            No goals yet. Create one and TossIQ will measure it against logged disposals from
            then on &mdash; pick what to measure, over which slice of the campus, and what you
            are aiming for.
          </p>
        ) : (
          <section className="cards">
            {initiatives.map((item) => (
              <InitiativeCard
                key={item.initiative_id}
                initiative={item}
                expanded={openId === item.initiative_id}
                onToggle={() =>
                  setOpenId(openId === item.initiative_id ? null : item.initiative_id)
                }
                onProjectStatus={setProjectStatus}
              />
            ))}
          </section>
        )}

        {report && (
          <section className="footnote">
            <header>how progress is measured</header>
            <p>{report.note}</p>
          </section>
        )}
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
        .controls {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .spacer {
          flex: 1;
        }
        .err {
          color: var(--status-bug);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10px;
        }
        .chip {
          padding: 4px 11px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          color: var(--text-muted);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .chip:hover:not(:disabled) {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.primary {
          color: var(--text-primary);
          background: var(--overlay-08);
          border-color: var(--border-solid);
        }
        .chip.primary:hover:not(:disabled) {
          background: var(--primary);
        }
        .chip:disabled {
          color: var(--text-dim);
          cursor: default;
        }
        .form {
          display: flex;
          flex-direction: column;
          gap: 9px;
          padding: 12px;
          background: var(--bg-surface);
          border: 1px solid var(--primary);
          border-radius: 4px;
        }
        .form-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }
        .form-grid :global(label.wide) {
          grid-column: span 2;
        }
        label {
          display: flex;
          flex-direction: column;
          gap: 3px;
          min-width: 0;
        }
        label span {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
        }
        input,
        select {
          width: 100%;
          padding: 5px 7px;
          background: var(--bg-card);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          color: var(--text-primary);
          font-size: 12px;
        }
        input::placeholder {
          color: var(--text-dim);
        }
        option {
          background: var(--bg-elevated);
        }
        .help {
          font-size: 10.5px;
          line-height: 15px;
          color: var(--text-muted);
        }
        .help.dim {
          color: var(--text-dim);
        }
        .form-actions {
          display: flex;
          gap: 6px;
        }
        .nudge {
          padding: 7px 10px;
          border: 1px solid var(--status-in-progress);
          border-radius: 3px;
          color: var(--status-in-progress);
          font-size: 11px;
          line-height: 16px;
        }
        .empty {
          padding: 22px 12px;
          color: var(--text-dim);
          font-size: 12px;
          line-height: 18px;
          max-width: 620px;
        }
        .cards {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          align-items: start;
        }
        .footnote {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-size: 10.5px;
          line-height: 15px;
        }
        .footnote header {
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10px;
        }
        .footnote p {
          padding: 7px 10px;
          color: var(--text-muted);
        }
        @media (max-width: 1240px) {
          .cards {
            grid-template-columns: 1fr;
          }
          .kpis {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
          .form-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
      `}</style>
    </>
  );
}
