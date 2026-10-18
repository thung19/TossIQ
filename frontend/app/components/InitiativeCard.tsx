"use client";

import { PACE_LABEL, formatMetric, periodLabel, type Initiative } from "../../lib/api";

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
  const period = periodLabel(initiative.baseline_window_days);
  const percent = initiative.progress_percent ?? 0;
  const drawn = Math.max(0, Math.min(100, percent));
  const regressing = percent < 0;

  return (
    <article className={`card ${initiative.progress_state} ${expanded ? "open" : ""}`}>
      <button className="head" onClick={onToggle} aria-expanded={expanded}>
        <span className="top">
          <span className={`state pace-${initiative.pace_state}`}>
            {PACE_LABEL[initiative.pace_state] ?? initiative.pace_state}
          </span>
          <span className="scope">{initiative.scope_label}</span>
          {initiative.status !== "active" && (
            <span className="status-tag">{initiative.status}</span>
          )}
          {initiative.measurement_warning && (
            <span className="too-small" title={initiative.measurement_warning}>
              counts mixed items
            </span>
          )}
          {!initiative.is_material && (
            <span className="too-small" title={initiative.materiality_note ?? undefined}>
              too small to mean much
            </span>
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
        {/* The period rides on the number itself. "381 to 117" with the
            window printed separately reads as a running total, and a
            reader has to assemble the rate from two places to understand
            the goal at all. */}
        <p className="metric-line">
          {initiative.metric_label}, {initiative.direction === "reduce" ? "reduce" : "lift"}{" "}
          from <b>{formatMetric(baseline, format)}{period}</b> to{" "}
          <b>{formatMetric(target, format)}{period}</b>
        </p>

        <span className="bar-wrap">
          <span className="bar-track">
            <span
              className={`bar-fill ${regressing ? "bad" : ""}`}
              style={{ width: `${drawn}%` }}
            />
          </span>
          <span className="bar-ends">
            <span>{formatMetric(baseline, format)}{period}</span>
            <span className={`now ${regressing ? "bad" : ""}`}>
              now {formatMetric(current, format)}{period}
              {initiative.progress_percent != null && (
                <b> · {initiative.progress_percent.toFixed(0)}%</b>
              )}
            </span>
            <span>{formatMetric(target, format)}{period}</span>
          </span>
        </span>

        <span className="forecast">
          {initiative.pace_state === "no_deadline" ? (
            <span className="warn">
              No target date. A goal with no deadline is permanently on track and never
              finished.
            </span>
          ) : initiative.projected_hits_target === true ? (
            <span className="good">
              At this rate, hits target around <b>{initiative.projected_completion}</b>
              {initiative.target_date && ` · due ${initiative.target_date}`}
            </span>
          ) : initiative.projected_hits_target === false ? (
            <span className="bad">
              At this rate, lands at{" "}
              <b>
                {formatMetric(initiative.projected_value, format)}
                {period}
              </b>{" "}
              by {initiative.target_date}, short of {formatMetric(target, format)}
              {period}
            </span>
          ) : (
            <span className="dim">Too early to forecast an outcome</span>
          )}
          {initiative.elapsed_percent != null && (
            <span className="dim">
              {initiative.progress_percent?.toFixed(0)}% done ·{" "}
              {initiative.elapsed_percent.toFixed(0)}% of the time gone
            </span>
          )}
        </span>

        <span className="foot">
          {initiative.project_count === 0 ? (
            <span className="warn">no projects yet, this is a wish, not a plan</span>
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
          {initiative.measurement_warning && (
            <p className="small-warn">{initiative.measurement_warning}</p>
          )}
          {!initiative.is_material && initiative.materiality_note && (
            <p className="small-warn">{initiative.materiality_note}</p>
          )}

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
            <Fact
              label="Measured over"
              value={`${initiative.baseline_window_days} days`}
              hint="a rolling window, so every figure is a rate"
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
                  {formatMetric(initiative.claimed_impact, format)} claimed by work under way, an estimate, not counted towards the measured figure above
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
                  <span className="pdue">{project.due_date ?? "-"}</span>
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
        .state.pace-achieved,
        .state.pace-ahead {
          color: var(--status-done);
        }
        .state.pace-on_track {
          color: var(--cat-recycling);
        }
        .state.pace-behind {
          color: var(--status-in-progress);
        }
        .state.pace-at_risk,
        .state.pace-regressing {
          color: var(--status-bug);
        }
        .state.pace-no_deadline {
          color: var(--status-in-progress);
          border-style: dashed;
        }
        .scope,
        .due,
        .status-tag {
          color: var(--text-dim);
        }
        .too-small {
          padding: 0 5px;
          line-height: 14px;
          border-radius: 2px;
          border: 1px dashed var(--status-in-progress);
          color: var(--status-in-progress);
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
        .per {
          color: var(--text-dim);
          font-size: 10.5px;
        }
        .forecast {
          display: flex;
          flex-direction: column;
          gap: 1px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10px;
          line-height: 14px;
        }
        .forecast .good {
          color: var(--status-done);
        }
        .forecast .bad {
          color: var(--status-bug);
        }
        .forecast .warn {
          color: var(--status-in-progress);
        }
        .forecast b {
          font-weight: 510;
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
        .small-warn {
          padding: 8px 10px;
          border: 1px solid var(--status-in-progress);
          border-radius: 3px;
          color: var(--status-in-progress);
          font-size: 11px;
          line-height: 16px;
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
