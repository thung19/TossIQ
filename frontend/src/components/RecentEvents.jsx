import CategoryLabel from './CategoryLabel.jsx';
import EventThumb from './EventThumb.jsx';

export default function RecentEvents({ events }) {
  return (
    <div className="panel events-panel">
      <h2>Recent events</h2>
      <table>
        <thead>
          <tr>
            <th>Image</th>
            <th>Object</th>
            <th>Category</th>
            <th>Location</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {events.length === 0 ? (
            <tr>
              <td className="empty" colSpan={5}>
                No events yet
              </td>
            </tr>
          ) : (
            events.map((e) => (
              <tr key={e.event_id ?? `${e.created_at}-${e.detected_object}`}>
                <td>
                  <EventThumb imageUrl={e.image_url} />
                </td>
                <td>
                  {e.detected_object || '—'}
                  {e.hazard_flag ? (
                    <>
                      {' '}
                      <span className="hazard-badge" title={e.hazard_reason || 'Potential hazard'}>
                        &#9888; Hazard
                      </span>
                    </>
                  ) : null}
                </td>
                <td>
                  <CategoryLabel category={e.category} fallback="unknown" />
                </td>
                <td>{e.location || '—'}</td>
                <td>{e.created_at}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
