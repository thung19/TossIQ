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

export type FillSource = "observed" | "simulated" | null;

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

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}
