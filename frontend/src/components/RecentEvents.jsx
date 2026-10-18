import { Fragment, useState } from 'react';
import { fetchJSON } from '../api.js';
import { similarityText } from '../similarity.js';
import CategoryLabel from './CategoryLabel.jsx';
import EventThumb from './EventThumb.jsx';

/**
 * The recent-events list, plus per-event similar-item search.
 *
 * "Similar" asks the API for that event's visually closest past disposals --
 * Oracle AI Database vector search over the Cohere image embedding stored with
 * each event -- and expands them beneath the row. One lookup is open at a
 * time, and it is requested on click rather than with the list, because it
 * costs a vector search per event.
 */
export default function RecentEvents({ events }) {
  const [openId, setOpenId] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [state, setState] = useState('idle'); // idle | loading | ready | error
  const [error, setError] = useState('');

  async function toggleSimilar(eventId) {
    if (openId === eventId) {
      setOpenId(null);
      return;
    }
    setOpenId(eventId);
    setSimilar([]);
    setError('');
    setState('loading');
    try {
      setSimilar(await fetchJSON(`/events/${eventId}/similar?limit=6`));
      setState('ready');
    } catch (err) {
      setError(err.message);
      setState('error');
    }
  }

  function similarCell() {
    if (state === 'loading') return <div className="empty">Searching stored embeddings...</div>;
    if (state === 'error') {
      return <div className="status-msg status-critical">Similar-item search failed: {error}</div>;
    }
    if (similar.length === 0) {
      return (
        <div className="empty">
          No visually similar past disposals. This needs a stored image embedding on both this
          event and an earlier one.
        </div>
      );
    }
    return (
      <>
        <div className="similar-caption">
          Closest past disposals by image embedding, nearest first.
        </div>
        <div className="similar-strip">
          {similar.map((s) => (
            <div className="similar-card" key={s.event_id}>
              <EventThumb imageUrl={s.image_url} />
              <div className="similar-meta">
                <div className="similar-object">{s.detected_object || '—'}</div>
                <div className="similar-score">{similarityText(s.distance)}</div>
                <div className="similar-when">{s.created_at || '—'}</div>
              </div>
            </div>
          ))}
        </div>
      </>
    );
  }

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
            <th />
          </tr>
        </thead>
        <tbody>
          {events.length === 0 ? (
            <tr>
              <td className="empty" colSpan={6}>
                No events yet
              </td>
            </tr>
          ) : (
            events.map((e) => (
              <Fragment key={e.event_id ?? `${e.created_at}-${e.detected_object}`}>
                <tr>
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
                  <td>
                    {e.event_id ? (
                      <button
                        type="button"
                        className="btn-inline"
                        aria-expanded={openId === e.event_id}
                        onClick={() => toggleSimilar(e.event_id)}
                      >
                        {openId === e.event_id ? 'Hide similar' : 'Similar'}
                      </button>
                    ) : null}
                  </td>
                </tr>
                {openId === e.event_id ? (
                  <tr className="similar-row">
                    <td colSpan={6}>{similarCell()}</td>
                  </tr>
                ) : null}
              </Fragment>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
