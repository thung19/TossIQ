"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import FillBar from "../components/FillBar";
import CanDetailPanel from "../components/CanDetailPanel";
import FleetFilters, { EMPTY_FILTERS, type FleetFilterState } from "../components/FleetFilters";
import {
  apiFetch,
  type Building,
  type Can,
  type CanModel,
  type CanStatus,
  type FleetSummary,
} from "../../lib/api";

// Leaflet touches `window` at import time, so the map component can only be
// loaded in the browser.
const CampusMap = dynamic(() => import("../components/CampusMap"), {
  ssr: false,
  loading: () => <div className="map-loading">loading map…</div>,
});

const STATUS_ORDER: CanStatus[] = ["offline", "fault", "needs_service", "ok"];
const STATUS_LABEL: Record<CanStatus, string> = {
  offline: "offline",
  fault: "fault",
  needs_service: "needs service",
  ok: "ok",
};

export default function CampusMapPage() {
  const [cans, setCans] = useState<Can[]>([]);
  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [models, setModels] = useState<CanModel[]>([]);
  const [filters, setFilters] = useState<FleetFilterState>(EMPTY_FILTERS);
  const [selectedCanId, setSelectedCanId] = useState<number | null>(null);
  // Bumped after a service action so the fleet refetches without waiting for
  // the next poll tick.
  const [refreshToken, setRefreshToken] = useState(0);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.buildingId) params.set("building_id", filters.buildingId);
    if (filters.modelId) params.set("model_id", filters.modelId);
    if (filters.stream) params.set("stream", filters.stream);
    const encoded = params.toString();
    return encoded ? `?${encoded}` : "";
  }, [filters]);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const [fleet, fleetSummary] = await Promise.all([
          apiFetch<Can[]>(`/cans${query}`),
          apiFetch<FleetSummary>("/fleet/summary"),
        ]);
        if (!alive) return;
        setCans(fleet);
        setSummary(fleetSummary);
      } catch {
        /* backend may be booting; the loop will retry */
      }
    };
    refresh();
    const id = setInterval(refresh, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [query, refreshToken]);

  // Filter options change far more slowly than fleet status, so they are
  // fetched once rather than polled.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [buildingList, modelList] = await Promise.all([
          apiFetch<Building[]>("/buildings"),
          apiFetch<CanModel[]>("/can-models"),
        ]);
        if (!alive) return;
        setBuildings(buildingList);
        setModels(modelList);
      } catch {
        /* backend may be booting; the fleet poll will still populate the map */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const worklist = useMemo(
    () =>
      [...cans]
        .filter((can) => can.status !== "ok")
        .sort(
          (a, b) =>
            STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
            (b.fill_percent ?? 0) - (a.fill_percent ?? 0)
        ),
    [cans]
  );

  return (
    <>
      <PageHeader
        breadcrumb="Operations"
        title="Campus map"
        right={
          <span className="header-meta">
            <span>{cans.length} cans shown</span>
            {summary && (
              <span className="dim">
                · {summary.observed} live · {summary.simulated} simulated
              </span>
            )}
          </span>
        }
      />

      <div className="page">
        <section className="kpi-row">
          <StatCard label="fleet" value={summary?.total ?? "—"} />
          {STATUS_ORDER.map((status) => (
            <StatCard
              key={status}
              label={STATUS_LABEL[status]}
              value={summary?.by_status[status] ?? "—"}
            />
          ))}
          <StatCard
            label="threshold"
            value={summary?.service_threshold_percent ?? "—"}
            suffix="%"
          />
        </section>

        <FleetFilters
          value={filters}
          onChange={setFilters}
          buildings={buildings}
          models={models}
          summary={summary}
        />

        <section className={`grid ${selectedCanId ? "with-panel" : ""}`}>
          <div className="map-col">
            <CampusMap cans={cans} selectedCanId={selectedCanId} onSelect={setSelectedCanId} />
          </div>

          {selectedCanId ? (
            <CanDetailPanel
              canId={selectedCanId}
              serviceThreshold={summary?.service_threshold_percent}
              onClose={() => setSelectedCanId(null)}
              onServiced={() => setRefreshToken((n) => n + 1)}
            />
          ) : (
            <section className="worklist">
              <header>
                <span className="title">attention</span>
                <span className="meta">{worklist.length}</span>
              </header>
              {worklist.length === 0 ? (
                <div className="empty">every can shown is healthy</div>
              ) : (
                <div className="rows">
                  {worklist.map((can) => (
                    <button
                      key={can.can_id}
                      className="row"
                      onClick={() => setSelectedCanId(can.can_id)}
                    >
                      <span className={`dot ${can.status}`} />
                      <span className="code">{can.can_code}</span>
                      <span className="where">{can.building_name}</span>
                      <span className="fill">
                        <FillBar
                          percent={can.fill_percent}
                          source={can.fill_source}
                          threshold={summary?.service_threshold_percent}
                          showLabel={false}
                        />
                      </span>
                      <span className="reason">{can.status_reasons[0] ?? STATUS_LABEL[can.status]}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
        </section>
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
        .header-meta .dim {
          color: var(--text-dim);
        }
        .page {
          padding: 10px 12px 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-height: 0;
          flex: 1;
        }
        .kpi-row {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr));
          gap: 6px;
        }
        .grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 380px;
          gap: 10px;
          flex: 1;
          min-height: 520px;
        }
        .map-col {
          min-width: 0;
          display: flex;
          flex-direction: column;
        }
        .map-col :global(.map-loading) {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-dim);
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
        }
        .worklist {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          overflow: hidden;
          min-width: 0;
          font-family: ui-monospace, Menlo, monospace;
        }
        .worklist header {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
          font-size: 11px;
          flex-shrink: 0;
        }
        .worklist .title {
          color: var(--text-dim);
        }
        .worklist .meta {
          color: var(--text-primary);
          font-weight: 510;
          font-variant-numeric: tabular-nums;
        }
        .rows {
          overflow-y: auto;
          display: flex;
          flex-direction: column;
        }
        .empty {
          padding: 12px 10px;
          font-size: 11px;
          color: var(--text-dim);
        }
        .row {
          display: grid;
          grid-template-columns: 7px minmax(0, 96px) minmax(0, 1fr) 54px;
          grid-template-areas:
            "dot code where fill"
            ".   reason reason reason";
          align-items: center;
          column-gap: 8px;
          row-gap: 2px;
          padding: 6px 10px;
          text-align: left;
          font-family: inherit;
          font-size: 11px;
          border-bottom: 1px solid var(--border-05);
        }
        .row:hover {
          background: var(--overlay-02);
        }
        .dot {
          grid-area: dot;
          width: 7px;
          height: 7px;
          border-radius: 50%;
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
        .dot.ok {
          background: var(--status-done);
        }
        .code {
          grid-area: code;
          color: var(--text-primary);
          font-weight: 510;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .where {
          grid-area: where;
          color: var(--text-muted);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .fill {
          grid-area: fill;
          min-width: 0;
        }
        .reason {
          grid-area: reason;
          color: var(--text-dim);
          font-size: 10px;
          line-height: 14px;
        }
        @media (max-width: 1240px) {
          .grid {
            grid-template-columns: 1fr;
          }
          .kpi-row {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
      `}</style>
    </>
  );
}
