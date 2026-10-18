"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import AnalyticsFilterBar from "../components/AnalyticsFilterBar";
import DistributionPanel from "../components/DistributionPanel";
import HotspotPanel from "../components/HotspotPanel";
import QualityPanel from "../components/QualityPanel";
import SuppliesPanel from "../components/SuppliesPanel";
import UsageHeatmap from "../components/UsageHeatmap";
import {
  EMPTY_ANALYTICS_FILTERS,
  MEASURE_LABEL,
  WHOLE_WINDOW,
  analyticsQuery,
  apiFetch,
  formatMeasure,
  type AccuracyReport,
  type AnalyticsFilterOptions,
  type AnalyticsFilterState,
  type AnalyticsHotspots,
  type AnalyticsOverview,
  type BinComposition,
  type Building,
  type Can,
  type CatalogRollup,
  type FleetActivity,
  type Measure,
  type MisroutedReport,
  type TimeBucket,
} from "../../lib/api";

/**
 * Waste intelligence: one filter set, six views over it.
 *
 * The page is organised as tabs rather than one long scroll because the
 * questions it answers are genuinely separate -- "what are we throwing away"
 * and "is the classifier right" are asked by different people on different
 * days, and stacking them makes both harder to find. The filter bar and the
 * measure toggle sit above the tabs and apply to all of them, so switching
 * tabs never silently changes the scope of what you are looking at.
 *
 * Only the active tab's data is fetched. Six tabs' worth of aggregates on
 * every filter change would be most of a second of OCI time spent on panels
 * nobody is looking at.
 */

type Tab = "overview" | "composition" | "hotspots" | "timing" | "supplies" | "quality";

const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: "overview", label: "Overview", blurb: "Volume, cost, mass and diversion at a glance" },
  { id: "composition", label: "Composition", blurb: "What is being thrown away, broken down any way you like" },
  { id: "hotspots", label: "Places", blurb: "Which buildings and cans are busy, and what is in them" },
  { id: "timing", label: "Timing", blurb: "When disposal peaks across the week" },
  { id: "supplies", label: "Supplies", blurb: "Discarded units by SKU and supplier" },
  { id: "quality", label: "Quality", blurb: "Classifier agreement with reviewers, and wrong-bin sorting" },
];

const MEASURES: Measure[] = ["count", "cost", "mass"];

export default function AnalyticsPage() {
  const [filters, setFilters] = useState<AnalyticsFilterState>(EMPTY_ANALYTICS_FILTERS);
  const [tab, setTab] = useState<Tab>("overview");
  const [measure, setMeasure] = useState<Measure>("count");

  const [options, setOptions] = useState<AnalyticsFilterOptions | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [cans, setCans] = useState<Can[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [hotspots, setHotspots] = useState<AnalyticsHotspots | null>(null);
  const [bins, setBins] = useState<BinComposition[] | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyReport | null>(null);
  const [misrouted, setMisrouted] = useState<MisroutedReport | null>(null);
  const [catalog, setCatalog] = useState<CatalogRollup | null>(null);
  const [activity, setActivity] = useState<FleetActivity | null>(null);
  const [bucket, setBucket] = useState<TimeBucket>(WHOLE_WINDOW);

  const query = useMemo(() => analyticsQuery(filters), [filters]);

  // Reference data: buildings, cans and the dimension list change far more
  // slowly than the aggregates, so they are fetched once rather than per
  // filter change. The filter options do depend on the window, since they
  // list the values actually present in it.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [buildingList, canList, dimensionList] = await Promise.all([
          apiFetch<Building[]>("/buildings"),
          apiFetch<Can[]>("/cans"),
          apiFetch<string[]>("/analytics/dimensions"),
        ]);
        if (!alive) return;
        setBuildings(buildingList);
        setCans(canList);
        setDimensions(dimensionList);
      } catch {
        /* backend may be booting; the per-tab fetches below retry */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const next = await apiFetch<AnalyticsFilterOptions>(
          `/analytics/filters?days=${filters.days}`
        );
        if (alive) setOptions(next);
      } catch {
        /* the bar still works with the building and can lists */
      }
    })();
    return () => {
      alive = false;
    };
  }, [filters.days]);

  // The KPI strip sits above every tab, so its data is fetched on any filter
  // change rather than with a particular tab. Accuracy is in here rather than
  // with the Quality tab for the same reason: it has a tile in the strip, and
  // a headline tile that reads "-" until you happen to open another tab looks
  // broken rather than deferred.
  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const [overviewData, accuracyData] = await Promise.all([
          apiFetch<AnalyticsOverview>(`/analytics/overview${query}`),
          apiFetch<AccuracyReport>(`/analytics/accuracy${query}`),
        ]);
        if (!alive) return;
        setOverview(overviewData);
        setAccuracy(accuracyData);
      } catch {
        if (alive) retry = setTimeout(load, 4000);
      }
    };
    load();
    return () => {
      alive = false;
      if (retry) clearTimeout(retry);
    };
  }, [query]);

  // Per-tab data, fetched only while that tab is open.
  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      try {
        if (tab === "hotspots") {
          const [hotspotData, binData] = await Promise.all([
            apiFetch<AnalyticsHotspots>(`/analytics/hotspots${query}`),
            apiFetch<BinComposition[]>(`/analytics/bins${query}`),
          ]);
          if (!alive) return;
          setHotspots(hotspotData);
          setBins(binData);
        } else if (tab === "quality") {
          // Accuracy is already loaded for the KPI strip; only the misrouting
          // report is specific to this tab.
          const misroutedData = await apiFetch<MisroutedReport>(`/analytics/misrouted${query}`);
          if (alive) setMisrouted(misroutedData);
        } else if (tab === "supplies") {
          const catalogData = await apiFetch<CatalogRollup>(`/analytics/catalog${query}`);
          if (alive) setCatalog(catalogData);
        } else if (tab === "timing") {
          // The usage heatmap is the fleet's own endpoint: it buckets by
          // weekday and hour, which is exactly the "when does it get busy"
          // question, and reusing it keeps one definition of a peak hour
          // across the map and this page.
          const params = new URLSearchParams({ days: String(filters.days) });
          if (filters.buildingId) params.set("building_id", filters.buildingId);
          const activityData = await apiFetch<FleetActivity>(`/fleet/activity?${params}`);
          if (alive) setActivity(activityData);
        }
      } catch {
        if (alive) retry = setTimeout(load, 4000);
      }
    };

    load();
    return () => {
      alive = false;
      if (retry) clearTimeout(retry);
    };
  }, [tab, query, filters.days, filters.buildingId]);

  // Clicking a bucket in a breakdown filters the page by it, for the
  // dimensions that correspond to a filter. Dimensions that do not (a
  // weekday, say) are left inert rather than wired to something surprising.
  const drill = useCallback(
    (dimension: string, value: string) => {
      if (dimension === "category") setFilters((f) => ({ ...f, category: value }));
      else if (dimension === "material") setFilters((f) => ({ ...f, material: value }));
      else if (dimension === "object") setFilters((f) => ({ ...f, detectedObject: value }));
      else if (dimension === "supplier") setFilters((f) => ({ ...f, supplier: value }));
      else if (dimension === "building") {
        const match = buildings.find((b) => b.name === value);
        if (match) setFilters((f) => ({ ...f, buildingId: String(match.building_id), canId: "" }));
      } else if (dimension === "can") {
        const match = cans.find((c) => c.can_code === value);
        if (match) setFilters((f) => ({ ...f, canId: String(match.can_id), buildingId: "" }));
      }
    },
    [buildings, cans]
  );

  const selectCan = useCallback(
    (canCode: string) => {
      const match = cans.find((c) => c.can_code === canCode);
      if (match) setFilters((f) => ({ ...f, canId: String(match.can_id), buildingId: "" }));
    },
    [cans]
  );

  const active = TABS.find((t) => t.id === tab)!;

  return (
    <>
      <PageHeader
        breadcrumb="Intelligence"
        title="Analytics"
        right={
          <span className="header-meta">
            {overview ? (
              <>
                <span>{overview.total_items.toLocaleString()} items</span>
                <span className="dim">· last {filters.days}d</span>
              </>
            ) : (
              <span className="dim">loading…</span>
            )}
          </span>
        }
      />

      <div className="page">
        <AnalyticsFilterBar
          value={filters}
          onChange={setFilters}
          options={options}
          buildings={buildings}
          cans={cans}
        />

        <section className="kpis">
          <StatCard label="items" value={overview?.total_items.toLocaleString() ?? "-"} />
          <StatCard
            label="est. cost"
            value={overview ? formatMeasure(overview.estimated_cost, "cost") : "-"}
          />
          <StatCard
            label="est. mass"
            value={overview ? formatMeasure(overview.estimated_kg, "mass") : "-"}
          />
          <StatCard label="diverted" value={overview?.diversion_rate ?? "-"} suffix="%" />
          <StatCard label="catalog match" value={overview?.catalog_match_rate ?? "-"} suffix="%" />
          <StatCard
            label="hazardous"
            value={overview?.hazard_items ?? "-"}
            delta={
              overview
                ? overview.hazard_critical_items > 0
                  ? `${overview.hazard_critical_items} critical`
                  : "none critical"
                : undefined
            }
          />
          <StatCard
            label="review agreement"
            value={accuracy?.accuracy ?? "-"}
            suffix={accuracy?.accuracy != null ? "%" : undefined}
            delta={accuracy ? `${accuracy.reviewed_events} reviewed` : undefined}
          />
        </section>

        <nav className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={`tab ${tab === item.id ? "on" : ""}`}
              onClick={() => setTab(item.id)}
              title={item.blurb}
            >
              {item.label}
            </button>
          ))}
          <span className="spacer" />
          {/* The measure toggle is global rather than per-panel: comparing
              items on one chart against dollars on another is the easiest
              way to misread this page. */}
          <span className="measure">
            <span className="k">measure</span>
            {MEASURES.map((option) => (
              <button
                key={option}
                className={`chip ${measure === option ? "on" : ""}`}
                onClick={() => setMeasure(option)}
              >
                {MEASURE_LABEL[option]}
              </button>
            ))}
          </span>
        </nav>

        <p className="blurb">{active.blurb}</p>

        {tab === "overview" && (
          <section className="grid-two">
            <DistributionPanel
              filters={filters}
              measure={measure}
              title="composition"
              initialDimension="material"
              dimensions={dimensions}
              onDrill={drill}
            />
            <DistributionPanel
              filters={filters}
              measure={measure}
              title="top items"
              initialDimension="object"
              dimensions={dimensions}
              onDrill={drill}
            />
            {overview && (
              <section className="notes">
                <header>how these numbers are made</header>
                <ul>
                  <li>
                    <b>Estimated mass.</b> {overview.estimate_notes.mass}
                  </li>
                  <li>
                    <b>Estimated cost.</b> {overview.estimate_notes.cost}
                  </li>
                  <li>
                    <b>Hazards.</b> {overview.estimate_notes.hazards}{" "}
                    <Link href="/hazards" className="link">
                      Open the hazards page
                    </Link>{" "}
                    to see where they were found and what handling each needs.
                  </li>
                  <li>
                    <b>Coverage.</b> {overview.estimate_notes.unmatched} Of the cost shown,{" "}
                    {formatMeasure(overview.cost_from_matched, "cost")} comes from a specific
                    product match and{" "}
                    {formatMeasure(overview.cost_from_class_average, "cost")} from the average
                    across an item&rsquo;s catalog variants.
                  </li>
                </ul>
              </section>
            )}
          </section>
        )}

        {tab === "composition" && (
          <section className="grid-two">
            <DistributionPanel
              filters={filters}
              measure={measure}
              title="breakdown"
              initialDimension="material"
              dimensions={dimensions}
              onDrill={drill}
            />
            <DistributionPanel
              filters={filters}
              measure={measure}
              title="cross-check"
              initialDimension="variant"
              dimensions={dimensions}
              onDrill={drill}
            />
          </section>
        )}

        {tab === "hotspots" && (
          <HotspotPanel
            hotspots={hotspots}
            bins={bins}
            measure={measure}
            onSelectCan={selectCan}
          />
        )}

        {tab === "timing" && (
          <section className="grid-two">
            <UsageHeatmap
              activity={activity}
              bucket={bucket}
              onBucketChange={setBucket}
              windowDays={filters.days}
              onWindowDaysChange={(days) => setFilters((f) => ({ ...f, days }))}
              selectionHint="click a cell, day, or hour to read its totals"
            />
            <DistributionPanel
              filters={filters}
              measure={measure}
              title="volume over time"
              initialDimension="day"
              dimensions={dimensions}
            />
          </section>
        )}

        {tab === "supplies" && <SuppliesPanel catalog={catalog} measure={measure} />}

        {tab === "quality" && <QualityPanel accuracy={accuracy} misrouted={misrouted} />}
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
          padding: 10px 12px 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-height: 0;
        }
        .kpis {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 6px;
        }
        .tabs {
          display: flex;
          align-items: center;
          gap: 2px;
          border-bottom: 1px solid var(--border-08);
          padding-bottom: 0;
        }
        .tab {
          padding: 5px 11px;
          font-size: 12px;
          color: var(--text-muted);
          border-bottom: 2px solid transparent;
          margin-bottom: -1px;
        }
        .tab:hover {
          color: var(--text-secondary);
        }
        .tab.on {
          color: var(--text-primary);
          border-bottom-color: var(--primary);
        }
        .spacer {
          flex: 1;
        }
        .measure {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          padding-bottom: 4px;
          font-family: ui-monospace, Menlo, monospace;
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
          line-height: 15px;
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
        .blurb {
          color: var(--text-dim);
          font-size: 11px;
          margin-top: -4px;
        }
        .grid-two {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 10px;
          align-items: start;
        }
        .notes {
          grid-column: 1 / -1;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
        }
        .notes header {
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 10px;
        }
        .notes ul {
          list-style: none;
          padding: 7px 10px 9px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .notes li {
          color: var(--text-muted);
          line-height: 15px;
        }
        .notes b {
          color: var(--text-secondary);
          font-weight: 510;
        }
        .notes :global(.link) {
          color: var(--link);
          text-decoration: underline;
        }
        @media (max-width: 1240px) {
          .grid-two {
            grid-template-columns: 1fr;
          }
          .kpis {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
      `}</style>
    </>
  );
}
