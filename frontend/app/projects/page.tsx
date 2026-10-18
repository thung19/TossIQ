"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import {
  API_BASE,
  PROJECT_STATUS_LABEL,
  apiFetch,
  apiPost,
  type Initiative,
  type InitiativeReport,
  type Project,
  type ProjectStatus,
} from "../../lib/api";

/**
 * The work. Specific actions, each one serving an initiative.
 *
 * Grouped by goal rather than listed flat, because a project's only reason
 * to exist is the target it moves -- an action nobody can trace to a goal
 * is either someone's pet task or evidence of a goal nobody wrote down, and
 * both are worth noticing. Projects with no initiative are shown in their
 * own group rather than hidden, for exactly that reason.
 */

const STATUSES: ProjectStatus[] = ["proposed", "in_progress", "blocked", "done", "cancelled"];
const BOARD_ORDER: ProjectStatus[] = ["in_progress", "blocked", "proposed", "done"];

const EMPTY_FORM = {
  initiative_id: "",
  name: "",
  description: "",
  owner: "facilities-ops@vanderbilt.edu",
  due_date: "",
  expected_impact: "",
  expected_impact_note: "",
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "all">("all");
  const [grouped, setGrouped] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const [projectList, report] = await Promise.all([
          apiFetch<Project[]>("/projects"),
          apiFetch<InitiativeReport>("/initiatives"),
        ]);
        if (!alive) return;
        setProjects(projectList);
        setInitiatives(report.initiatives);
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

  const setStatus = useCallback(async (projectId: number, status: string) => {
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setRefreshToken((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not update");
    }
  }, []);

  const submit = useCallback(async () => {
    if (!form.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost("/projects", {
        initiative_id: form.initiative_id ? Number(form.initiative_id) : null,
        name: form.name.trim(),
        description: form.description.trim() || null,
        owner: form.owner.trim() || null,
        status: "proposed",
        expected_impact: form.expected_impact ? Number(form.expected_impact) : null,
        expected_impact_note: form.expected_impact_note.trim() || null,
        due_date: form.due_date || null,
      });
      setForm({ ...EMPTY_FORM });
      setCreating(false);
      setRefreshToken((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not create the project");
    } finally {
      setBusy(false);
    }
  }, [form]);

  const shown = useMemo(
    () => projects.filter((p) => statusFilter === "all" || p.status === statusFilter),
    [projects, statusFilter]
  );

  const groups = useMemo(() => {
    const byInitiative = new Map<number | null, Project[]>();
    for (const project of shown) {
      const key = project.initiative_id ?? null;
      byInitiative.set(key, [...(byInitiative.get(key) ?? []), project]);
    }
    const names = new Map(initiatives.map((i) => [i.initiative_id, i]));
    const entries = [...byInitiative.entries()].map(([id, items]) => ({
      id,
      initiative: id == null ? null : names.get(id) ?? null,
      items,
    }));
    // Unassigned last: it is the exception, and leading with it would make
    // the page look like a flat task list.
    entries.sort((a, b) => (a.id == null ? 1 : 0) - (b.id == null ? 1 : 0));
    return entries;
  }, [shown, initiatives]);

  const counts = useMemo(() => {
    const tally: Record<string, number> = {};
    for (const project of projects) tally[project.status] = (tally[project.status] ?? 0) + 1;
    return tally;
  }, [projects]);

  const overdue = projects.filter(
    (p) =>
      p.due_date &&
      p.status !== "done" &&
      p.status !== "cancelled" &&
      new Date(p.due_date) < new Date()
  ).length;

  return (
    <>
      <PageHeader
        breadcrumb="Workspace"
        title="Projects"
        right={
          <span className="header-meta">
            <span>{projects.length} total</span>
            <span className="dim">
              · {counts.in_progress ?? 0} in progress · {counts.done ?? 0} done
            </span>
          </span>
        }
      />

      <div className="page">
        <section className="kpis">
          <StatCard label="in progress" value={counts.in_progress ?? 0} />
          <StatCard label="blocked" value={counts.blocked ?? 0} />
          <StatCard label="proposed" value={counts.proposed ?? 0} />
          <StatCard label="done" value={counts.done ?? 0} />
          <StatCard label="past due" value={overdue} delta={overdue > 0 ? "not yet done" : undefined} />
        </section>

        <section className="controls">
          <button className="chip primary" onClick={() => setCreating((v) => !v)}>
            {creating ? "cancel" : "+ new project"}
          </button>
          <span className="divider" />
          <button
            className={`chip ${statusFilter === "all" ? "on" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            all {projects.length}
          </button>
          {STATUSES.map((status) =>
            counts[status] ? (
              <button
                key={status}
                className={`chip ${statusFilter === status ? "on" : ""}`}
                onClick={() => setStatusFilter(status)}
              >
                {PROJECT_STATUS_LABEL[status]} {counts[status]}
              </button>
            ) : null
          )}
          <span className="divider" />
          <button className={`chip ${grouped ? "on" : ""}`} onClick={() => setGrouped((v) => !v)}>
            {grouped ? "grouped by goal" : "flat list"}
          </button>
          <span className="spacer" />
          {error && <span className="err">{error}</span>}
        </section>

        {creating && (
          <section className="form">
            <div className="form-grid">
              <label className="wide">
                <span>Action</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Install refill stations in Rand and Commons"
                />
              </label>
              <label>
                <span>Serves which goal</span>
                <select
                  value={form.initiative_id}
                  onChange={(e) => setForm({ ...form, initiative_id: e.target.value })}
                >
                  <option value="">none yet</option>
                  {initiatives.map((i) => (
                    <option key={i.initiative_id} value={i.initiative_id}>
                      {i.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Owner</span>
                <input
                  value={form.owner}
                  onChange={(e) => setForm({ ...form, owner: e.target.value })}
                />
              </label>
              <label className="wide">
                <span>What it involves</span>
                <input
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </label>
              <label>
                <span>Due</span>
                <input
                  type="date"
                  value={form.due_date}
                  onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                />
              </label>
              <label>
                <span>Expected impact</span>
                <input
                  type="number"
                  value={form.expected_impact}
                  onChange={(e) => setForm({ ...form, expected_impact: e.target.value })}
                  placeholder="in the goal's units"
                />
              </label>
            </div>
            <p className="help dim">
              Expected impact is an estimate of what this action will contribute. It is shown
              beside the goal&rsquo;s measured progress and never added to it.
            </p>
            <div className="form-actions">
              <button
                className="chip primary"
                onClick={submit}
                disabled={busy || !form.name.trim()}
              >
                {busy ? "creating…" : "create project"}
              </button>
            </div>
          </section>
        )}

        {shown.length === 0 ? (
          <p className="empty">
            {projects.length === 0
              ? "No projects yet. A project is a specific action that moves an initiative, create one here, or from a card on the recommendations page."
              : "No projects in this status."}
          </p>
        ) : grouped ? (
          <section className="groups">
            {groups.map((group) => (
              <section key={String(group.id)} className="group">
                <header>
                  {group.initiative ? (
                    <>
                      <Link href="/initiatives" className="g-name">
                        {group.initiative.name}
                      </Link>
                      <span className="g-meta">
                        {group.initiative.metric_label} ·{" "}
                        {group.initiative.progress_percent != null
                          ? `${group.initiative.progress_percent.toFixed(0)}% of the way`
                          : "not measurable"}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="g-name orphan">Not tied to a goal</span>
                      <span className="g-meta">
                        Either somebody&rsquo;s pet task, or a goal nobody wrote down
                      </span>
                    </>
                  )}
                  <span className="g-count">{group.items.length}</span>
                </header>
                {group.items.map((project) => (
                  <ProjectRow key={project.project_id} project={project} onStatus={setStatus} />
                ))}
              </section>
            ))}
          </section>
        ) : (
          <section className="group">
            {BOARD_ORDER.flatMap((status) =>
              shown.filter((p) => p.status === status)
            ).map((project) => (
              <ProjectRow
                key={project.project_id}
                project={project}
                onStatus={setStatus}
                showInitiative
              />
            ))}
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
          gap: 5px;
          flex-wrap: wrap;
          padding: 8px 10px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
        }
        .divider {
          width: 1px;
          height: 15px;
          background: var(--border-08);
          margin: 0 3px;
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
          padding: 3px 9px;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          color: var(--text-muted);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .chip:hover:not(:disabled) {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.on,
        .chip.primary {
          background: var(--overlay-08);
          border-color: var(--border-solid);
          color: var(--text-primary);
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
          grid-template-columns: repeat(3, minmax(0, 1fr));
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
        }
        .help.dim {
          color: var(--text-dim);
        }
        .form-actions {
          display: flex;
          gap: 6px;
        }
        .empty {
          padding: 22px 12px;
          color: var(--text-dim);
          font-size: 12px;
          line-height: 18px;
          max-width: 620px;
        }
        .groups {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .group {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          overflow: hidden;
        }
        .group header {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 8px 10px;
          border-bottom: 1px solid var(--border-05);
        }
        .group header :global(.g-name) {
          font-size: 12.5px;
          font-weight: 510;
          color: var(--text-primary);
        }
        .group header :global(.g-name:hover) {
          color: var(--link);
          text-decoration: underline;
        }
        .g-name.orphan {
          color: var(--status-in-progress);
        }
        .g-meta {
          font-family: ui-monospace, Menlo, monospace;
          font-size: 9.5px;
          color: var(--text-dim);
        }
        .g-count {
          margin-left: auto;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          color: var(--text-muted);
        }
        @media (max-width: 1240px) {
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

function ProjectRow({
  project,
  onStatus,
  showInitiative = false,
}: {
  project: Project;
  onStatus: (projectId: number, status: string) => void;
  showInitiative?: boolean;
}) {
  const late =
    project.due_date &&
    project.status !== "done" &&
    project.status !== "cancelled" &&
    new Date(project.due_date) < new Date();

  return (
    <div className={`row ${project.status}`}>
      <span className={`dot ${project.status}`} />
      <span className="main">
        <span className="name">{project.name}</span>
        {project.description && <span className="desc">{project.description}</span>}
        <span className="tags">
          {showInitiative && project.initiative_name && (
            <span className="tag goal">{project.initiative_name}</span>
          )}
          {project.source_recommendation_key && (
            <span className="tag rec">from a recommendation</span>
          )}
          {project.expected_impact != null && (
            <span className="tag impact">
              claims {project.expected_impact.toLocaleString()}
              {project.expected_impact_note ? `, ${project.expected_impact_note}` : ""}
            </span>
          )}
        </span>
      </span>
      <span className="owner">{project.owner ?? "unassigned"}</span>
      <span className={`due ${late ? "late" : ""}`}>
        {project.due_date ?? "-"}
        {late && <span className="late-tag">overdue</span>}
      </span>
      <select value={project.status} onChange={(e) => onStatus(project.project_id, e.target.value)}>
        {STATUSES.map((status) => (
          <option key={status} value={status}>
            {PROJECT_STATUS_LABEL[status]}
          </option>
        ))}
      </select>

      <style jsx>{`
        .row {
          display: grid;
          grid-template-columns: 8px minmax(0, 1fr) 170px 100px 112px;
          align-items: start;
          gap: 10px;
          padding: 8px 10px;
          border-top: 1px solid var(--border-05);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        .row:hover {
          background: var(--overlay-02);
        }
        .row.done,
        .row.cancelled {
          opacity: 0.55;
        }
        .dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          margin-top: 5px;
          background: var(--text-dim);
        }
        .dot.in_progress {
          background: var(--primary);
        }
        .dot.blocked {
          background: var(--status-bug);
        }
        .dot.done {
          background: var(--status-done);
        }
        .dot.proposed {
          background: var(--status-in-progress);
        }
        .main {
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }
        .name {
          color: var(--text-primary);
          font-size: 12px;
        }
        .desc {
          color: var(--text-dim);
          font-size: 10px;
          line-height: 14px;
        }
        .tags {
          display: flex;
          flex-wrap: wrap;
          gap: 5px;
          margin-top: 2px;
        }
        .tag {
          font-size: 9px;
          line-height: 14px;
          padding: 0 5px;
          border-radius: 2px;
          border: 1px solid var(--border-08);
          color: var(--text-dim);
        }
        .tag.goal {
          color: var(--text-muted);
        }
        .tag.rec {
          color: var(--mention-text);
          border-color: var(--mention-bg);
        }
        .tag.impact {
          color: var(--cat-compost);
        }
        .owner,
        .due {
          color: var(--text-dim);
          font-size: 10px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .due.late {
          color: var(--status-bug);
        }
        .late-tag {
          display: block;
          font-size: 9px;
        }
        select {
          font-family: inherit;
          font-size: 10px;
          color: var(--text-secondary);
          background: var(--overlay-05);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 2px 4px;
          cursor: pointer;
        }
        option {
          background: var(--bg-elevated);
        }
      `}</style>
    </div>
  );
}
