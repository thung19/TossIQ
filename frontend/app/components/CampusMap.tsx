"use client";

import { useEffect, useRef, useState } from "react";
import type { Can, CanStatus } from "../../lib/api";
import { bucketLabel, heatColor, heatFraction } from "../../lib/heatScale";
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
 * inherit the palette from globals.css instead of needing a recoloured PNG
 * per status, and so the activity mode can drive size and colour per can
 * from a count without generating any images.
 */

// Three basemaps, because one basemap cannot answer both questions this map
// gets asked. Satellite shows the actual quad, path and loading dock a can
// sits beside, which is what someone walking out to empty it needs; streets
// names the buildings; the dark canvas is the quietest backdrop for reading
// the heat layer. All three are keyless Esri/OSM services -- CARTO's dark_all
// was the original choice here but its CDN now returns an "API KEY REQUIRED"
// watermark tile instead of map data.
//
// Esri publishes its tiles as {z}/{y}/{x}, the reverse of Leaflet's default
// {z}/{x}/{y}, hence the swapped placeholders. OSM uses the normal order.
const ESRI_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> | Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export type BasemapKey = "satellite" | "streets" | "dark";

const BASEMAPS: Record<
  BasemapKey,
  { label: string; url: string; attribution: string; maxNativeZoom: number; dim: number }
> = {
  satellite: {
    label: "satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTRIBUTION,
    maxNativeZoom: 19,
    // Imagery is far brighter than the rest of the app, and bright ground
    // under a heat layer reads as heat. A CSS filter knocks it back so the
    // data stays the brightest thing on screen.
    dim: 0.62,
  },
  streets: {
    label: "streets",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxNativeZoom: 19,
    dim: 0.72,
  },
  dark: {
    label: "dark",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTRIBUTION,
    // The dark canvas service has no tiles above z16, but cans inside one
    // building sit ~40 m apart. maxNativeZoom lets Leaflet upscale the z16
    // tile rather than showing blank tiles, so pins stay individually
    // clickable at the cost of a softer basemap.
    maxNativeZoom: 16,
    dim: 1,
  },
};

export const DEFAULT_BASEMAP: BasemapKey = "satellite";

// Approximate centre of the Vanderbilt campus, matching seed_campus.py.
const CAMPUS_CENTRE: [number, number] = [36.145, -86.803];

// Hard limit on where this map can go. The seeded buildings span roughly
// 36.1414..36.1496 N and -86.8083..-86.8011 W; this is that extent with
// enough padding to show the surrounding blocks for orientation and no more.
// Without it the default Leaflet behaviour is an unbounded world map, so a
// stray scroll lands the operator somewhere in Tennessee with no pins and no
// obvious way back. maxBoundsViscosity 1.0 makes the edge solid rather than
// elastic.
const CAMPUS_BOUNDS: [[number, number], [number, number]] = [
  [36.1335, -86.8165],
  [36.1565, -86.7895],
];

// At z14 the campus bounds are narrower than the map pane, so the tile layer's
// own `bounds` leaves grey bands down either side. z15 is the widest view that
// still fills the frame, and it already shows the whole fleet plus the
// surrounding blocks -- there is nothing further out worth panning to.
const MIN_ZOOM = 15;
const MAX_ZOOM = 19;
const DEFAULT_ZOOM = 16;

// A heat blob's reach is a distance on the ground, not a number of pixels: a
// busy can influences the area around it, and that area is the same size
// whether you are zoomed in or out. Sized in pixels instead, the blobs stay
// huge as you zoom out until the whole campus is one orange wash, and shrink
// to dots as you zoom in -- the opposite of what a heatmap should do.
const HEAT_RADIUS_METERS_MIN = 18;
const HEAT_RADIUS_METERS_MAX = 55;

// Web-Mercator ground resolution at the equator, in metres per pixel at z0.
const EQUATOR_METERS_PER_PIXEL = 156543.03392;

function metersToPixels(meters: number, latitude: number, zoom: number): number {
  const metersPerPixel =
    (EQUATOR_METERS_PER_PIXEL * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
  return meters / metersPerPixel;
}

const STATUS_CLASS: Record<CanStatus, string> = {
  ok: "pin-ok",
  needs_service: "pin-service",
  fault: "pin-fault",
  offline: "pin-offline",
};

export type MapMode = "status" | "activity";

export default function CampusMap({
  cans,
  selectedCanId,
  onSelect,
  mode = "status",
  basemap = DEFAULT_BASEMAP,
  onBasemapChange,
  intensity,
  intensityScaleMax = 1,
  bucketDay = null,
  bucketHour = null,
  dayNames = [],
}: {
  cans: Can[];
  selectedCanId: number | null;
  onSelect: (canId: number) => void;
  mode?: MapMode;
  basemap?: BasemapKey;
  onBasemapChange?: (basemap: BasemapKey) => void;
  /** can_id -> disposals in the selected time bucket. */
  intensity?: Map<number, number>;
  /** Percentile bound the colour ramp normalises against, from the API. */
  intensityScaleMax?: number;
  bucketDay?: number | null;
  bucketHour?: number | null;
  dayNames?: string[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const tileRef = useRef<import("leaflet").TileLayer | null>(null);
  const heatRef = useRef<import("leaflet").LayerGroup | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  // Props the draw closure reads. They live in refs so a parent re-render
  // does not have to tear down and rebuild every marker, and so the init
  // effect can call draw() without depending on them.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const drawRef = useRef<() => void>(() => {});

  const [ready, setReady] = useState(false);
  // The initial fit happens once, on the first non-empty fleet. Re-fitting on
  // every poll would yank the view back from wherever the operator panned,
  // and re-fitting when a filter narrows the fleet to one building would zoom
  // the map without being asked to.
  const fittedRef = useRef(false);

  useEffect(() => {
    let disposed = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (disposed || !containerRef.current || mapRef.current) return;

      const map = L.map(containerRef.current, {
        center: CAMPUS_CENTRE,
        zoom: DEFAULT_ZOOM,
        minZoom: MIN_ZOOM,
        maxZoom: MAX_ZOOM,
        maxBounds: CAMPUS_BOUNDS,
        maxBoundsViscosity: 1.0,
        zoomControl: true,
        attributionControl: true,
      });
      // Belt and braces with maxBounds: a programmatic setView or a pinch
      // that overshoots is snapped back to campus on the next frame.
      map.setMaxBounds(CAMPUS_BOUNDS);

      leafletRef.current = L;
      mapRef.current = map;
      // Heat blobs sit in their own pane beneath the markers, so a hot cluster
      // never swallows the pin the operator is trying to click.
      map.createPane("heat");
      const heatPane = map.getPane("heat");
      if (heatPane) {
        heatPane.style.zIndex = "350";
        heatPane.style.pointerEvents = "none";
      }
      heatRef.current = L.layerGroup([], { pane: "heat" }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);

      // Blob radius is derived from the zoom level, so the heat layer has to
      // be rebuilt whenever that changes.
      map.on("zoomend", () => drawRef.current());

      setReady(true);
      drawRef.current();
    })();

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      tileRef.current = null;
      heatRef.current = null;
      layerRef.current = null;
    };
  }, []);

  // The tile layer is swapped rather than rebuilt with the map, so changing
  // the basemap keeps the current pan, zoom and selection.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map) return;
    const config = BASEMAPS[basemap];
    const next = L.tileLayer(config.url, {
      attribution: config.attribution,
      maxNativeZoom: config.maxNativeZoom,
      maxZoom: MAX_ZOOM,
      bounds: CAMPUS_BOUNDS,
    }).addTo(map);
    const previous = tileRef.current;
    tileRef.current = next;
    // Removing the old layer only once the new one has painted avoids a flash
    // of empty background mid-swap.
    next.once("load", () => previous?.remove());
    const safety = setTimeout(() => previous?.remove(), 2500);
    return () => clearTimeout(safety);
  }, [basemap, ready]);

  // Markers are rebuilt wholesale on every poll. At ~43 cans that is cheaper
  // and far simpler than diffing, and the 3 s tick makes it unnoticeable.
  const draw = () => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = layerRef.current;
    const heat = heatRef.current;
    if (!L || !map || !layer || !heat) return;

    layer.clearLayers();
    heat.clearLayers();

    for (const can of cans) {
      if (can.latitude == null || can.longitude == null) continue;

      const count = intensity?.get(can.can_id) ?? 0;
      const fraction = heatFraction(count, intensityScaleMax);
      const selected = can.can_id === selectedCanId;

      if (mode === "activity" && count > 0) {
        // A soft radial blob per can, blended additively, so overlapping cans
        // in one building pool into a single bright area the way a real
        // heatmap does -- without pulling in leaflet.heat, which has no
        // typings on DefinitelyTyped for the current Leaflet 1.9 line.
        //
        // Cans with nothing logged in the selected bucket get no blob at all.
        // A blob for zero is not "cold", it is a smear of colour over a can
        // that contributed nothing, and 43 of them wash out the cans that did.
        const radius = metersToPixels(
          HEAT_RADIUS_METERS_MIN + fraction * (HEAT_RADIUS_METERS_MAX - HEAT_RADIUS_METERS_MIN),
          can.latitude,
          map.getZoom()
        );
        heat.addLayer(
          L.marker([can.latitude, can.longitude], {
            interactive: false,
            keyboard: false,
            pane: "heat",
            icon: L.divIcon({
              className: "heat-blob-wrap",
              html: `<span class="heat-blob" style="--heat:${heatColor(
                count,
                intensityScaleMax
              )};--alpha:${(0.2 + fraction * 0.45).toFixed(3)}"></span>`,
              iconSize: [radius * 2, radius * 2],
              iconAnchor: [radius, radius],
            }),
          })
        );
      }

      const classes = [
        "can-pin",
        mode === "activity" ? "by-heat" : STATUS_CLASS[can.status],
        selected ? "selected" : "",
        can.is_simulated ? "simulated" : "",
        // Faults and offline units keep a visible mark in activity mode: a
        // silent can reads as "cold" on a usage scale, which is the opposite
        // of what it means, so it is ringed rather than left to look quiet.
        mode === "activity" && (can.status === "fault" || can.status === "offline")
          ? "attention"
          : "",
      ]
        .filter(Boolean)
        .join(" ");

      const size = mode === "activity" ? 12 + Math.round(fraction * 12) : 15;
      const style =
        mode === "activity"
          ? `--heat:${heatColor(count, intensityScaleMax)};width:${size}px;height:${size}px`
          : "";

      const bucket = bucketLabel(bucketDay, bucketHour, dayNames);
      const title =
        mode === "activity"
          ? `${can.can_code}, ${count} item${count === 1 ? "" : "s"} (${bucket}), ${can.status}`
          : `${can.can_code}, ${can.status}`;

      L.marker([can.latitude, can.longitude], {
        icon: L.divIcon({
          className: "can-pin-wrap",
          html: `<span class="${classes}" style="${style}"></span>`,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        }),
        title,
        zIndexOffset: selected ? 1000 : Math.round(fraction * 500),
      })
        .addTo(layer)
        .on("click", () => onSelectRef.current(can.can_id));
    }
  };
  drawRef.current = draw;

  useEffect(draw, [cans, selectedCanId, mode, intensity, intensityScaleMax, bucketDay, bucketHour, dayNames]);

  // Frame the fleet rather than trusting a hardcoded centre and zoom: the
  // cans sit in one part of the campus bounding box, so the default view left
  // several of them off the bottom of a short viewport.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map || fittedRef.current) return;
    const points = cans
      .filter((can) => can.latitude != null && can.longitude != null)
      .map((can) => [can.latitude as number, can.longitude as number] as [number, number]);
    if (points.length === 0) return;
    fittedRef.current = true;
    map.fitBounds(L.latLngBounds(points).pad(0.12), { animate: false, maxZoom: MAX_ZOOM });
  }, [cans, ready]);

  return (
    <div className="map-shell">
      <div
        ref={containerRef}
        className="map"
        style={{ ["--tile-dim" as string]: String(BASEMAPS[basemap].dim) }}
      />

      {onBasemapChange && (
        <div className="basemaps">
          {(Object.keys(BASEMAPS) as BasemapKey[]).map((key) => (
            <button
              key={key}
              className={`chip ${basemap === key ? "on" : ""}`}
              onClick={() => onBasemapChange(key)}
            >
              {BASEMAPS[key].label}
            </button>
          ))}
        </div>
      )}

      <div className="legend">
        {mode === "status" ? (
          <>
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
          </>
        ) : (
          <>
            <span className="legend-item">
              {bucketLabel(bucketDay, bucketHour, dayNames)}
            </span>
            <span className="legend-item ramp">
              <span className="dim">0</span>
              {[0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => (
                <span
                  key={f}
                  className="swatch square"
                  style={{ background: heatColor(f * intensityScaleMax, intensityScaleMax) }}
                />
              ))}
              <span className="dim">{intensityScaleMax}+</span>
            </span>
            <span className="legend-item note">items logged · white ring = fault or offline</span>
          </>
        )}
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
        .basemaps {
          position: absolute;
          right: 10px;
          top: 10px;
          z-index: 500;
          display: flex;
          gap: 3px;
          padding: 3px;
          background: var(--bg-card);
          border: 1px solid var(--border-08);
          border-radius: 3px;
        }
        .chip {
          padding: 2px 7px;
          border-radius: 2px;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 10px;
          line-height: 15px;
          color: var(--text-muted);
        }
        .chip:hover {
          background: var(--overlay-05);
          color: var(--text-secondary);
        }
        .chip.on {
          background: var(--overlay-08);
          color: var(--text-primary);
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
        .legend-item.ramp {
          gap: 2px;
        }
        .legend-item .dim {
          color: var(--text-dim);
          font-size: 9.5px;
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
        .swatch.square {
          width: 13px;
          height: 8px;
          border-radius: 1px;
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
        block. They are still driven entirely by the palette tokens and by the
        per-marker custom properties set above.
      */}
      <style jsx global>{`
        .leaflet-container {
          background: var(--bg);
          font-family: "Inter Variable", system-ui, sans-serif;
        }
        /* Keeps a bright basemap from competing with the data drawn on it.
           Applied to the tile pane only, so pins, heat and controls are
           untouched. */
        .leaflet-tile-pane {
          filter: brightness(var(--tile-dim, 1)) saturate(1.05);
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
        .can-pin-wrap,
        .heat-blob-wrap {
          background: none;
          border: none;
        }
        .heat-blob {
          display: block;
          width: 100%;
          height: 100%;
          border-radius: 50%;
          background: radial-gradient(
            circle,
            color-mix(in srgb, var(--heat) calc(var(--alpha) * 100%), transparent) 0%,
            color-mix(in srgb, var(--heat) calc(var(--alpha) * 45%), transparent) 45%,
            transparent 72%
          );
          mix-blend-mode: screen;
        }
        .can-pin {
          display: block;
          width: 15px;
          height: 15px;
          border-radius: 50%;
          /* A light rim instead of the page background: on satellite imagery a
             near-black ring disappears into tree cover, and the pin with it. */
          border: 2px solid rgba(255, 255, 255, 0.92);
          box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.55), 0 1px 3px rgba(0, 0, 0, 0.6);
          cursor: pointer;
          transition: transform 0.1s ease;
        }
        .can-pin:hover {
          transform: scale(1.3);
        }
        .can-pin.selected {
          box-shadow: 0 0 0 3px var(--primary), 0 0 0 4px rgba(0, 0, 0, 0.6);
          transform: scale(1.3);
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
        .can-pin.by-heat {
          background: var(--heat);
        }
        .can-pin.by-heat.attention {
          border-color: var(--text-primary);
          border-width: 3px;
        }
      `}</style>
    </div>
  );
}
