import { useRef, useState } from 'react';
import { postJSON } from '../api.js';

const EMPTY = { name: '', supplier: '', sku: '', material: '', cost: '' };

/**
 * Adding a catalog item is two requests: the product row first, then the
 * optional reference image as multipart form data against the new id. A failed
 * image upload still leaves the product added, which the status message says.
 */
export default function CatalogForm({ products, onAdded }) {
  const [fields, setFields] = useState(EMPTY);
  const [status, setStatus] = useState({ text: '', kind: '' });
  const fileRef = useRef(null);

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    const imageFile = fileRef.current?.files[0];
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

      if (imageFile) {
        setStatus({ text: 'Added. Uploading reference image...', kind: 'status-good' });
        try {
          const imgBody = new FormData();
          imgBody.append('file', imageFile);
          const imgRes = await fetch(`/products/${product_id}/reference-image`, {
            method: 'POST',
            body: imgBody,
          });
          if (!imgRes.ok) throw new Error(await imgRes.text());
          setStatus({ text: 'Added, with reference image.', kind: 'status-good' });
        } catch (imgErr) {
          setStatus({
            text: `Added, but reference image failed: ${imgErr.message}`,
            kind: 'status-critical',
          });
        }
      }

      setFields(EMPTY);
      if (fileRef.current) fileRef.current.value = '';
      await onAdded();
    } catch (err) {
      setStatus({ text: `Failed: ${err.message}`, kind: 'status-critical' });
    }
  }

  return (
    <div className="panel">
      <h2>Add catalog item</h2>
      <form onSubmit={handleSubmit}>
        <input id="pName" placeholder="Product name" required value={fields.name} onChange={set('name')} />
        <input id="pSupplier" placeholder="Supplier" value={fields.supplier} onChange={set('supplier')} />
        <input id="pSku" placeholder="SKU" value={fields.sku} onChange={set('sku')} />
        <input id="pMaterial" placeholder="Material" value={fields.material} onChange={set('material')} />
        <input
          id="pCost"
          placeholder="Unit cost"
          type="number"
          step="0.01"
          value={fields.cost}
          onChange={set('cost')}
        />
        <input id="pReferenceImage" ref={fileRef} type="file" accept="image/*" />
        <button type="submit">Add</button>
      </form>
      <div className={`status-msg ${status.kind}`.trim()}>{status.text}</div>
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
    </div>
  );
}
