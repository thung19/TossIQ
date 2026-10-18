export default function ItemsTable({ items }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Item</th>
          <th>Catalog match</th>
          <th className="num">Count</th>
          <th>Last seen</th>
          <th className="num">Est. value</th>
        </tr>
      </thead>
      <tbody>
        {items.length === 0 ? (
          <tr>
            <td className="empty" colSpan={5}>
              No events yet
            </td>
          </tr>
        ) : (
          items.map((i, idx) => (
            <tr key={`${i.detected_object}-${idx}`}>
              <td>{i.detected_object}</td>
              <td>{i.matched_product || '—'}</td>
              <td className="num">{i.count}</td>
              <td>{i.last_seen}</td>
              <td className="num">
                {i.estimated_value !== null ? `$${i.estimated_value.toFixed(2)}` : '—'}
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
