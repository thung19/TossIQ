"use client";

import { PROGRESS_LABEL, formatMetric, type Initiative } from "../../lib/api";

/**
 * One goal, with the distance it has actually travelled.
 *
 * The bar runs baseline to target, not zero to current. A reduction goal
 * drawn from zero would fill up as things got worse, and "cut bottled water
 * to 16 from 53" has no sensible meaning on a 0-100 scale of its own value.
 * Baseline on the left, target on the right, a marker where you are now.
 *
 * Claimed impact from projects sits apart from measured progress and is
 * never added to it. A goal is met when the data says so, not when enough
 * optimistic estimates have been filed against it.
 */
export default function InitiativeCard({
  initiative,
  expanded,
  onToggle,
  onProjectStatus,
}: {
  initiative: Initiative;
  expanded: boolean;
  onToggle: () => void;
  onProjectStatus: (projectId: number, status: string) => void;
}) {
  const {
    baseline_value: baseline,
    target_value: target,
    current_value: current,
    format,
  } = initiative;

  // Where the current value sits between baseline and target, clamped for
  // drawing only -- the number beside it is never clamped.
  const percent = initiative.progress_percent ?? 0;
  const drawn = Math.max(0, Math.min(100, percent));
  const regressing = percent < 0;

  return (
    <article className={`card ${initiative.progress_state} ${expanded ? "open" : ""}`}>
      <button className="head" onClick={onToggle} aria-expanded={expanded}>
        <span className="top">
          <span className={`state ${initiative.progress_state}`}>
            {PROGRESS_LABEL[initiative.progress_state]}
          </span>
          <span className="scope">{initiative.scope_label}</span>
          {initiative.status !== "active" && (
            <span className="status-tag">{initiative.status}</span>
          )}
          <span className="spacer" />
          {initiative.days_remaining != null && (
            <span className={`due ${initiative.days_remaining < 0 ? "late" : ""}`}>
              {initiative.days_remaining < 0
                ? `${-initiative.days_remaining}d overdue`
                : `${initiative.days_remaining}d left`}
            </span>
          )}
        </span>

        <h3>{initiative.name}</h3>
        <p className="metric-line">
          {initiative.metric_label} &mdash; {initiative.direction === "reduce" ? "reduce" : "lift"}{" "}
          from <b>{formatMetric(baseline, format)}</b> to <b>{formatMetric(target, format)}</b>
        </p>

        <span className="bar-wrap">
          <span className="bar-track">
            <span
              className={`bar-fill ${regressing ? "bad" : ""}`}
              style={{ width: `${drawn}%` }}
            />
          </span>
          <span className="bar-ends">
            <span>{formatMetric(baseline, format)}</span>
            <span className={`now ${regressing ? "bad" : ""}`}>
              now {formatMetric(current, format)}
              {initiative.progress_percent != null && (
                <b> · {initiative.progress_percent.toFixed(0)}%</b>
              )}
            </span>
            <span>{formatMetric(target, format)}</span>
          </span>
        </span>

        <span className="foot">
          {initiative.project_count === 0 ? (
            <span className="warn">no projects yet &mdash; this is a wish, not a plan</span>
          ) : (
            <span>
              {initiative.projects_done} of {initiative.project_count} project
              {initiative.project_count === 1 ? "" : "s"} done
              {initiative.projects_active > 0 && `, ${initiative.projects_active} in progress`}
            </span>
          )}
          <span className="dim">click to see the work</span>
        </span>
      </button>

      {expanded && (
        <div className="body">
          {initiative.description && <p className="desc">{initiative.description}</p>}

          <div className="facts">
            <Fact label="Metric" value={initiative.metric_label} hint={initiative.metric_help} />
            <Fact label="Scope" value={initiative.scope_label} />
            <Fact
              label="Baseline"
              value={formatMetric(baseline, format)}
              hint={
                initiative.baseline_captured_at
                  ? `captured ${initiative.baseline_captured_at.slice(0, 10)}, over ${initiative.baseline_window_days}d`
                  : undefined
              }
            />
            <Fact
              label="Still to go"
              value={formatMetric(
                initiative.distance_to_target == null
                  ? null
                  : Math.abs(initiative.distance_to_target),
                format
              )}
              hint={initiative.direction === "reduce" ? "further reduction" : "further gain"}
            />
            <Fact label="Owner" value={initiative.owner ?? "unassigned"} />
            <Fact
              label="Target date"
              value={initiative.target_date ?? "open-ended"}
            />
          </div>

          <div className="projects">
            <header>
              projects
              {initiative.claimed_impact > 0 && (
                <span className="claimed">
                  {formatMetric(initiative.claimed_impact, format)} claimed by work under way
                  &mdash; an estimate, not counted towards the measured figure above
                </span>
              )}
            </header>
            {initiative.projects.length === 0 ? (
              <p className="empty">
                Nothing is being done about this yet. A target with no action behind it will
                not move on its own.
              </p>
            ) : (
              initiative.projects.map((project) => (
                <div key={project.project_id} className={`project ${project.status}`}>
                  <span className={`pstate ${project.status}`}>
                    {project.status.replace("_", " ")}
                  </span>
                  <span className="pname">
                    {project.name}
                    {project.source_recommendation_key && (
                      <span className="from-rec">from a recommendation</span>
                    )}
                  </span>
                  <span className="pdue">{project.due_date ?? "—"}</span>
                  <select
                    value={project.status}
                    onChange={(e) => onProjectStatus(project.project_id, e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {["proposed", "in_progress", "blocked", "done", "cancelled"].map((s) => (
                      <option key={s} value={s}>
                        {s.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .card {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-left-width: 3px;
          border-radius: 4px;
          min-width: 0;
          overflow: hidden;
        }
        .card.achieved {
          border-left-color: var(--status-done);
        }
        .card.near_target {
          border-left-color: var(--cat-recycling);
        }
        .card.in_progress {
          border-left-color: var(--primary);
        }
        .card.off_track {
          border-left-color: var(--status-in-progress);
        }
        .card.regressing {
          border-left-color: var(--status-bug);
        }
        .card.open {
          border-color: var(--primary);
          border-left-color: var(--primary);
        }
        .head {
          display: flex;
          flex-direction: column;
          gap: 7px;
          padding: 11px 13px 12px;
          text-align: left;
          width: 100%;
        }
        .top {
          display: flex;
          align-items: center;
          gap: 7px;
          flex-wrap: wrap;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
        }
        .state {
          padding: 0 6px;
          line-height: 15px;
          border-radius: 2px;
          border: 1px solid currentColor;
          color: var(--text-muted);
        }
        .state.achieved {
          color: var(--status-done);
        }
        .state.near_target {
          color: var(--cat-recycling);
        }
        .state.in_progress {
          color: var(--primary);
        }
        .state.off_track {
          color: var(--status-in-progress);
        }
        .state.regressing {
          color: var(--status-bug);
        }
        .scope,
        .due,
        .status-tag {
          color: var(--text-dim);
        }
        .due.late {
          color: var(--status-bug);
        }
        .spacer {
          flex: 1;
        }
        h3 {
          font-size: 13.5px;
          font-weight: 510;
          line-height: 18px;
          color: var(--text-primary);
        }
        .metric-line {
          font-size: 11.5px;
          line-height: 16px;
          color: var(--text-muted);
        }
        .metric-line b {
          color: var(--text-secondary);
          font-weight: 510;
          font-variant-numeric: tabular-nums;
        }
        .bar-wrap {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .bar-track {
          height: 8px;
          background: var(--overlay-05);
          border-radius: 4px;
          overflow: hidden;
        }
        .bar-fill {
          display: block;
          height: 100%;
          background: var(--primary);
          border-radius: 4px;
        }
        .card.achieved .bar-fill {
          background: var(--status-done);
        }
        .bar-fill.bad {
          background: var(--status-bug);
        }
        .bar-ends {
          display: flex;
          justify-content: space-between;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
        }
        .now {
          color: var(--text-secondary);
        }
        .now b {
          color: var(--text-primary);
        }
        .now.bad,
        .now.bad b {
          color: var(--status-bug);
        }
        .foot {
          display: flex;
          justify-content: space-between;
          gap: 8px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-muted);
        }
        .warn {
          color: var(--status-in-progress);
        }
        .dim {
          color: var(--text-dim);
        }
        .body {
          padding: 0 13px 13px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .desc {
          font-size: 11.5px;
          line-height: 17px;
          color: var(--text-muted);
        }
        .facts {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
          gap: 6px;
        }
        .projects {
          background: var(--bg-card);
          border: 1px solid var(--border-05);
          border-radius: 3px;
        }
        .projects header {
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 7px 9px;
          border-bottom: 1px solid var(--border-05);
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
        }
        .claimed {
          color: var(--text-dim);
          opacity: 0.85;
        }
        .empty {
          padding: 10px 9px;
          font-size: 11px;
          line-height: 16px;
          color: var(--text-dim);
        }
        .project {
          display: grid;
          grid-template-columns: 78px minmax(0, 1fr) 78px 104px;
          align-items: center;
          gap: 8px;
          padding: 5px 9px;
          border-top: 1px solid var(--border-05);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .project.done {
          opacity: 0.6;
        }
        .pstate {
          font-size: 9px;
          color: var(--text-dim);
        }
        .pstate.in_progress {
          color: var(--primary);
        }
        .pstate.blocked {
          color: var(--status-bug);
        }
        .pstate.done {
          color: var(--status-done);
        }
        .pname {
          color: var(--text-secondary);
          display: flex;
          flex-direction: column;
          min-width: 0;
        }
        .from-rec {
          color: var(--mention-text);
          font-size: 9px;
        }
        .pdue {
          color: var(--text-dim);
          font-size: 9.5px;
        }
        select {
          font-family: inherit;
          font-size: 10px;
          color: var(--text-secondary);
          background: var(--overlay-05);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 1px 3px;
          cursor: pointer;
        }
        option {
          background: var(--bg-elevated);
        }
      `}</style>
    </article>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="fact">
      <span className="f-label">{label}</span>
      <span className="f-value">{value}</span>
      {hint && <span className="f-hint">{hint}</span>}
      <style jsx>{`
        .fact {
          display: flex;
          flex-direction: column;
          gap: 1px;
          padding: 6px 8px;
          background: var(--bg-card);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          min-width: 0;
          font-family: ui-monospace, Menlo, monospace;
        }
        .f-label {
          color: var(--text-dim);
          font-size: 9px;
        }
        .f-value {
          color: var(--text-primary);
          font-size: 11.5px;
          overflow-wrap: anywhere;
        }
        .f-hint {
          color: var(--text-dim);
          font-size: 9px;
          line-height: 12px;
        }
      `}</style>
    </div>
  );
}
