"use client";

import { useEffect, useRef } from "react";
import type { Can, CanStatus } from "../../lib/api";
import "leaflet/dist/leaflet.css";

/**
 * Leaflet wrapper for the campus fleet.
 *
 * Plain Leaflet instantiated in a useEffect, not react-leaflet: this app runs
 * Next 16 / React 19, and the wrapper's peer-dependency surface is the most
 * likely thing to break on versions that new. Leaflet itself has no React
 * version opinion. It touches `window` at import time, so the page loads this
 * component through next/dynamic with ssr: false.
 *
 * Markers are L.divIcon, i.e. styled DOM rather than image sprites, so they
 * inherit the dark palette from globals.css instead of needing a recoloured
 * PNG per status.
 */

// Esri's World Dark Gray Canvas: a dark basemap that still serves real tiles
// without an API key, and muted enough that the Linear palette reads on top
// of it. CARTO's dark_all was the obvious first choice, but its CDN now
// returns an "API KEY REQUIRED" watermark tile instead of map data, so it is
// no longer the keyless option it used to be.
//
// Esri publishes this service with {z}/{y}/{x} ordering, the reverse of
// Leaflet's default {z}/{x}/{y}, hence the swapped placeholders below.
const TILE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const TILE_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// The service has no tiles above z16, but cans inside one building sit ~40 m
// apart, which needs closer zoom to separate. maxNativeZoom lets Leaflet
// upscale the z16 tile rather than showing blank tiles, so the pins stay
// individually clickable at the cost of a softer basemap.
const MAX_NATIVE_ZOOM = 16;
const MAX_ZOOM = 19;

// Approximate centre of the Vanderbilt campus, matching seed_campus.py.
const CAMPUS_CENTRE: [number, number] = [36.145, -86.803];
const DEFAULT_ZOOM = 16;

// Below this zoom the whole campus is a few hundred pixels wide and 43 pins
// overlap into a blob, so only the cans that need attention are drawn.
const DETAIL_ZOOM = 16;

const STATUS_CLASS: Record<CanStatus, string> = {
  ok: "pin-ok",
  needs_service: "pin-service",
  fault: "pin-fault",
  offline: "pin-offline",
};

export default function CampusMap({
  cans,
  selectedCanId,
  onSelect,
}: {
  cans: Can[];
  selectedCanId: number | null;
  onSelect: (canId: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  // The click handler is read from a ref so re-rendering the parent does not
  // force every marker to be torn down and rebuilt.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    let disposed = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (disposed || !containerRef.current || mapRef.current) return;

      const map = L.map(containerRef.current, {
        center: CAMPUS_CENTRE,
        zoom: DEFAULT_ZOOM,
        maxZoom: MAX_ZOOM,
        zoomControl: true,
        attributionControl: true,
      });
      L.tileLayer(TILE_URL, {
        attribution: TILE_ATTRIBUTION,
        maxNativeZoom: MAX_NATIVE_ZOOM,
        maxZoom: MAX_ZOOM,
      }).addTo(map);

      leafletRef.current = L;
      mapRef.current = map;
      layerRef.current = L.layerGroup().addTo(map);

      // Redraw on zoom so the low-zoom thinning takes effect.
      map.on("zoomend", () => draw());
      draw();
    })();

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Markers are rebuilt wholesale on every poll. At 43 cans that is cheaper
  // and far simpler than diffing, and the 3 s tick makes it unnoticeable.
  const draw = () => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!L || !map || !layer) return;

    layer.clearLayers();
    const zoomedOut = map.getZoom() < DETAIL_ZOOM;

    for (const can of cans) {
      if (can.latitude == null || can.longitude == null) continue;
      if (zoomedOut && can.status === "ok") continue;

      const selected = can.can_id === selectedCanId;
      const icon = L.divIcon({
        className: "can-pin-wrap",
        html: `<span class="can-pin ${STATUS_CLASS[can.status]}${selected ? " selected" : ""}${
          can.is_simulated ? " simulated" : ""
        }"></span>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });

      L.marker([can.latitude, can.longitude], { icon, title: `${can.can_code} — ${can.status}` })
        .addTo(layer)
        .on("click", () => onSelectRef.current(can.can_id));
    }
  };

  useEffect(draw, [cans, selectedCanId]);

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map" />

      <div className="legend">
        {(
          [
            ["ok", "ok"],
            ["needs_service", "needs service"],
            ["fault", "hardware fault"],
            ["offline", "offline"],
          ] as [CanStatus, string][]
        ).map(([status, label]) => (
          <span key={status} className="legend-item">
            <span className={`swatch ${STATUS_CLASS[status]}`} />
            {label}
          </span>
        ))}
        <span className="legend-item note">dashed ring = simulated can</span>
      </div>

      <style jsx>{`
        .map-shell {
          position: relative;
          border: 1px solid var(--border-08);
          border-radius: 3px;
          overflow: hidden;
          background: var(--bg-surface);
          min-height: 420px;
          height: 100%;
        }
        .map {
          position: absolute;
          inset: 0;
        }
        .legend {
          position: absolute;
          left: 10px;
          bottom: 10px;
          z-index: 500;
          display: flex;
          flex-direction: column;
          gap: 3px;
          padding: 7px 9px;
          background: var(--bg-card);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10.5px;
          color: var(--text-muted);
        }
        .legend-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          white-space: nowrap;
        }
        .legend-item.note {
          color: var(--text-dim);
          margin-top: 2px;
        }
        .swatch {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .swatch.pin-ok {
          background: var(--status-done);
        }
        .swatch.pin-service {
          background: var(--status-in-progress);
        }
        .swatch.pin-fault {
          background: var(--status-bug);
        }
        .swatch.pin-offline {
          background: var(--status-backlog);
        }
      `}</style>

      {/*
        Marker internals are injected by Leaflet as raw HTML strings, which
        styled-jsx cannot scope, so the pin rules live in a plain global style
        block. They are still driven entirely by the palette tokens.
      */}
      <style jsx global>{`
        .leaflet-container {
          background: var(--bg);
          font-family: "Inter Variable", system-ui, sans-serif;
        }
        .leaflet-control-attribution {
          background: var(--bg-card) !important;
          color: var(--text-dim) !important;
          font-size: 9.5px !important;
        }
        .leaflet-control-attribution a {
          color: var(--text-muted) !important;
        }
        .leaflet-bar,
        .leaflet-bar a {
          background: var(--bg-card) !important;
          border-color: var(--border-08) !important;
          color: var(--text-secondary) !important;
        }
        .leaflet-bar a:hover {
          background: var(--bg-elevated) !important;
        }
        .can-pin-wrap {
          background: none;
          border: none;
        }
        .can-pin {
          display: block;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          border: 2px solid var(--bg);
          box-shadow: 0 0 0 1px var(--border-solid);
          cursor: pointer;
          transition: transform 0.1s ease;
        }
        .can-pin:hover {
          transform: scale(1.25);
        }
        .can-pin.selected {
          box-shadow: 0 0 0 2px var(--text-primary);
          transform: scale(1.25);
        }
        /* A simulated can wears a dashed outline so the mock fleet is never
           mistaken for reporting hardware. */
        .can-pin.simulated {
          border-style: dashed;
        }
        .can-pin.pin-ok {
          background: var(--status-done);
        }
        .can-pin.pin-service {
          background: var(--status-in-progress);
        }
        .can-pin.pin-fault {
          background: var(--status-bug);
        }
        .can-pin.pin-offline {
          background: var(--status-backlog);
        }
      `}</style>
    </div>
  );
}
