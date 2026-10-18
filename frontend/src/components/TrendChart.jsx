import { useRef, useState } from 'react';
import { useTooltip } from './Tooltip.jsx';

const W = 680;
const H = 180;
const PAD_L = 36;
const PAD_R = 12;
const PAD_T = 16;
const PAD_B = 26;

export default function TrendChart({ trend }) {
  const { showTooltip, hideTooltip } = useTooltip();
  const svgRef = useRef(null);
  // Null until first focus, when it starts on the most recent point like the
  // pre-React chart did.
  const focusIdx = useRef(null);
  const [crosshairX, setCrosshairX] = useState(null);

  if (!trend || trend.length === 0) return <div className="empty">No events yet</div>;

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const n = trend.length;
  const maxCount = Math.max(1, ...trend.map((t) => t.count));

  const xAt = (i) => PAD_L + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (v) => PAD_T + plotH - (v / maxCount) * plotH;
  const points = trend.map((t, i) => [xAt(i), yAt(t.count)]);

  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(' ');
  const areaPath = `${linePath} L${points[n - 1][0].toFixed(1)},${(PAD_T + plotH).toFixed(1)} L${points[0][0].toFixed(1)},${(PAD_T + plotH).toFixed(1)} Z`;

  const yTicks = [...new Set([0, Math.round(maxCount / 2), maxCount])];
  const xIdxs = n === 1 ? [0] : [...new Set([0, Math.floor((n - 1) / 2), n - 1])];

  function nearestIndex(clientX) {
    const rect = svgRef.current.getBoundingClientRect();
    const svgX = ((clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(p[0] - svgX);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    return best;
  }

  function showAt(i, clientX, clientY) {
    setCrosshairX(points[i][0]);
    showTooltip(clientX, clientY, [`${trend[i].count} items`, trend[i].date]);
  }

  function clientPointFor(i) {
    const rect = svgRef.current.getBoundingClientRect();
    const p = points[i];
    return [rect.left + (p[0] / W) * rect.width, rect.top + (p[1] / H) * rect.height];
  }

  function hide() {
    setCrosshairX(null);
    hideTooltip();
  }

  function showFocused() {
    const base = focusIdx.current === null ? n - 1 : focusIdx.current;
    const i = Math.min(n - 1, Math.max(0, base));
    focusIdx.current = i;
    const [cx, cy] = clientPointFor(i);
    showAt(i, cx, cy);
  }

  return (
    <svg
      ref={svgRef}
      className="trend-svg"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Disposal volume over time"
    >
      {yTicks.map((t) => (
        <line
          key={`grid-${t}`}
          className="gridline-svg"
          x1={PAD_L}
          x2={W - PAD_R}
          y1={yAt(t).toFixed(1)}
          y2={yAt(t).toFixed(1)}
        />
      ))}
      <path className="trend-area" d={areaPath} />
      <path className="trend-line" d={linePath} />
      {points.map((p, i) => (
        <circle key={`dot-${i}`} className="trend-dot" cx={p[0].toFixed(1)} cy={p[1].toFixed(1)} r="3" />
      ))}
      {yTicks.map((t) => (
        <text
          key={`ylab-${t}`}
          className="axis-label"
          x={PAD_L - 8}
          y={yAt(t).toFixed(1)}
          textAnchor="end"
          dominantBaseline="middle"
        >
          {t}
        </text>
      ))}
      {xIdxs.map((i) => (
        <text key={`xlab-${i}`} className="axis-label" x={xAt(i).toFixed(1)} y={H - 8} textAnchor="middle">
          {trend[i].date.slice(5)}
        </text>
      ))}
      {crosshairX !== null && (
        <line className="crosshair" x1={crosshairX} x2={crosshairX} y1={PAD_T} y2={PAD_T + plotH} />
      )}
      <rect
        className="trend-hit"
        x={PAD_L}
        y={PAD_T}
        width={plotW}
        height={plotH}
        fill="transparent"
        tabIndex={0}
        onPointerMove={(e) => showAt(nearestIndex(e.clientX), e.clientX, e.clientY)}
        onPointerLeave={hide}
        onFocus={showFocused}
        onBlur={hide}
        onKeyDown={(e) => {
          const base = focusIdx.current === null ? n - 1 : focusIdx.current;
          if (e.key === 'ArrowRight') focusIdx.current = Math.min(n - 1, base + 1);
          else if (e.key === 'ArrowLeft') focusIdx.current = Math.max(0, base - 1);
          else return;
          e.preventDefault();
          showFocused();
        }}
      />
    </svg>
  );
}
