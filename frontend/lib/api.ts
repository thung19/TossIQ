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
  /** Flagged hazardous items inside this bucket. Carried on every
   * breakdown so "which building throws away the most dangerous things" is
   * answerable from the same query as "which throws away the most". */
  hazard_items: number;
  hazard_critical_items: number;
  avg_confidence: number | null;
};

export type Bucket = Measures & { bucket: string; share?: number };

export type AnalyticsOverview = Measures & {
  total_items: number;
  by_category: (Measures & { category: string })[];
  diverted_items: number;
  diversion_rate: number;
  catalog_match_rate: number;
  hazard_rate: number;
  estimate_notes: { mass: string; cost: string; unmatched: string; hazards: string };
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
  correct_bin: string | null;
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


// --- Recommendations ----------------------------------------------------
// Every recommendation carries the observations it came from. That is the
// contract: a card asserts something, and opening it shows the data behind
// the assertion rather than asking the reader to trust the sentence.
//
// `annual_saving` is always a PROJECTION from the window, never a booked
// figure, and the card says so. A null means the recommendation has no money
// attached (emptying a full bin saves nothing directly), not that it saves
// zero.

export type EvidenceMetric = {
  type: "metric";
  label: string;
  value: string;
  caption: string | null;
};

export type EvidenceTable = {
  type: "table";
  label: string;
  columns: string[];
  rows: (string | number)[][];
  caption: string | null;
};

export type EvidenceBars = {
  type: "bars";
  label: string;
  rows: { bucket: string; value: number; note: string | null }[];
  caption: string | null;
};

export type Evidence = EvidenceMetric | EvidenceTable | EvidenceBars;

export type RecommendationKind =
  | "infrastructure"
  | "procurement"
  | "food"
  | "operations"
  | "placement"
  | "sustainability"
  | "safety";

export type Recommendation = {
  key: string;
  kind: RecommendationKind;
  title: string;
  summary: string;
  action: string;
  evidence: Evidence[];
  /** What the rule measured, in plain language. */
  basis: string;
  window_days: number;
  annual_saving: number | null;
  /** Estimated kg CO2e a year. The axis that matters for switches whose
   * better option costs more -- a paper straw is dearer than a plastic one,
   * so ranking on money alone would argue against it. */
  annual_co2e_kg: number | null;
  annual_landfill_kg: number | null;
  confidence: "high" | "medium" | "low";
  caveat: string | null;
  /** Service-quality findings are shown whatever they return: a bin
   * overflowing at noon is worth fixing regardless of its payback. */
  exempt_from_materiality: boolean;
  /** Shown only when minor items are requested. */
  below_threshold: boolean;
};

export type RecommendationReport = {
  window_days: number;
  generated: number;
  recommendations: Recommendation[];
  projected_annual_saving: number;
  projected_annual_co2e_kg: number;
  projected_annual_landfill_kg: number;
  /** Findings held back for being too small to act on. Reported rather than
   * hidden, so a reader can see what was set aside and on what threshold. */
  suppressed_immaterial: number;
  /** Extra findings of a kind already represented, trimmed so one pattern
   * cannot own the page. */
  trimmed_duplicates: number;
  rules_run: number;
  /** Rules that threw. Surfaced rather than swallowed: a page listing nine
   * recommendations when it should list eleven is worse than one saying so. */
  rules_failed: string[];
  assumptions: Record<string, number>;
  impact_disclaimer: string;
  note: string;
};

export const KIND_LABEL: Record<RecommendationKind, string> = {
  infrastructure: "infrastructure",
  procurement: "purchasing",
  food: "food waste",
  operations: "operations",
  placement: "bin placement",
  sustainability: "diversion",
  safety: "safety",
};


// --- Hazards ------------------------------------------------------------
// The vision model raises the flag; hazards.py says what kind and how
// urgent. Severity is about RESPONSE TIME, not how unpleasant something is:
// critical means it can start a fire in a compacted load or injure whoever
// reaches in.

export type HazardSeverity = "critical" | "high" | "medium" | "unclassified";

export type HazardEvent = {
  event_id: number;
  detected_object: string | null;
  material: string | null;
  category: string | null;
  hazard_reason: string | null;
  hazard_class: string | null;
  hazard_severity: HazardSeverity | null;
  hazard_note: string | null;
  confidence: number | null;
  created_at: string | null;
  image_url: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  location: string | null;
  can_id: number | null;
  can_code: string | null;
  floor: string | null;
  placement_note: string | null;
  building_id: number | null;
  building_name: string | null;
  campus_area: string | null;
  /** Procedure for the class, served with the event rather than stored per
   * row -- a corrected instruction has to reach every item, not only the
   * ones logged after the correction. */
  display_name: string;
  handling: string;
  response_hours: number;
};

export type HazardOverdue = {
  event_id: number;
  detected_object: string | null;
  hazard_class: string | null;
  display_name: string;
  severity: HazardSeverity;
  building_name: string | null;
  can_code: string | null;
  created_at: string | null;
  hours_open: number;
  response_hours: number;
  hours_overdue: number;
};

export type HazardRecurrence = {
  building_name: string;
  building_id: number | null;
  hazard_class: string;
  severity: HazardSeverity;
  count: number;
  cans: number;
  last_seen: string | null;
  display_name: string;
  handling: string;
};

export type HazardSummary = {
  window_days: number;
  total: number;
  outstanding: number;
  by_severity: { severity: HazardSeverity; count: number; outstanding: number }[];
  by_class: {
    hazard_class: string;
    severity: HazardSeverity;
    count: number;
    outstanding: number;
    display_name: string;
    handling: string;
  }[];
  by_location: {
    building_name: string;
    building_id: number | null;
    hazard_class: string;
    severity: HazardSeverity;
    count: number;
    cans: number;
    last_seen: string | null;
  }[];
  /** Specific items nobody has acknowledged inside their severity's
   * response window. Somebody needs to go and deal with these. */
  overdue: HazardOverdue[];
  /** The same class recurring in one building. Dealing with each one
   * individually will not stop the next. */
  recurring: HazardRecurrence[];
  trend: { date: string; severity: HazardSeverity; count: number }[];
  response_hours: Record<string, number>;
  recurrence_threshold: number;
  note: string;
};

export const SEVERITY_RANK: Record<HazardSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  unclassified: 3,
};


// --- Initiatives and projects -------------------------------------------
// An initiative stores a measurement recipe, not a number. `metric` says
// what to measure and the scope fields say over what slice, so
// `current_value` is recomputed from logged disposals on every read.
//
// `progress_percent` is the distance travelled from baseline to target, not
// current-over-target: for a reduction goal that ratio exceeds 1 while you
// are failing, which reads as success. It can go negative, and that is the
// point -- "no progress" and "losing ground" are different facts.

export type InitiativeMetric =
  | "items"
  | "landfill_items"
  | "cost"
  | "mass"
  | "diversion_rate"
  | "contamination_rate"
  | "food_waste_cost"
  | "hazard_events"
  | "review_accuracy";

export type MetricSpec = {
  label: string;
  unit: string;
  format: "count" | "money" | "mass" | "percent";
  lower_is_better: boolean;
  help: string;
};

export type ProgressState =
  | "achieved"
  | "near_target"
  | "in_progress"
  | "off_track"
  | "regressing"
  | "unmeasured";

export type ProjectStatus = "proposed" | "in_progress" | "blocked" | "done" | "cancelled";

export type Project = {
  project_id: number;
  initiative_id: number | null;
  name: string;
  description: string | null;
  owner: string | null;
  status: ProjectStatus;
  /** What the action CLAIMS it will contribute, in its initiative's units.
   * Never added to measured progress: a pile of optimistic estimates must
   * not read as achievement. */
  expected_impact: number | null;
  expected_impact_note: string | null;
  source_recommendation_key: string | null;
  due_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  initiative_name?: string | null;
  initiative_metric?: string | null;
};

export type Initiative = {
  initiative_id: number;
  name: string;
  description: string | null;
  owner: string | null;
  metric: InitiativeMetric;
  direction: "reduce" | "increase";
  scope_building_id: number | null;
  scope_category: string | null;
  scope_material: string | null;
  scope_object: string | null;
  scope_supplier: string | null;
  baseline_value: number | null;
  baseline_window_days: number;
  baseline_captured_at: string | null;
  target_value: number;
  target_date: string | null;
  status: string;
  created_at: string | null;

  metric_label: string;
  unit: string;
  format: MetricSpec["format"];
  metric_help: string;
  scope_label: string;
  current_value: number | null;
  progress_percent: number | null;
  progress_state: ProgressState;
  distance_to_target: number | null;
  days_remaining: number | null;
  project_count: number;
  projects_by_status: Record<string, number>;
  projects_done: number;
  projects_active: number;
  claimed_impact: number;
  /** False when the slice this goal measures is too small for a target to
   * mean anything -- a goal to cut $3 to $1 is noise with a percentage sign
   * on it. Rates and safety metrics are never flagged. */
  is_material: boolean;
  materiality_note: string | null;
  /** Progress against the clock, not just against the target. "33% of the
   * way" says nothing alone: 33% with most of the year left is fine, 33%
   * with a fortnight to go is a goal about to be missed, and a goal with
   * no deadline is permanently on track and never finished. */
  pace_state:
    | "ahead"
    | "on_track"
    | "behind"
    | "at_risk"
    | "regressing"
    | "achieved"
    | "too_early"
    | "no_deadline"
    | "unmeasured";
  elapsed_percent: number | null;
  /** Set when on pace: when the current rate would reach the target. */
  projected_completion: string | null;
  /** Set when off pace: where the target date would actually find you. */
  projected_value: number | null;
  projected_hits_target: boolean | null;
  projects: Project[];
};

export type InitiativeReport = {
  initiatives: Initiative[];
  total: number;
  by_state: Record<string, number>;
  achieved: number;
  regressing: number;
  /** Active goals with no project under them. A goal with no work is a
   * wish, and the page says so rather than showing an encouraging bar. */
  unbacked: { initiative_id: number; name: string }[];
  overdue: { initiative_id: number; name: string; days_overdue: number }[];
  immaterial: { initiative_id: number; name: string; note: string | null }[];
  undated: { initiative_id: number; name: string }[];
  behind_pace: {
    initiative_id: number;
    name: string;
    pace_state: string;
    projected_value: number | null;
  }[];
  materiality_floor: Record<string, number>;
  metrics: Record<string, MetricSpec>;
  note: string;
};

export const PACE_LABEL: Record<string, string> = {
  ahead: "ahead of pace",
  on_track: "on pace",
  behind: "behind pace",
  at_risk: "at risk",
  regressing: "losing ground",
  achieved: "achieved",
  too_early: "too early to say",
  no_deadline: "no deadline set",
  unmeasured: "not measurable",
};

export const PROGRESS_LABEL: Record<ProgressState, string> = {
  achieved: "achieved",
  near_target: "near target",
  in_progress: "on the way",
  off_track: "off track",
  regressing: "losing ground",
  unmeasured: "not measurable",
};

export const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  proposed: "proposed",
  in_progress: "in progress",
  blocked: "blocked",
  done: "done",
  cancelled: "cancelled",
};

/** Formats a metric value in its own units. */
export function formatMetric(
  value: number | null | undefined,
  format: MetricSpec["format"]
): string {
  if (value == null) return "—";
  if (format === "money") {
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  if (format === "percent") return `${value.toFixed(1)}%`;
  if (format === "mass") {
    return value >= 1
      ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} kg`
      : `${Math.round(value * 1000)} g`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}
