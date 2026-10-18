"use client";

import { useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import RecommendationCard from "../components/RecommendationCard";
import {
  KIND_LABEL,
  apiFetch,
  type Recommendation,
  type RecommendationKind,
  type RecommendationReport,
} from "../../lib/api";

/**
 * What to do about the waste, ranked.
 *
 * Every card is generated from logged data by a rule in recommendations.py,
 * and carries the observations behind it. Opening one shows those
 * observations -- the counts, the arithmetic, the cans -- so the operator
 * can disagree with the reasoning rather than only with the conclusion.
 *
 * Deliberately not a chat or a generated paragraph. These are claims about
 * money and rotas, and a claim worth acting on has to be auditable; a
 * sentence from a model is not, even when it is right.
 */

const WINDOWS = [7, 30, 90];

export default function RecommendationsPage() {
  const [report, setReport] = useState<RecommendationReport | null>(null);
  const [days, setDays] = useState(30);
  const [kind, setKind] = useState<RecommendationKind | "all">("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [includeMinor, setIncludeMinor] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    setReport(null);

    const load = async () => {
      try {
        const next = await apiFetch<RecommendationReport>(
          `/recommendations/insights?days=${days}&include_minor=${includeMinor}`
        );
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
  }, [days, includeMinor]);

  const counts = useMemo(() => {
    const tally = new Map<RecommendationKind, number>();
    for (const item of report?.recommendations ?? []) {
      tally.set(item.kind, (tally.get(item.kind) ?? 0) + 1);
    }
    return tally;
  }, [report]);

  const shown: Recommendation[] = useMemo(
    () =>
      (report?.recommendations ?? []).filter((item) => kind === "all" || item.kind === kind),
    [report, kind]
  );

  const withMoney = shown.filter((item) => (item.annual_saving ?? 0) > 0).length;

  return (
    <>
      <PageHeader
        breadcrumb="Intelligence"
        title="Recommendations"
        right={
          <span className="header-meta">
            {report ? (
              <>
                <span>{report.generated} from logged data</span>
                <span className="dim">· {report.rules_run} rules</span>
              </>
            ) : (
              <span className="dim">{error ? "unavailable, retrying" : "loading…"}</span>
            )}
          </span>
        }
      />

      <div className="page">
        <section className="kpis">
          <StatCard label="shown" value={report?.generated ?? "-"} />
          <StatCard
            label="projected saving"
            value={
              report
                ? `$${report.projected_annual_saving.toLocaleString(undefined, {
                    maximumFractionDigits: 0,
                  })}`
                : "-"
            }
            delta="per year, if acted on"
          />
          <StatCard
            label="carbon avoided"
            value={
              report
                ? report.projected_annual_co2e_kg >= 1000
                  ? `${(report.projected_annual_co2e_kg / 1000).toFixed(1)} t`
                  : `${Math.round(report.projected_annual_co2e_kg)} kg`
                : "-"
            }
            delta="CO₂e per year, estimated"
          />
          <StatCard label="with money attached" value={report ? withMoney : "-"} />
        </section>

        <section className="controls">
          <span className="k">window</span>
          {WINDOWS.map((option) => (
            <button
              key={option}
              className={`chip ${days === option ? "on" : ""}`}
              onClick={() => setDays(option)}
            >
              {option}d
            </button>
          ))}

          <span className="divider" />

          <button className={`chip ${kind === "all" ? "on" : ""}`} onClick={() => setKind("all")}>
            all {report ? report.generated : ""}
          </button>
          {([...counts.keys()] as RecommendationKind[])
            .sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0))
            .map((option) => (
              <button
                key={option}
                className={`chip ${kind === option ? "on" : ""}`}
                onClick={() => setKind(option)}
              >
                {KIND_LABEL[option] ?? option} {counts.get(option)}
              </button>
            ))}

          <span className="spacer" />
          {/* The gate hides small findings by default. It does not delete
              them, and a reader auditing the page can see what was set
              aside rather than wondering why a known problem is missing. */}
          <button
            className={`chip ${includeMinor ? "on" : ""}`}
            onClick={() => setIncludeMinor((value) => !value)}
            title="Findings below the materiality thresholds"
          >
            {includeMinor
              ? "hide minor"
              : `show minor${report && report.suppressed_immaterial > 0 ? ` ${report.suppressed_immaterial}` : ""}`}
          </button>
          {shown.length > 0 && (
            <button
              className="chip"
              onClick={() => setOpenKey(openKey ? null : shown[0].key)}
            >
              {openKey ? "collapse" : "open top card"}
            </button>
          )}
        </section>

        {report && report.rules_failed.length > 0 && (
          <p className="warn">
            {report.rules_failed.length} rule
            {report.rules_failed.length === 1 ? "" : "s"} failed to run and are missing from
            this list: {report.rules_failed.join(", ")}.
          </p>
        )}

        {!report ? (
          <p className="empty">
            {error ? `Could not reach the recommendations service (${error}). Retrying.` : "Reading the last " + days + " days…"}
          </p>
        ) : shown.length === 0 ? (
          <p className="empty">
            Nothing in this window clears the thresholds these rules use. That is the
            intended result for a quiet period: no recommendation is better than a
            fabricated one.
          </p>
        ) : (
          <section className="cards">
            {shown.map((item) => (
              <RecommendationCard
                key={item.key}
                recommendation={item}
                expanded={openKey === item.key}
                onToggle={() => setOpenKey(openKey === item.key ? null : item.key)}
              />
            ))}
          </section>
        )}

        {report && (
          <section className="footnote">
            <header>how this list is made</header>
            <p>{report.note}</p>
            <p>
              Rules are thresholds over logged disposals, not a model. A rule stays silent
              below <b>{report.assumptions.min_observations} observations</b> rather than
              drawing a conclusion from a handful of items, and no rule contributes more
              than three cards, so one pattern cannot own the page.
            </p>
            <p>
              A finding is shown when it clears{" "}
              <b>${report.assumptions.min_annual_saving.toLocaleString()} a year</b> or{" "}
              <b>{report.assumptions.min_annual_co2e_kg} kg CO₂e a year</b>, or when it is a
              service problem, an overflowing bin is worth fixing whatever it
              returns. Both thresholds are judgement calls sized for this deployment, not
              measured quantities.
              {report.suppressed_immaterial > 0 && (
                <>
                  {" "}
                  <b>{report.suppressed_immaterial}</b> finding
                  {report.suppressed_immaterial === 1 ? " is" : "s are"} below them right
                  now; use &ldquo;show minor&rdquo; above to see{" "}
                  {report.suppressed_immaterial === 1 ? "it" : "them"}.
                </>
              )}
              {report.trimmed_duplicates > 0 && (
                <>
                  {" "}
                  A further <b>{report.trimmed_duplicates}</b> repeat the pattern of a card
                  already shown.
                </>
              )}
            </p>
            <p>
              Two numbers have no source in your data and are the ones to argue with
              first: washing a reusable at{" "}
              <b>${report.assumptions.wash_cost_per_use.toFixed(2)} per use</b>, and a
              refill station at{" "}
              <b>${report.assumptions.refill_station_cost.toLocaleString()}</b> installed.
            </p>
            <p className="dim">{report.impact_disclaimer}</p>
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
          font-family: ui-monospace, Menlo, monospace;
        }
        .k {
          color: var(--text-dim);
          font-size: 10px;
        }
        .divider {
          width: 1px;
          height: 15px;
          background: var(--border-08);
          margin: 0 4px;
        }
        .spacer {
          flex: 1;
        }
        .chip {
          padding: 2px 8px;
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
        .warn {
          padding: 7px 10px;
          border: 1px solid var(--status-in-progress);
          border-radius: 3px;
          color: var(--status-in-progress);
          font-size: 11px;
          line-height: 15px;
        }
        .empty {
          padding: 22px 12px;
          color: var(--text-dim);
          font-size: 12px;
          line-height: 18px;
          max-width: 620px;
        }
        /* Two columns, because a recommendation is read one at a time and a
           full-width card wastes the screen, but three would squeeze the
           evidence tables an expanded card has to hold. */
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
        .footnote p + p {
          padding-top: 0;
        }
        .footnote b {
          color: var(--text-secondary);
          font-weight: 510;
        }
        .footnote p.dim {
          color: var(--text-dim);
          font-size: 10px;
        }
        @media (max-width: 1240px) {
          .cards {
            grid-template-columns: 1fr;
          }
          .kpis {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
      `}</style>
    </>
  );
}
