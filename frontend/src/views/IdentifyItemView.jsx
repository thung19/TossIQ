import { useEffect, useRef, useState } from 'react';
import { postForm } from '../api.js';
import CategoryLabel from '../components/CategoryLabel.jsx';

const FOOD_CONTAMINATED_LABEL = { true: 'Yes', false: 'No' };

/** One labelled result field. Rendered only by the caller when it has a value. */
function ResultRow({ label, children }) {
  return (
    <div className="result-row">
      <div className="result-label">{label}</div>
      <div className="result-value">{children}</div>
    </div>
  );
}

/**
 * On-demand identification of a single item through POST /classify -- the same
 * advanced-analysis path the edge device's background enrichment uses.
 *
 * Two properties of that endpoint shape this page. It runs the full cloud
 * vision analysis, so a request takes seconds and the submit control stays
 * disabled while one is in flight. And it persists its result as a waste
 * event, so every identification here lands in the dashboard's counts; the
 * result says so rather than hiding it.
 */
export default function IdentifyItemView({ hidden }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [locationText, setLocationText] = useState('');
  const [dragging, setDragging] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState({ text: '', kind: '' });
  const fileRef = useRef(null);
  // Drag events from the drop zone's own children fire dragleave on the zone,
  // so the highlight tracks a depth count rather than a single boolean event.
  const dragDepth = useRef(0);

  useEffect(() => {
    if (!file) {
      setPreviewUrl('');
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function clearFileInput() {
    if (fileRef.current) fileRef.current.value = '';
  }

  function reject(text) {
    clearFileInput();
    setStatus({ text, kind: 'status-critical' });
  }

  // A rejected candidate leaves any previous valid selection in place; only
  // the message changes.
  function selectFile(candidate) {
    if (!candidate) return;
    if (!candidate.type.startsWith('image/')) {
      reject(`"${candidate.name}" is not an image file. Choose a JPEG, PNG, or WebP image.`);
      return;
    }
    setFile(candidate);
    setResult(null);
    setStatus({ text: '', kind: '' });
  }

  function handleDragEnter(e) {
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (!dropped) {
      setStatus({
        text: 'That drop carried no file. Drag an image file, or use the picker.',
        kind: 'status-critical',
      });
      return;
    }
    selectFile(dropped);
  }

  function clearSelection() {
    setFile(null);
    clearFileInput();
    setResult(null);
    setStatus({ text: '', kind: '' });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file || pending) return;
    setPending(true);
    setResult(null);
    setStatus({ text: 'Identifying — the full cloud analysis takes a few seconds...', kind: '' });
    try {
      const body = new FormData();
      body.append('file', file);
      const location = locationText.trim();
      if (location) body.append('location', location);
      setResult(await postForm('/classify', body));
      setStatus({ text: '', kind: '' });
    } catch (err) {
      setStatus({ text: `Failed: ${err.message}`, kind: 'status-critical' });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="view" hidden={hidden}>
      <div className="topbar">
        <div>
          <h1>Identify Item</h1>
          <div className="subtitle">
            Upload one item&rsquo;s photo for advanced analysis. Each identification is logged as a
            waste event, so it counts in the dashboard.
          </div>
        </div>
      </div>

      <div className="grid grid-split">
        <div className="panel">
          <h2>Upload image</h2>
          <form onSubmit={handleSubmit}>
            {/* The drop zone is a label around the native file input, so a
                click anywhere in it opens the picker and the input itself
                stays keyboard-reachable. */}
            <label
              className={`dropzone${dragging ? ' dragover' : ''}`}
              onDragEnter={handleDragEnter}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <span className="dropzone-hint">
                {dragging ? 'Drop the image to use it' : 'Drag an image here, or choose a file'}
              </span>
              <input
                id="identifyFile"
                ref={fileRef}
                type="file"
                accept="image/*"
                aria-label="Image to identify"
                onChange={(e) => selectFile(e.target.files?.[0])}
              />
              <span className="dropzone-note">JPEG, PNG, or WebP, up to 10&nbsp;MB</span>
            </label>

            <input
              id="identifyLocation"
              className="identify-location"
              placeholder="Location (optional)"
              value={locationText}
              onChange={(e) => setLocationText(e.target.value)}
            />

            <button type="submit" disabled={!file || pending}>
              {pending ? 'Identifying...' : 'Identify item'}
            </button>
            {file ? (
              <button type="button" className="btn-secondary" onClick={clearSelection}>
                Clear
              </button>
            ) : null}
          </form>

          {/* `previewUrl` is set from an effect, so it still holds the old
              object URL for the one render after the file is cleared or
              replaced. Both must be present before the preview reads either. */}
          {file && previewUrl ? (
            <div className="identify-preview">
              <img src={previewUrl} alt={`Selected image: ${file.name}`} />
              <div className="identify-preview-name">{file.name}</div>
            </div>
          ) : null}

          <div className={`status-msg ${status.kind}`.trim()}>{status.text}</div>
        </div>

        <div className="panel">
          <h2>Identification</h2>
          {result ? (
            <>
              {result.parse_error ? (
                <div className="status-msg status-critical">
                  Partial identification &mdash; the model&rsquo;s response did not fully parse:{' '}
                  {result.parse_error}. Treat any field below as incomplete.
                </div>
              ) : null}

              <ResultRow label="Object">{result.object || '—'}</ResultRow>
              <ResultRow label="Material">{result.material || '—'}</ResultRow>
              <ResultRow label="Material subtype">{result.material_subtype || '—'}</ResultRow>
              <ResultRow label="Category">
                <CategoryLabel category={result.category} fallback="—" />
              </ResultRow>
              <ResultRow label="Food contaminated">
                {FOOD_CONTAMINATED_LABEL[result.food_contaminated] ?? 'Not reported'}
              </ResultRow>
              <ResultRow label="Reason">{result.reason || '—'}</ResultRow>
              <ResultRow label="Matched rule">{result.matched_rule || '—'}</ResultRow>
              {result.matched_product ? (
                <ResultRow label="Matched catalog product">{result.matched_product}</ResultRow>
              ) : null}

              <div className="status-msg status-good">
                {`Logged as waste event #${result.event_id}; it now counts in the dashboard's totals and recent events.`}
              </div>
            </>
          ) : (
            <div className="empty">
              {pending
                ? 'Running advanced analysis...'
                : 'No identification yet. Upload an image and identify it.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
