import { useState } from 'react';
import { postJSON } from '../api.js';
import EventThumb from '../components/EventThumb.jsx';

const HAZARD_NEXT_STATUS = { open: 'acknowledged', acknowledged: 'resolved' };
const HAZARD_STATUS_LABEL = { open: 'Open', acknowledged: 'Acknowledged', resolved: 'Resolved' };

export default function HazardDetectionView({ hidden, hazards, onStatusChanged }) {
  const [pendingId, setPendingId] = useState(null);

  async function advance(eventId, nextStatus) {
    setPendingId(eventId);
    try {
      await postJSON(`/hazards/${eventId}/status`, { status: nextStatus });
      await onStatusChanged();
    } catch (err) {
      console.error(err);
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="view" hidden={hidden}>
      <div className="topbar">
        <div>
          <h1>Hazard Detection</h1>
          <div className="subtitle">
            AI-flagged hazards are preliminary &mdash; review, acknowledge, and resolve each
            incident.
          </div>
        </div>
      </div>

      <div className="grid">
        <div className="panel events-panel">
          <h2>Incidents</h2>
          <table>
            <thead>
              <tr>
                <th>Image</th>
                <th>Object</th>
                <th>Hazard reason</th>
                <th>Location</th>
                <th>Time</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {hazards.length === 0 ? (
                <tr>
                  <td className="empty" colSpan={7}>
                    No hazard incidents flagged
                  </td>
                </tr>
              ) : (
                hazards.map((h) => {
                  const next = HAZARD_NEXT_STATUS[h.hazard_status];
                  return (
                    <tr key={h.event_id}>
                      <td>
                        <EventThumb imageUrl={h.image_url} />
                      </td>
                      <td>{h.detected_object || '—'}</td>
                      <td>{h.hazard_reason || '—'}</td>
                      <td>{h.location || '—'}</td>
                      <td>{h.date || '—'}</td>
                      <td>
                        <span className={`hazard-status status-${h.hazard_status}`}>
                          {HAZARD_STATUS_LABEL[h.hazard_status] || h.hazard_status}
                        </span>
                      </td>
                      <td>
                        {next ? (
                          <button
                            type="button"
                            className="hazard-action-btn"
                            disabled={pendingId === h.event_id}
                            onClick={() => advance(h.event_id, next)}
                          >
                            Mark {HAZARD_STATUS_LABEL[next]}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
