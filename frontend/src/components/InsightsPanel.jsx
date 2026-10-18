import { useState } from 'react';

export default function InsightsPanel({ days, recommendations, onGenerated }) {
  const [status, setStatus] = useState({ text: '', kind: '' });
  const [running, setRunning] = useState(false);

  async function generate() {
    setRunning(true);
    setStatus({ text: 'Generating...', kind: '' });
    try {
      const res = await fetch(`/recommendations/generate?days=${days}`, { method: 'POST' });
      const data = await res.json();
      setStatus({
        text: data.new_recommendations.length
          ? `${data.new_recommendations.length} new recommendation(s).`
          : 'No new recommendations (nothing new meets the thresholds yet).',
        kind: 'status-good',
      });
      await onGenerated();
    } catch (err) {
      setStatus({ text: `Failed: ${err.message}`, kind: 'status-critical' });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="panel">
      <h2>Insights &amp; recommendations</h2>
      <button type="button" onClick={generate} disabled={running}>
        Generate insights
      </button>
      <div className={`status-msg ${status.kind}`.trim()}>{status.text}</div>
      <div style={{ marginTop: '12px' }}>
        {recommendations.length === 0 ? (
          <div className="empty">
            No recommendations yet &mdash; click "Generate insights" once you have some disposal
            events logged.
          </div>
        ) : (
          recommendations.map((r, idx) => (
            <div className="rec-item" key={r.id ?? `${r.created_at}-${idx}`}>
              {r.text}
              <div className="rec-time">{r.created_at}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
