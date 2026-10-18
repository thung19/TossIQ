import { useEffect, useState } from 'react';
import { fetchJSON } from '../api.js';
import CatalogForm from '../components/CatalogForm.jsx';
import CategoryLabel from '../components/CategoryLabel.jsx';
import EventThumb from '../components/EventThumb.jsx';

/**
 * Unknown-item discovery: what the organization throws away repeatedly but has
 * never catalogued.
 *
 * Every advanced-analysis event stores its item photo's Cohere Embed v4
 * embedding, so the events that matched no catalog product can be grouped by
 * visual similarity with Oracle AI Database vector search -- no labels, no
 * training, no model knows what these items are. Each group is an offer to
 * teach one: the action opens the normal catalog form with the group's
 * representative photo as the product's reference image, which is exactly what
 * makes future disposals of it match.
 *
 * The clustering compares every unmatched event in the window against every
 * other, so it is fetched when this view is opened and on an explicit refresh,
 * never on the dashboard's 5-second poll.
 */
export default function WasteAuditView({ hidden, products, onProductAdded }) {
  const [report, setReport] = useState(null);
  const [state, setState] = useState('idle'); // idle | loading | ready | error
  const [error, setError] = useState('');
  const [teaching, setTeaching] = useState(null);

  async function load() {
    setState('loading');
    setError('');
    try {
      setReport(await fetchJSON('/events/unknown-clusters?days=30'));
      setState('ready');
    } catch (err) {
      setError(err.message);
      setState('error');
    }
  }

  // Loads the first time the view is opened, not while it sits hidden behind
  // another view.
  useEffect(() => {
    if (!hidden && state === 'idle') load();
  }, [hidden, state]);

  const clusters = report?.clusters ?? [];

  return (
    <div className="view" hidden={hidden}>
      <div className="topbar">
        <div>
          <h1>AI Insights / Waste Audit</h1>
          <div className="subtitle">
            Repeatedly discarded items that match nothing in the catalog &mdash; the organization&rsquo;s
            blind spots.
          </div>
        </div>
        <button type="button" onClick={load} disabled={state === 'loading'}>
          {state === 'loading' ? 'Grouping...' : 'Refresh'}
        </button>
      </div>

      <div className="panel audit-explainer">
        <h2>How these groups are found</h2>
        <p>
          Each item photographed for advanced analysis is turned into a{' '}
          <strong>Cohere Embed v4 image embedding</strong> and stored alongside its disposal event.
          The events below <strong>matched no catalog entry</strong> &mdash; not by name and not by
          reference image &mdash; and were grouped purely by how close their photos sit in that
          embedding space, using <strong>Oracle AI Database native vector search</strong>{' '}
          (<code>VECTOR_DISTANCE</code>, cosine).
        </p>
        <p>
          Nothing here is labelled or trained. A group means &ldquo;these photos look like the same
          thing, and TossIQ has never been told what it is.&rdquo; Add one to the catalog and future
          disposals of it are recognised, with no retraining.
        </p>
        <p className="audit-caveat">
          The similarity threshold is a heuristic, not a tuned value. Treat a group as a prompt to
          look, not as a verdict.
        </p>
      </div>

      <div className="panel">
        <h2>
          Unidentified item groups
          {report
            ? ` — ${clusters.length} group${clusters.length === 1 ? '' : 's'} across the most recent ${
                report.unmatched_events
              } unmatched events`
            : ''}
        </h2>

        {state === 'loading' && !report ? (
          <div className="empty">Comparing unmatched item photos...</div>
        ) : null}

        {state === 'error' ? (
          <div className="status-msg status-critical">Could not load the audit: {error}</div>
        ) : null}

        {report && clusters.length === 0 ? (
          <div className="empty">
            {report.unmatched_events === 0
              ? `No disposal events in the last ${report.window_days} days are both unmatched and carry an image embedding, so there is nothing to group yet.`
              : `The most recent ${report.unmatched_events} unmatched event(s) in the last ${report.window_days} days were compared, but no two were visually alike enough to group. Nothing is being thrown away repeatedly and unrecognised yet.`}
          </div>
        ) : null}

        {clusters.map((cluster) => {
          const representative =
            cluster.members.find((m) => m.event_id === cluster.representative_event_id) ??
            cluster.members[0];
          const names = [...new Set(cluster.members.map((m) => m.detected_object).filter(Boolean))];
          const isTeaching = teaching === cluster.representative_event_id;

          return (
            <div className="audit-cluster" key={cluster.representative_event_id}>
              <div className="audit-cluster-head">
                <div>
                  <div className="audit-count">
                    Seen {cluster.size} time{cluster.size === 1 ? '' : 's'}
                  </div>
                  <div className="audit-window">
                    {cluster.first_seen === cluster.last_seen
                      ? cluster.first_seen
                      : `${cluster.first_seen} → ${cluster.last_seen}`}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-secondary"
                  aria-expanded={isTeaching}
                  onClick={() =>
                    setTeaching(isTeaching ? null : cluster.representative_event_id)
                  }
                >
                  {isTeaching ? 'Cancel' : 'Add to catalog'}
                </button>
              </div>

              <div className="audit-thumbs">
                {cluster.members.map((m) => (
                  <div
                    className={`audit-thumb${
                      m.event_id === cluster.representative_event_id ? ' is-representative' : ''
                    }`}
                    key={m.event_id}
                    title={`Event ${m.event_id}${m.created_at ? ` — ${m.created_at}` : ''}`}
                  >
                    <EventThumb imageUrl={m.image_url} />
                  </div>
                ))}
              </div>

              <div className="audit-cluster-meta">
                <span>
                  Sorted as <CategoryLabel category={representative.category} fallback="unknown" />
                </span>
                <span>
                  Described by the model as:{' '}
                  {names.length ? names.join(', ') : 'nothing in particular'}
                </span>
              </div>

              {isTeaching ? (
                <CatalogForm
                  key={`teach-${cluster.representative_event_id}`}
                  title="Teach TossIQ this item"
                  products={products}
                  onAdded={onProductAdded}
                  prefill={{
                    fields: {
                      name: representative.detected_object ?? '',
                      material: representative.material ?? '',
                    },
                    eventId: representative.event_id,
                    imageLabel: `The representative photo from this group (event ${representative.event_id}) will be used as the reference image`,
                  }}
                />
              ) : null}
            </div>
          );
        })}
      </div>

    </div>
  );
}
