import { useState } from 'react';
import Sidebar from './components/Sidebar.jsx';
import { TooltipProvider } from './components/Tooltip.jsx';
import { PLACEHOLDER_TEXT } from './navigation.js';
import useDashboardData from './useDashboardData.js';
import DashboardView from './views/DashboardView.jsx';
import HazardDetectionView from './views/HazardDetectionView.jsx';
import IdentifyItemView from './views/IdentifyItemView.jsx';
import PlaceholderView from './views/PlaceholderView.jsx';

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [days, setDays] = useState(30);

  // Polling runs at the shell level so the hazard view and the dashboard share
  // one refresh cycle, as they did before the React split.
  const data = useDashboardData(days);

  function navigate(viewId) {
    setActiveView(viewId);
    setSidebarOpen(false);
  }

  return (
    <TooltipProvider>
      <div className="app-shell">
        <button
          type="button"
          className="nav-toggle"
          aria-label="Toggle navigation"
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((open) => !open)}
        >
          &#9776;
        </button>
        <div
          className={`sidebar-overlay${sidebarOpen ? ' open' : ''}`}
          onClick={() => setSidebarOpen(false)}
        />
        <Sidebar activeView={activeView} onNavigate={navigate} open={sidebarOpen} />

        {/* Every view stays mounted and is toggled with `hidden`, matching the
            pre-React shell. Unmounting would discard in-progress local state
            (a half-filled catalog form, a status message) on navigation. */}
        <main className="main-content">
          <DashboardView
            hidden={activeView !== 'dashboard'}
            days={days}
            onDaysChange={setDays}
            data={data}
          />
          <HazardDetectionView
            hidden={activeView !== 'hazard-detection'}
            hazards={data.hazards}
            onStatusChanged={data.refreshHazards}
          />
          <IdentifyItemView hidden={activeView !== 'identify-item'} />
          {Object.entries(PLACEHOLDER_TEXT).map(([viewId, text]) => (
            <PlaceholderView key={viewId} hidden={activeView !== viewId} text={text} />
          ))}
        </main>
      </div>
    </TooltipProvider>
  );
}
