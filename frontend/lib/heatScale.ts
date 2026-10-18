/**
 * The one colour ramp the usage heatmap and the map's activity pins share.
 *
 * Sequential and perceptually ordered (a magma-style dark-purple to amber
 * run), for two reasons. It reads as "more" without a legend, which a rainbow
 * does not, and its stops stay distinguishable in greyscale and under the
 * common forms of colour blindness, because lightness climbs monotonically
 * along it rather than the hue alone doing the work.
 *
 * It is deliberately NOT the status palette from globals.css. Status
 * (ok / needs service / fault / offline) and usage are different questions,
 * and reusing green-amber-red for both would make a busy healthy can look
 * broken.
 */

export const HEAT_RAMP = [
  "#161a2e", // in scope, but nothing logged in this bucket
  "#2d1b5e",
  "#5b1f7d",
  "#90266f",
  "#c2384f",
  "#e9692c",
  "#f9c642", // at or above the scale bound
] as const;

/** Where `value` sits on the scale, 0..1, clamped. */
export function heatFraction(value: number, scaleMax: number): number {
  if (scaleMax <= 0) return 0;
  return Math.min(1, Math.max(0, value / scaleMax));
}

/**
 * Linear interpolation along HEAT_RAMP. A `value` at or above `scaleMax`
 * returns the top stop. The server bounds `scaleMax` at a percentile rather
 * than at the maximum, so over-scale buckets are expected; the UI flags them
 * rather than letting the clamp hide them.
 */
export function heatColor(value: number, scaleMax: number): string {
  if (value <= 0) return HEAT_RAMP[0];
  const position = heatFraction(value, scaleMax) * (HEAT_RAMP.length - 1);
  const lower = Math.floor(position);
  const upper = Math.min(HEAT_RAMP.length - 1, lower + 1);
  return mix(HEAT_RAMP[lower], HEAT_RAMP[upper], position - lower);
}

function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = rgb(a);
  const [br, bg, bb] = rgb(b);
  const channel = (x: number, y: number) => Math.round(x + (y - x) * t);
  return `rgb(${channel(ar, br)}, ${channel(ag, bg)}, ${channel(ab, bb)})`;
}

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Hour label for an axis tick or a readout: 0 -> "12a", 13 -> "1p". */
export function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "a" : "p";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}${suffix}`;
}

/**
 * The human name for a selected bucket, used in the map header and the panel
 * title: "Tue 1p", "Tuesdays", "1p, every day", or "all hours".
 */
export function bucketLabel(
  day: number | null,
  hour: number | null,
  dayNames: string[]
): string {
  const dayName = day == null ? null : dayNames[day] ?? `day ${day}`;
  if (dayName && hour != null) return `${dayName} ${hourLabel(hour)}`;
  if (dayName) return `${dayName}s`;
  if (hour != null) return `${hourLabel(hour)}, every day`;
  return "all hours";
}
