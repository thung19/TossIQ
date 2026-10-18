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
