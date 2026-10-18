export const CATEGORY_ORDER = ['recycling', 'landfill', 'compost', 'unknown'];

// The palette maps one colour per category, so anything outside the known set
// collapses to `unknown` rather than rendering an unstyled dot.
export function normalizeCategory(cat) {
  return CATEGORY_ORDER.includes(cat) ? cat : 'unknown';
}
