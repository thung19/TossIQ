import { useId, useRef, useState } from 'react';
import { postJSON } from '../api.js';

const EMPTY = { name: '', supplier: '', sku: '', material: '', cost: '' };

/**
 * Adding a catalog item is two requests: the product row first, then the
 * optional reference image as multipart form data against the new id. A failed
 * image upload still leaves the product added, which the status message says.
 *
 * `prefill` lets another view open this same form already filled in --
 * `{ fields, imageUrl, imageLabel }`. When it carries an `imageUrl` and the
 * operator picks no file of their own, that stored photo is fetched back as a
 * blob and sent through this same reference-image upload, so there is one
 * upload path rather than two. `prefill` is read once, when the form mounts;
 * render a new instance (a different React `key`) to fill it in differently.
 *
 * `products` is optional: omit it to render just the form, without the catalog
 * table underneath.
 */
export default function CatalogForm({ products, onAdded, title = 'Add catalog item', prefill }) {
  // Two instances of this form can be mounted at once (the dashboard's and one
  // opened from a waste-audit cluster), so the field ids have to be unique.
  const idPrefix = useId();
  const [initialFields] = useState(() => ({ ...EMPTY, ...(prefill?.fields ?? {}) }));
  const [fields, setFields] = useState(initialFields);
  const [status, setStatus] = useState({ text: '', kind: '' });
  const fileRef = useRef(null);

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

  /** The operator's own pick wins; otherwise the prefilled stored photo, if any. */
  async function referenceImageFile() {
    const picked = fileRef.current?.files[0];
    if (picked) return picked;
    if (!prefill?.imageUrl) return null;
    const res = await fetch(prefill.imageUrl);
    if (!res.ok) throw new Error(`could not read the stored photo (${res.status})`);
    const blob = await res.blob();
    return new File([blob], 'reference.jpg', { type: blob.type || 'image/jpeg' });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setStatus({ text: 'Adding...', kind: '' });
    try {
      const { product_id } = await postJSON('/products', {
        product_name: fields.name,
        supplier: fields.supplier || null,
        sku: fields.sku || null,
        material: fields.material || null,
        unit_cost: fields.cost ? parseFloat(fields.cost) : null,
      });
      setStatus({ text: 'Added.', kind: 'status-good' });

      try {
        const imageFile = await referenceImageFile();
        if (imageFile) {
          setStatus({ text: 'Added. Uploading reference image...', kind: 'status-good' });
          const imgBody = new FormData();
          imgBody.append('file', imageFile);
          const imgRes = await fetch(`/products/${product_id}/reference-image`, {
            method: 'POST',
            body: imgBody,
          });
          if (!imgRes.ok) throw new Error(await imgRes.text());
          setStatus({
            text: 'Added, with reference image. Future disposals of this item will match it; past events keep the record they were given.',
            kind: 'status-good',
          });
        }
      } catch (imgErr) {
        setStatus({
          text: `Added, but reference image failed: ${imgErr.message}`,
          kind: 'status-critical',
        });
      }

      setFields(initialFields);
      if (fileRef.current) fileRef.current.value = '';
      await onAdded();
    } catch (err) {
      setStatus({ text: `Failed: ${err.message}`, kind: 'status-critical' });
    }
  }

  return (
    <div className="panel">
      <h2>{title}</h2>
      <form onSubmit={handleSubmit}>
        <input id={`${idPrefix}Name`} placeholder="Product name" required value={fields.name} onChange={set('name')} />
        <input id={`${idPrefix}Supplier`} placeholder="Supplier" value={fields.supplier} onChange={set('supplier')} />
        <input id={`${idPrefix}Sku`} placeholder="SKU" value={fields.sku} onChange={set('sku')} />
        <input id={`${idPrefix}Material`} placeholder="Material" value={fields.material} onChange={set('material')} />
        <input
          id={`${idPrefix}Cost`}
          placeholder="Unit cost"
          type="number"
          step="0.01"
          value={fields.cost}
          onChange={set('cost')}
        />
        <input id={`${idPrefix}ReferenceImage`} ref={fileRef} type="file" accept="image/*" />
        <button type="submit">Add</button>
      </form>
      {prefill?.imageUrl ? (
        <div className="status-msg">
          {prefill.imageLabel ?? 'A stored photo will be used as the reference image'} unless you
          choose a file above.
        </div>
      ) : null}
      <div className={`status-msg ${status.kind}`.trim()}>{status.text}</div>
      {products ? (
        <table>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td className="empty" colSpan={3}>
                  No catalog items yet
                </td>
              </tr>
            ) : (
              products.map((p) => (
                <tr key={p.product_id}>
                  <td>{p.product_name}</td>
                  <td>{p.supplier}</td>
                  <td className="num">
                    {p.unit_cost !== null ? `$${Number(p.unit_cost).toFixed(2)}` : ''}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
