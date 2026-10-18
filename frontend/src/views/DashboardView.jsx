import CatalogForm from '../components/CatalogForm.jsx';
import CategoryDonut from '../components/CategoryDonut.jsx';
import InsightsPanel from '../components/InsightsPanel.jsx';
import ItemsTable from '../components/ItemsTable.jsx';
import LocationsTable from '../components/LocationsTable.jsx';
import RecentEvents from '../components/RecentEvents.jsx';
import TopItemsChart from '../components/TopItemsChart.jsx';
import TrendChart from '../components/TrendChart.jsx';

export default function DashboardView({ hidden, days, onDaysChange, data }) {
  const { overview, items, locations, products, recommendations, events } = data;

  return (
    <div className="view" hidden={hidden}>
      <div className="topbar">
        <div>
          <h1>TossIQ</h1>
          <div className="subtitle">Waste intelligence dashboard &mdash; live from OCI</div>
        </div>
        <div>
          <label className="subtitle" htmlFor="daysSelect">
            Window:{' '}
          </label>
          <select
            id="daysSelect"
            value={days}
            onChange={(e) => onDaysChange(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </div>

      <div className="grid grid-hero">
        <div className="panel hero-tile">
          <h2>Total items</h2>
          <div className="hero-number">{overview ? overview.total_items : '—'}</div>
          <div className="hero-sub">{overview ? `Last ${overview.window_days} days` : ''}</div>
        </div>

        <div className="panel">
          <h2>Disposal trend</h2>
          <TrendChart trend={overview?.trend} />
        </div>
      </div>

      <div className="grid grid-split">
        <div className="panel">
          <h2>By category</h2>
          <CategoryDonut byCategory={overview?.by_category} />
        </div>

        <div className="panel">
          <h2>Top items</h2>
          <TopItemsChart topItems={overview?.top_items} />
        </div>
      </div>

      <div className="grid grid-pair">
        <div className="panel">
          <h2>Item-level detail</h2>
          <ItemsTable items={items} />
        </div>

        <div className="panel">
          <h2>By location</h2>
          <LocationsTable locations={locations} />
        </div>
      </div>

      <div className="grid grid-pair">
        <CatalogForm products={products} onAdded={data.refreshProducts} />
        <InsightsPanel
          days={days}
          recommendations={recommendations}
          onGenerated={data.refreshRecommendations}
        />
      </div>

      <div className="grid">
        <RecentEvents events={events} />
      </div>
    </div>
  );
}
