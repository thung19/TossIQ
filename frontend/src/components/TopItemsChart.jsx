import { useTooltip } from './Tooltip.jsx';

export default function TopItemsChart({ topItems }) {
  const { showTooltip, hideTooltip } = useTooltip();

  if (!topItems || topItems.length === 0) return <div className="empty">No events yet</div>;

  const max = Math.max(1, ...topItems.map((i) => i.count));

  return (
    <>
      {topItems.map((item, idx) => {
        const show = (clientX, clientY) =>
          showTooltip(clientX, clientY, [`${item.count} disposals`, item.object]);
        return (
          <div
            key={`${item.object}-${idx}`}
            className="hbar-row"
            tabIndex={0}
            role="img"
            aria-label={`${item.object}: ${item.count}`}
            onPointerEnter={(e) => show(e.clientX, e.clientY)}
            onPointerMove={(e) => show(e.clientX, e.clientY)}
            onPointerLeave={hideTooltip}
            onFocus={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              show(rect.right, rect.top);
            }}
            onBlur={hideTooltip}
          >
            <div className="hbar-label" title={item.object}>
              {item.object}
            </div>
            <div className="hbar-track">
              <div className="hbar-fill" style={{ width: `${((item.count / max) * 100).toFixed(1)}%` }} />
            </div>
            <div className="hbar-value">{item.count}</div>
          </div>
        );
      })}
    </>
  );
}
