type Category = "recycling" | "compost" | "landfill" | "unknown" | string | null;

export const CATEGORY_COLOR: Record<string, string> = {
  recycling: "var(--cat-recycling)",
  compost: "var(--cat-compost)",
  landfill: "var(--cat-landfill)",
  unknown: "var(--cat-unknown)",
};

export function CategoryDot({ category, size = 8 }: { category: Category; size?: number }) {
  const key = category || "unknown";
  const color = CATEGORY_COLOR[key] || "var(--cat-unknown)";
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: color,
        display: "inline-block",
        flexShrink: 0,
      }}
    />
  );
}

export function CategoryLabel({ category }: { category: Category }) {
  const key = category || "unknown";
  const text = key.charAt(0).toUpperCase() + key.slice(1);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <CategoryDot category={category} />
      <span style={{ fontSize: 13, fontWeight: 510, color: "var(--text-secondary)" }}>{text}</span>
    </span>
  );
}
