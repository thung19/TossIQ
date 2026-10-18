import CategoryLabel from './CategoryLabel.jsx';

export default function LocationsTable({ locations }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Location</th>
          <th>Category</th>
          <th className="num">Count</th>
        </tr>
      </thead>
      <tbody>
        {locations.length === 0 ? (
          <tr>
            <td className="empty" colSpan={3}>
              No events yet
            </td>
          </tr>
        ) : (
          locations.map((r, idx) => (
            <tr key={`${r.location}-${r.category}-${idx}`}>
              <td>{r.location}</td>
              <td>
                <CategoryLabel category={r.category} />
              </td>
              <td className="num">{r.count}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
