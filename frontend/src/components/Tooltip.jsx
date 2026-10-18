import { createContext, useCallback, useContext, useMemo, useState } from 'react';

const TooltipContext = createContext(null);

export function useTooltip() {
  return useContext(TooltipContext);
}

/**
 * One fixed-position tooltip shared by every chart, matching the single
 * `.chart-tooltip` node the pre-React dashboard appended to the body.
 */
export function TooltipProvider({ children }) {
  const [tip, setTip] = useState(null);

  const showTooltip = useCallback((clientX, clientY, lines) => {
    setTip({ x: clientX, y: clientY, lines });
  }, []);
  const hideTooltip = useCallback(() => setTip(null), []);

  const value = useMemo(() => ({ showTooltip, hideTooltip }), [showTooltip, hideTooltip]);

  return (
    <TooltipContext.Provider value={value}>
      {children}
      {tip && (
        <div className="chart-tooltip" style={{ left: `${tip.x}px`, top: `${tip.y}px` }}>
          {tip.lines.map((line, i) => (
            <div key={i} className={i === 0 ? 'tip-value' : 'tip-label'}>
              {line}
            </div>
          ))}
        </div>
      )}
    </TooltipContext.Provider>
  );
}
