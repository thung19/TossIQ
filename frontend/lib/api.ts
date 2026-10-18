export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE ||
  API_BASE.replace(/^http/, "ws");

export async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

/** POST variant of apiFetch. Surfaces FastAPI's `detail` string so a
 * backend failure (e.g. OCI unreachable on /asku) renders as the message
 * the API wrote rather than a bare status code. */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (typeof d?.detail === "string" ? d.detail : null))
      .catch(() => null);
    throw new Error(detail || `${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type Detection = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  confidence: number;
  category: "recycling" | "compost" | "landfill" | null;
};

export type DetectionEvent = {
  timestamp: number;
  inference_ms: number;
  detections: Detection[];
};

export type CameraStats = {
  running: boolean;
  camera_opened: boolean;
  frames: number;
  detections: number;
  last_inference_ms: number | null;
  started_at: number | null;
  error: string | null;
  latest_detections: Detection[];
};

export type StatsOverview = {
  window_days: number;
  total_items: number;
  by_category: { category: string; count: number }[];
  top_items: { object: string; count: number }[];
  trend: { date: string; count: number }[];
};

export type WasteEvent = {
  event_id: number;
  detected_object: string | null;
  material: string | null;
  category: string | null;
  location: string | null;
  confidence: number | null;
  image_key: string | null;
  created_at: string | null;
  hazard_flag: number | null;
  hazard_reason: string | null;
  visible_text: string | null;
  reusable_condition: string | null;
};

export type Product = {
  product_id: number;
  product_name: string;
  supplier: string | null;
  sku: string | null;
  material: string | null;
  unit_cost: number | null;
};

export type AskuObservationSection = {
  title: string;
  lines: string[];
};

export type AskuAnswer = {
  question: string;
  answer: string;
  window_days: number;
  model_id: string;
  grounding: AskuObservationSection[];
};

// --- Campus fleet -------------------------------------------------------
// status and fill_source are resolved server-side by fleet.py. The frontend
// never recomputes them: it maps a status to a colour and renders the reasons
// the API supplies, so retuning a threshold needs no change here.

export type CanStatus = "ok" | "needs_service" | "fault" | "offline";

// "unknown" is the honest answer for a can with no fill signal: there are no
// weight sensors, so a can with nothing attributed to it reports no fill
// rather than 0% observed.
export type FillSource = "observed" | "simulated" | "unknown" | null;

export type Can = {
  can_id: number;
  can_code: string;
  floor: string | null;
  placement_note: string | null;
  latitude: number | null;
  longitude: number | null;
  installed_on: string | null;
  lifecycle_status: string;
  is_simulated: number;
  model_id: number;
  model_code: string;
  model_name: string;
  capacity_liters: number | null;
  capacity_items: number;
  height_cm: number | null;
  stream_count: number | null;
  has_camera: number;
  has_actuator: number;
  firmware_version: string | null;
  building_id: number;
  building_code: string;
  building_name: string;
  campus_area: string | null;
  reported_at: string | null;
  fill_percent: number | null;
  fill_source: FillSource;
  camera_ok: number | null;
  actuator_ok: number | null;
  connectivity_ok: number | null;
  battery_percent: number | null;
  fault_code: string | null;
  fault_detail: string | null;
  last_emptied_at: string | null;
  events_since_emptied: number;
  status: CanStatus;
  status_reasons: string[];
};

export type CanReading = {
  reading_id: number;
  reported_at: string | null;
  fill_percent: number | null;
  fill_source: FillSource;
  camera_ok: number | null;
  actuator_ok: number | null;
  connectivity_ok: number | null;
  battery_percent: number | null;
  fault_code: string | null;
  fault_detail: string | null;
};

export type ServiceEvent = {
  service_id: number;
  service_type: string;
  performed_at: string | null;
  performed_by: string | null;
  notes: string | null;
};

export type CanDetail = Can & {
  readings: CanReading[];
  service_events: ServiceEvent[];
};

export type CanContents = {
  can_id: number;
  since: string | null;
  window_days: number | null;
  total_items: number;
  by_category: { category: string; count: number }[];
  top_items: {
    detected_object: string | null;
    matched_product: string | null;
    count: number;
    estimated_value: number | null;
  }[];
  estimated_value: number | null;
  events: (WasteEvent & { image_url: string | null })[];
};

export type CanModel = {
  model_id: number;
  model_code: string;
  display_name: string;
  capacity_liters: number | null;
  capacity_items: number;
  height_cm: number | null;
  stream_count: number | null;
  has_camera: number;
  has_actuator: number;
  firmware_version: string | null;
  released_on: string | null;
};

export type Building = {
  building_id: number;
  building_code: string;
  name: string;
  campus_area: string | null;
  latitude: number | null;
  longitude: number | null;
  can_count: number;
};

export type FleetSummary = {
  total: number;
  by_status: Record<CanStatus, number>;
  simulated: number;
  observed: number;
  stale_minutes: number;
  service_threshold_percent: number;
};


// --- Usage heatmap ------------------------------------------------------
// Counts are logged disposal events, i.e. how OFTEN a can is used. With no
// weight sensors there is no volume to report, so nothing here should be
// labelled as fullness.
//
// day_of_week is 0 = Monday .. 6 = Sunday. scale_max_* is a high percentile
// rather than the maximum, computed server-side so the grid and the map pins
// normalise against the same denominator; a bucket above it is genuinely
// over-scale and the UI says so rather than clipping it silently.

export type ActivityCell = {
  can_id: number;
  day_of_week: number;
  hour_of_day: number;
  count: number;
};

export type ActivityPeak = {
  day_of_week: number;
  day_name: string;
  hour_of_day: number;
  count: number;
};

export type FleetActivity = {
  window_days: number;
  total_events: number;
  /** Sparse: only buckets that saw a disposal. */
  cells: ActivityCell[];
  /** Dense 7 x 24, summed over cans. */
  day_hour: number[][];
  by_hour: number[];
  by_day: number[];
  by_can: { can_id: number; count: number }[];
  max_cell: number;
  max_can: number;
  scale_max_cell: number;
  scale_max_can: number;
  /** Largest single bucket in the window. May well be a one-off burst. */
  peak: ActivityPeak | null;
  /** Median across the seven weekdays for each hour: the recurring rhythm,
   * unmoved by a single day's spike. */
  typical_by_hour: number[];
  typical_peak: { hour_of_day: number; count: number } | null;
  day_names: string[];
};

/** A slice of the heatmap. Either coordinate may be left open: a day with no
 * hour is the whole day, an hour with no day is that hour across the week. */
export type TimeBucket = { day: number | null; hour: number | null };

export const WHOLE_WINDOW: TimeBucket = { day: null, hour: null };

/** Per-can counts inside one bucket. Mirrors fleet.activity_for_bucket; the
 * cells are already in the client so re-querying the API on every cell click
 * would add a round trip for an aggregation over a few hundred rows. */
export function canCountsForBucket(
  cells: ActivityCell[],
  bucket: TimeBucket
): Map<number, number> {
  const totals = new Map<number, number>();
  for (const cell of cells) {
    if (bucket.day != null && cell.day_of_week !== bucket.day) continue;
    if (bucket.hour != null && cell.hour_of_day !== bucket.hour) continue;
    totals.set(cell.can_id, (totals.get(cell.can_id) ?? 0) + cell.count);
  }
  return totals;
}
