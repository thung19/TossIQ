// Every call stays a same-origin relative path so the same code works behind
// the Vite dev proxy and behind the FastAPI static mount in production.

// FastAPI reports its own errors as `{"detail": "..."}`, so unwrap that before
// the message reaches a status line. Anything else (a proxy error page, an
// empty body) falls back to the raw text and then to the status code, so a
// failed request always has something to say.
async function errorMessage(res) {
  const text = await res.text();
  try {
    const { detail } = JSON.parse(text);
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
  } catch {
    // Not JSON -- fall through to the raw body.
  }
  return text || `${res.status} ${res.statusText}`;
}

export async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

export async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

/**
 * POST multipart form data. The browser sets the multipart boundary itself, so
 * this deliberately sends no Content-Type header of its own.
 */
export async function postForm(url, formData) {
  const res = await fetch(url, { method: 'POST', body: formData });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}
