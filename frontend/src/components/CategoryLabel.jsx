import { normalizeCategory } from '../categories.js';

/**
 * Category text with its palette dot. `fallback` is what shows when the row
 * carries no category at all; the dot itself always normalizes to a known
 * palette entry.
 */
export default function CategoryLabel({ category, fallback = '' }) {
  return (
    <span className="cat-label">
      <span className={`cat-dot cat-${normalizeCategory(category)}`} />
      {category || fallback}
    </span>
  );
}
