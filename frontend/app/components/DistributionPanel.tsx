"use client";

import { useEffect, useState } from "react";
import BarList from "./BarList";
import {
  MEASURE_LABEL,
  apiFetch,
  analyticsQuery,
  type AnalyticsDistribution,
  type AnalyticsFilterState,
  type Measure,
} from "../../lib/api";

/**
 * "Distribution of X" for any X the API will group by.
 *
 * One panel rather than a dozen hardcoded charts: the server publishes the
 * dimensions it supports (/analytics/dimensions) and this renders whichever
 * one is picked, so adding a grouping is a backend change alone. The same
 * query also backs the supplier and material views, which is what guarantees
 * the cost column reconciles across them.
 */

const DIMENSION_LABEL: Record<string, string> = {
  category: "bin it went in",
  material: "material",
  material_subtype: "material detail",
  object: "detected item",
  product: "catalog product",
  variant: "product variant",
  brand: "brand",
  supplier: "supplier",
  sku: "SKU",
  building: "building",
  campus_area: "campus area",
  can: "can",
  floor: "floor",
  correct_bin: "bin it belonged in",
  match_method: "how it was matched",
  hazard_class: "hazard type",
  hazard_severity: "hazard severity",
  hour: "hour of day",
  weekday: "weekday",
  day: "date",
};

// Offered in a deliberate order rather than alphabetically: the groupings
// someone actually opens first come first.
const DIMENSION_ORDER = [
  "material", "material_subtype", "object", "variant", "brand", "product",
  "sku", "supplier", "category", "correct_bin", "building", "campus_area",
  "can", "floor", "hazard_class", "hazard_severity", "hour", "weekday", "day",
  "match_method",
];

export default function DistributionPanel({
  filters,
  measure,
  title = "distribution",
  initialDimension = "material",
  dimensions,
  onDrill,
}: {
  filters: AnalyticsFilterState;
  measure: Measure;
  title?: string;
  initialDimension?: string;
  dimensions: string[];
  /** Clicking a bucket asks the page to filter by it, where that makes
   * sense for the dimension on screen. */
  onDrill?: (dimension: string, bucket: string) => void;
}) {
  const [dimension, setDimension] = useState(initialDimension);
  const [data, setData] = useState<AnalyticsDistribution | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const next = await apiFetch<AnalyticsDistribution>(
          `/analytics/distribution${analyticsQuery(filters, { dimension, limit: 40 })}`
        );
        if (!alive) return;
        setData(next);
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
  }, [filters, dimension]);

  const ordered = DIMENSION_ORDER.filter((name) => dimensions.includes(name));
  const available = ordered.length > 0 ? ordered : dimensions;

  return (
    <section className="panel">
      <header>
        <span className="title">{title}</span>
        <span className="by">by</span>
        <select value={dimension} onChange={(e) => setDimension(e.target.value)}>
          {available.map((name) => (
            <option key={name} value={name}>
              {DIMENSION_LABEL[name] ?? name}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <span className="meta">
          {data
            ? `${data.rows.length} group${data.rows.length === 1 ? "" : "s"} · ` +
              `${data.shown_count.toLocaleString()} of ${data.total_count.toLocaleString()} items` +
              (data.truncated ? " · tail not shown" : "")
            : error
              ? "unavailable, retrying"
              : "loading…"}
        </span>
      </header>

      {/* A breakdown by item or SKU routinely runs to forty rows while the
          one beside it has eight. Capping the scroll height keeps the two
          columns the same size instead of leaving one of them mostly
          whitespace. */}
      <div className="scroll">
        <BarList
          rows={data?.rows ?? []}
          measure={measure}
          onSelect={onDrill ? (bucket) => onDrill(dimension, bucket) : undefined}
          emptyLabel={error ? "could not load this breakdown" : "nothing logged in this scope"}
        />
      </div>

      {measure !== "count" && (
        <footer>
          solid bar = {MEASURE_LABEL[measure]} from a matched product · hatched =
          carried by the class average for that item
        </footer>
      )}

      <style jsx>{`
        .panel {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          min-width: 0;
          font-family: ui-monospace, Menlo, monospace;
        }
        header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          font-size: 11px;
        }
        .scroll {
          max-height: 420px;
          overflow-y: auto;
          padding: 4px 0;
          min-width: 0;
        }
        .title {
          color: var(--text-primary);
          font-weight: 510;
        }
        .by,
        .meta {
          color: var(--text-dim);
          font-size: 10px;
        }
        .spacer {
          flex: 1;
        }
        select {
          font-family: inherit;
          font-size: 10.5px;
          color: var(--text-primary);
          background: var(--overlay-05);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          padding: 1px 4px;
          cursor: pointer;
        }
        option {
          background: var(--bg-elevated);
        }
        footer {
          padding: 6px 10px 8px;
          color: var(--text-dim);
          font-size: 9.5px;
          line-height: 13px;
        }
      `}</style>
    </section>
  );
}
