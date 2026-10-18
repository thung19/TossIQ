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


// --- Analytics ----------------------------------------------------------
// Every figure named `estimated_*` is modelled, not measured. There are no
// weight sensors on any can, so all mass is (items x catalog reference mass);
// cost is the catalog's loss-on-discard, which is 0.00 for consumed residue
// like peels and spent grounds. `matched_count` and the two cost-provenance
// fields say how much of a total rests on a specific product match rather
// than on the average across a vision label's variants.

export type Measures = {
  count: number;
  matched_count: number;
  estimated_cost: number;
  estimated_grams: number;
  estimated_kg: number;
  cost_from_matched: number;
  cost_from_class_average: number;
  no_cost_items: number;
  avg_confidence: number | null;
};

export type Bucket = Measures & { bucket: string; share?: number };

export type AnalyticsOverview = Measures & {
  total_items: number;
  by_category: (Measures & { category: string })[];
  diverted_items: number;
  diversion_rate: number;
  catalog_match_rate: number;
  estimate_notes: { mass: string; cost: string; unmatched: string };
};

export type AnalyticsDistribution = {
  dimension: string;
  rows: Bucket[];
  shown_count: number;
  total_count: number;
  truncated: boolean;
};

export type AnalyticsHotspots = {
  by_building: Bucket[];
  by_campus_area: Bucket[];
  by_can: Bucket[];
};

export type BinComposition = {
  can_id: number;
  can_code: string;
  building_name: string | null;
  shown_items: number;
  items: { item: string; category: string; count: number; estimated_cost: number }[];
};

export type MisroutedReport = {
  rows: {
    item: string;
    logged_as: string;
    should_be: string;
    count: number;
    grams: number;
    estimated_kg: number;
  }[];
  misrouted_count: number;
  total_items: number;
  misrouted_rate: number;
  note: string;
};

export type AccuracyReport = {
  reviewed_events: number;
  total_events: number;
  review_coverage: number;
  correct: number;
  /** null when nothing in scope has been reviewed -- not zero, which would
   * read as "the classifier got everything wrong". */
  accuracy: number | null;
  by_category: { category: string; reviewed: number; correct: number; accuracy: number }[];
  calibration: {
    label: string;
    lower: number;
    reviewed: number;
    correct: number;
    accuracy: number | null;
  }[];
  unscored_reviews: number;
  confusions: { seen_as: string; actually_was: string; count: number }[];
  note: string;
};

export type CatalogSku = Measures & {
  sku: string;
  product_name: string | null;
  brand: string | null;
  variant_label: string | null;
  supplier: string | null;
  material: string | null;
  material_subtype: string | null;
  unit_cost: number | null;
  unit_weight_grams: number | null;
  intended_stream: string | null;
  recyclable: number | null;
  case_pack_qty: number | null;
  case_cost: number | null;
  cases_equivalent: number | null;
};

export type CatalogRollup = {
  skus: CatalogSku[];
  by_supplier: Bucket[];
  catalog_size: number;
};

export type AnalyticsFilterOptions = {
  categories: string[];
  materials: string[];
  objects: string[];
  suppliers: string[];
};

/** The filter set every /analytics/* route accepts. Kept as one object so the
 * page narrows together: a building chosen once applies to the composition,
 * the hotspots, the supplies table and the accuracy sample alike. */
export type AnalyticsFilterState = {
  days: number;
  buildingId: string;
  canId: string;
  category: string;
  material: string;
  detectedObject: string;
  supplier: string;
};

export const EMPTY_ANALYTICS_FILTERS: AnalyticsFilterState = {
  days: 30,
  buildingId: "",
  canId: "",
  category: "",
  material: "",
  detectedObject: "",
  supplier: "",
};

/** Serialises the filter state into the query string the API expects. Only
 * set values are sent, so an unfiltered request stays readable in the log. */
export function analyticsQuery(
  filters: AnalyticsFilterState,
  extra: Record<string, string | number | undefined> = {}
): string {
  const params = new URLSearchParams();
  params.set("days", String(filters.days));
  if (filters.buildingId) params.set("building_id", filters.buildingId);
  if (filters.canId) params.set("can_id", filters.canId);
  if (filters.category) params.set("category", filters.category);
  if (filters.material) params.set("material", filters.material);
  if (filters.detectedObject) params.set("detected_object", filters.detectedObject);
  if (filters.supplier) params.set("supplier", filters.supplier);
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return `?${params.toString()}`;
}

/** How many filters beyond the time window are active -- drives the "clear"
 * affordance and the count badge. */
export function activeAnalyticsFilterCount(filters: AnalyticsFilterState): number {
  return [
    filters.buildingId,
    filters.canId,
    filters.category,
    filters.material,
    filters.detectedObject,
    filters.supplier,
  ].filter(Boolean).length;
}

/** The three ways every distribution can be measured. Items is counted;
 * the other two are catalog estimates, which the UI labels wherever it
 * shows them. */
export type Measure = "count" | "cost" | "mass";

export const MEASURE_LABEL: Record<Measure, string> = {
  count: "items",
  cost: "est. cost",
  mass: "est. mass",
};

export function measureValue(row: Measures, measure: Measure): number {
  if (measure === "cost") return row.estimated_cost;
  if (measure === "mass") return row.estimated_kg;
  return row.count;
}

export function formatMeasure(value: number, measure: Measure): string {
  if (measure === "cost") {
    return `$${value.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  if (measure === "mass") {
    return value >= 1
      ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} kg`
      : `${Math.round(value * 1000)} g`;
  }
  return value.toLocaleString();
}
