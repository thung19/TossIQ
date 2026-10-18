type Variant = "in-progress" | "done" | "backlog" | "bug";

const COLORS: Record<Variant, string> = {
  "in-progress": "var(--status-in-progress)",
  done: "var(--status-done)",
  backlog: "var(--status-backlog)",
  bug: "var(--status-bug)",
};

export function StatusRing({ variant = "in-progress", size = 14 }: { variant?: Variant; size?: number }) {
  const color = COLORS[variant];
  if (variant === "backlog") {
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
        <circle cx="8" cy="8" r="6" fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="2 2" />
      </svg>
    );
  }
  if (variant === "done") {
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
        <circle cx="8" cy="8" r="7" fill={color} />
        <path d="M4.5 8l2.5 2.5L11.5 5.5" fill="none" stroke="#08090a" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (variant === "bug") {
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
        <circle cx="8" cy="8" r="4" fill={color} />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      <circle cx="8" cy="8" r="6" fill="none" stroke={color} strokeWidth="1.5" />
      <path d="M 8 2 a 6 6 0 0 1 6 6 H 8 V 2" fill={color} />
    </svg>
  );
}
