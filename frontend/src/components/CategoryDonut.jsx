import { useState } from 'react';
import { CATEGORY_ORDER, normalizeCategory } from '../categories.js';
import { useTooltip } from './Tooltip.jsx';

const R = 70;
const STROKE = 26;
const GAP = 3;
const CIRC = 2 * Math.PI * R;

function buildSegments(counts, total) {
  let cumulative = 0;
  return CATEGORY_ORDER.filter((cat) => counts[cat] > 0).map((cat) => {
    const frac = counts[cat] / total;
    const fullLen = frac * CIRC;
    const dashLen = Math.max(fullLen - GAP, 0.5);
    const seg = {
      cat,
      count: counts[cat],
      frac,
      dashOffset: -cumulative,
      dashLen,
      gapLen: CIRC - dashLen,
    };
    cumulative += fullLen;
    return seg;
  });
}

export default function CategoryDonut({ byCategory }) {
  const { showTooltip, hideTooltip } = useTooltip();
  const [highlighted, setHighlighted] = useState(null);

  const counts = {};
  CATEGORY_ORDER.forEach((c) => {
    counts[c] = 0;
  });
  (byCategory || []).forEach((c) => {
    counts[normalizeCategory(c.category)] += c.count;
  });
  const total = CATEGORY_ORDER.reduce((sum, c) => sum + counts[c], 0);

  if (total === 0) return <div className="empty">No events yet</div>;

  const segments = buildSegments(counts, total);

  const clear = () => {
    setHighlighted(null);
    hideTooltip();
  };

  return (
    <div className="donut-wrap">
      <svg className="donut-svg" viewBox="0 0 200 200" role="img" aria-label="Disposals by category">
        {segments.map((seg) => {
          const pct = (seg.frac * 100).toFixed(0);
          const show = (clientX, clientY) => {
            setHighlighted(seg.cat);
            showTooltip(clientX, clientY, [`${seg.count} items (${pct}%)`, seg.cat]);
          };
          return (
            <circle
              key={seg.cat}
              className={`donut-arc cat-${seg.cat}${highlighted && highlighted !== seg.cat ? ' dim' : ''}`}
              cx="100"
              cy="100"
              r={R}
              strokeWidth={STROKE}
              strokeDasharray={`${seg.dashLen.toFixed(2)} ${seg.gapLen.toFixed(2)}`}
              strokeDashoffset={seg.dashOffset.toFixed(2)}
              transform="rotate(-90 100 100)"
              tabIndex={0}
              role="img"
              aria-label={`${seg.cat}: ${seg.count} items`}
              onPointerEnter={(e) => show(e.clientX, e.clientY)}
              onPointerMove={(e) => show(e.clientX, e.clientY)}
              onPointerLeave={clear}
              onFocus={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                show(rect.left + rect.width / 2, rect.top);
              }}
              onBlur={clear}
            />
          );
        })}
        <text x="100" y="96" textAnchor="middle" className="donut-center-value">
          {total}
        </text>
        <text x="100" y="114" textAnchor="middle" className="donut-center-label">
          items
        </text>
      </svg>
      <div className="legend">
        {CATEGORY_ORDER.map((cat) => {
          const count = counts[cat];
          const pct = total ? ((count / total) * 100).toFixed(0) : '0';
          const show = (clientX, clientY) => {
            setHighlighted(cat);
            showTooltip(clientX, clientY, [`${count} items (${pct}%)`, cat]);
          };
          return (
            <button
              key={cat}
              type="button"
              className="legend-row"
              onPointerEnter={(e) => show(e.clientX, e.clientY)}
              onPointerLeave={clear}
              onFocus={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                show(rect.right, rect.top);
              }}
              onBlur={clear}
            >
              <span className="cat-label">
                <span className={`cat-dot cat-${cat}`} />
                {cat}
              </span>
              <span>
                <span className="legend-count">{count}</span> <span className="legend-pct">{pct}%</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
