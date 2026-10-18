"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PageHeader from "./components/PageHeader";
import StatCard from "./components/StatCard";
import CameraCanvas from "./components/CameraCanvas";
import EventFilmstrip from "./components/EventFilmstrip";
import SessionPanel from "./components/SessionPanel";
import ProgressTracker from "./components/ProgressTracker";
import ThroughputChart from "./components/ThroughputChart";
import CategorySplit from "./components/CategorySplit";
import {
  apiFetch,
  type CameraStats,
  type Detection,
  type DetectionEvent,
  type StatsOverview,
  type WasteEvent,
} from "../lib/api";

export default function LiveSortingPage() {
  const [current, setCurrent] = useState<Detection | null>(null);
  const [currentUpdatedAt, setCurrentUpdatedAt] = useState<number | null>(null);
  const [cameraStats, setCameraStats] = useState<CameraStats | null>(null);
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [events, setEvents] = useState<WasteEvent[]>([]);
  const [now, setNow] = useState<number>(0);
  const sessionStartRef = useRef<number>(0);
  useEffect(() => {
    if (sessionStartRef.current === 0) sessionStartRef.current = Date.now();
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleDetection = useCallback((ev: DetectionEvent) => {
    const named = ev.detections
      .filter((d) => d.category !== null)
      .sort((a, b) => b.confidence - a.confidence)[0];
    if (named) {
      setCurrent(named);
      setCurrentUpdatedAt(Date.now());
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const [cam, overview, recent] = await Promise.all([
          apiFetch<CameraStats>("/camera/stats"),
          apiFetch<StatsOverview>("/stats/overview?days=1"),
          apiFetch<WasteEvent[]>("/events/recent?limit=200"),
        ]);
        if (!alive) return;
        setCameraStats(cam);
        setStats(overview);
        setEvents(recent);
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
  }, []);

  const kpis = computeKpis(stats, cameraStats, events, sessionStartRef.current, now);
  const splitRows = (stats?.by_category || []).map((c) => ({ category: c.category || "unknown", count: c.count }));

  return (
    <>
      <PageHeader
        breadcrumb="Operations"
        title="Live sorting"
        right={
          <span className="header-meta">
            <span className={`dot ${cameraStats?.running ? "on" : "off"}`} />
            <span>{cameraStats?.running ? "Live" : "Offline"}</span>
          </span>
        }
      />

      <div className="page">
        <section className="grid-top">
          <SessionPanel cameraStats={cameraStats} events={events} sessionStart={sessionStartRef.current} now={now} />

          <div className="center">
            <CameraCanvas onDetection={handleDetection} />
            <ProgressTracker detection={current} updatedAt={currentUpdatedAt} cameraStats={cameraStats} now={now} />
          </div>

          <div className="right">
            <div className="kpi-grid">
              {kpis.map((k) => (
                <StatCard key={k.label} label={k.label} value={k.value} suffix={k.suffix} delta={k.delta} />
              ))}
            </div>
            <ThroughputChart events={events} now={now} />
            <CategorySplit rows={splitRows} totalLabel="items (24h)" />
          </div>
        </section>

        <EventFilmstrip events={events} />
      </div>

      <style jsx>{`
        .header-meta {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: var(--text-muted);
        }
        .header-meta .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }
        .header-meta .dot.on {
          background: var(--status-done);
        }
        .header-meta .dot.off {
          background: var(--status-backlog);
        }
        .page {
          padding: 10px 12px 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .grid-top {
          display: grid;
          grid-template-columns: 260px minmax(0, 1fr) 320px;
          gap: 10px;
          align-items: stretch;
        }
        .center {
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-width: 0;
        }
        .right {
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-width: 0;
        }
        .kpi-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 6px;
        }
        @media (max-width: 1400px) {
          .grid-top {
            grid-template-columns: 280px minmax(0, 1fr);
          }
          .right {
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: repeat(2, 1fr) 1.5fr;
            gap: 10px;
          }
          .right > :global(.card),
          .right > :global(section) {
            min-width: 0;
          }
          .kpi-grid {
            grid-column: 1 / -1;
          }
        }
        @media (max-width: 1100px) {
          .grid-top {
            grid-template-columns: 1fr;
          }
          .right {
            grid-template-columns: 1fr;
          }
          .kpi-grid {
            grid-template-columns: repeat(3, 1fr);
          }
        }
      `}</style>
    </>
  );
}

type Kpi = { label: string; value: string | number; suffix?: string; delta?: string };

function computeKpis(stats: StatsOverview | null, cam: CameraStats | null, events: WasteEvent[], sessionStart: number, now: number): Kpi[] {
  const byCat = Object.fromEntries((stats?.by_category || []).map((c) => [c.category, c.count]));
  const total = stats?.total_items || 0;
  const recycled = byCat["recycling"] || 0;
  const composted = byCat["compost"] || 0;
  const landfill = byCat["landfill"] || 0;

  const diverted = total > 0 ? Math.round(((recycled + composted) / total) * 100) : 0;

  const sessionMin = Math.max(1, Math.floor((now - sessionStart) / 60000));
  const throughput = cam ? Math.round(((cam.detections || 0) / sessionMin) * 10) / 10 : 0;

  const uncertain = events.filter((e) => !e.category || e.category === "unknown").length;

  return [
    { label: "items 24h", value: total },
    { label: "diverted", value: diverted, suffix: "%" },
    { label: "landfill", value: landfill },
    { label: "uncertain", value: uncertain },
    { label: "inference", value: cam?.last_inference_ms ?? "-", suffix: cam?.last_inference_ms != null ? "ms" : undefined },
    { label: "throughput", value: throughput, suffix: "/min" },
  ];
}
