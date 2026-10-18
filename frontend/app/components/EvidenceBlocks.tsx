"use client";

import type { Evidence } from "../../lib/api";

/**
 * Renders the observations behind one recommendation.
 *
 * Three block types, because three is what the rules produce and a fourth
 * would be a chart nobody asked for. Each block prints its own caption: the
 * evidence has to stand on its own under a card, away from the sentence that
 * cited it, or it is decoration rather than proof.
 */
export default function EvidenceBlocks({ evidence }: { evidence: Evidence[] }) {
  const metrics = evidence.filter((item) => item.type === "metric");
  const rest = evidence.filter((item) => item.type !== "metric");

  return (
    <div className="evidence">
      {metrics.length > 0 && (
        <div className="metrics">
          {metrics.map((item) => (
            <div key={item.label} className="metric">
              <span className="m-label">{item.label}</span>
              <span className="m-value">{item.value}</span>
              {item.caption && <span className="m-caption">{item.caption}</span>}
            </div>
          ))}
        </div>
      )}

      {rest.map((item) =>
        item.type === "table" ? (
          <section key={item.label} className="block">
            <header>{item.label}</header>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    {item.columns.map((column, index) => (
                      <th key={column || index} className={index === 0 ? "" : "n"}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {item.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className={cellIndex === 0 ? "first" : "n"}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {item.caption && <footer>{item.caption}</footer>}
          </section>
        ) : (
          <section key={item.label} className="block">
            <header>{item.label}</header>
            <BarRows rows={item.rows} />
            {item.caption && <footer>{item.caption}</footer>}
          </section>
        )
      )}

      <style jsx>{`
        .evidence {
          display: flex;
          flex-direction: column;
          gap: 10px;
          font-family: ui-monospace, Menlo, monospace;
        }
        .metrics {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
          gap: 6px;
        }
        .metric {
          display: flex;
          flex-direction: column;
          gap: 1px;
          padding: 7px 9px;
          background: var(--bg-card);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          min-width: 0;
        }
        .m-label {
          color: var(--text-dim);
          font-size: 9.5px;
        }
        .m-value {
          color: var(--text-primary);
          font-size: 15px;
          line-height: 20px;
          font-variant-numeric: tabular-nums;
        }
        .m-caption {
          color: var(--text-dim);
          font-size: 9px;
          line-height: 12px;
        }
        .block {
          background: var(--bg-card);
          border: 1px solid var(--border-05);
          border-radius: 3px;
          min-width: 0;
        }
        .block header {
          padding: 6px 9px;
          border-bottom: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 9.5px;
        }
        .block footer {
          padding: 6px 9px 7px;
          border-top: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 9px;
          line-height: 12px;
        }
        /* Evidence tables carry procurement detail and go wide. They scroll
           inside their own box rather than pushing the card sideways. */
        .scroll {
          overflow-x: auto;
          max-height: 300px;
          overflow-y: auto;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 10.5px;
          white-space: nowrap;
        }
        th {
          position: sticky;
          top: 0;
          background: var(--bg-card);
          text-align: right;
          font-weight: 400;
          color: var(--text-dim);
          font-size: 9px;
          padding: 4px 9px;
        }
        th:first-child {
          text-align: left;
        }
        td {
          padding: 3px 9px;
          color: var(--text-secondary);
          border-top: 1px solid var(--border-05);
        }
        td.first {
          color: var(--text-primary);
          white-space: normal;
          max-width: 230px;
        }
        .n {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
      `}</style>
    </div>
  );
}

function BarRows({ rows }: { rows: { bucket: string; value: number; note: string | null }[] }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="bars">
      {rows.map((row, index) => (
        <div key={`${row.bucket}-${index}`} className={`row ${row.note ? "noted" : ""}`}>
          <span className="bucket">{row.bucket}</span>
          <span className="track">
            <span className="bar" style={{ width: `${(row.value / max) * 100}%` }} />
          </span>
          <span className="value">{row.value.toLocaleString()}</span>
          <span className="note">{row.note ?? ""}</span>
        </div>
      ))}
      <style jsx>{`
        .bars {
          display: flex;
          flex-direction: column;
          padding: 5px 9px 7px;
          gap: 1px;
        }
        .row {
          display: grid;
          grid-template-columns: 42px minmax(0, 1fr) 44px 52px;
          align-items: center;
          gap: 7px;
          font-size: 10px;
        }
        .bucket {
          color: var(--text-dim);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .track {
          min-width: 0;
          height: 9px;
          background: var(--overlay-02);
          border-radius: 2px;
          overflow: hidden;
        }
        .bar {
          display: block;
          height: 100%;
          background: var(--primary);
          border-radius: 2px;
        }
        .row.noted .bar {
          background: var(--status-in-progress);
        }
        .value {
          text-align: right;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }
        .note {
          color: var(--status-in-progress);
          font-size: 9px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      `}</style>
    </div>
  );
}
