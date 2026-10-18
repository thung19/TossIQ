"use client";

import type { AccuracyReport, MisroutedReport } from "../../lib/api";

/**
 * Classification quality, from the two sources that can actually speak to it.
 *
 * Human review is ground truth, and there is only ever a sample of it, so
 * every rate here is shown with the sample it came from. Misrouting needs no
 * reviewer at all: it compares the stream an item was logged into against the
 * stream its catalog entry declares, and both are recorded facts.
 *
 * Model confidence appears only as the axis of the calibration table, which
 * asks whether confidence predicts agreement. It is deliberately never
 * presented as accuracy -- that would be the classifier grading itself.
 */
export default function QualityPanel({
  accuracy,
  misrouted,
}: {
  accuracy: AccuracyReport | null;
  misrouted: MisroutedReport | null;
}) {
  return (
    <div className="wrap">
      <section className="panel">
        <header>
          <span className="title">review agreement</span>
          <span className="spacer" />
          {accuracy && (
            <span className="meta">
              {accuracy.reviewed_events.toLocaleString()} of{" "}
              {accuracy.total_events.toLocaleString()} reviewed ·{" "}
              {accuracy.review_coverage}% coverage
            </span>
          )}
        </header>

        {!accuracy ? (
          <div className="empty">loading…</div>
        ) : accuracy.reviewed_events === 0 ? (
          <div className="empty">
            nothing in this scope has been reviewed, so there is no accuracy to report
          </div>
        ) : (
          <>
            <div className="headline">
              <span className="big">{accuracy.accuracy}%</span>
              <span className="cap">
                agreement with a human reviewer, over {accuracy.reviewed_events} reviewed
                item{accuracy.reviewed_events === 1 ? "" : "s"}
              </span>
            </div>

            <div className="sub">by bin</div>
            <table>
              <thead>
                <tr>
                  <th>bin</th>
                  <th className="n">reviewed</th>
                  <th className="n">agreed</th>
                  <th className="n">rate</th>
                </tr>
              </thead>
              <tbody>
                {accuracy.by_category.map((row) => (
                  <tr key={row.category}>
                    <td>{row.category}</td>
                    <td className="n">{row.reviewed}</td>
                    <td className="n">{row.correct}</td>
                    <td className="n">
                      {row.accuracy}%
                      {/* A rate over a handful of reviews is noise, and
                          saying so beside it is cheaper than a reader
                          discovering it later. */}
                      {row.reviewed < 10 && <span className="warn"> small sample</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="sub">
              confidence calibration
              <span className="hint">
                does the model&rsquo;s own confidence predict whether a human agreed?
              </span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>confidence</th>
                  <th className="n">reviewed</th>
                  <th className="n">agreement</th>
                  <th>&nbsp;</th>
                </tr>
              </thead>
              <tbody>
                {accuracy.calibration.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td className="n">{row.reviewed}</td>
                    <td className="n">{row.accuracy == null ? "-" : `${row.accuracy}%`}</td>
                    <td className="track">
                      {row.accuracy != null && (
                        <span className="bar" style={{ width: `${row.accuracy}%` }} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {accuracy.confusions.length > 0 && (
              <>
                <div className="sub">what it gets wrong</div>
                <ul className="confusions">
                  {accuracy.confusions.map((row) => (
                    <li key={`${row.seen_as}->${row.actually_was}`}>
                      <span className="seen">{row.seen_as}</span>
                      <span className="arrow">read as</span>
                      <span className="actual">{row.actually_was}</span>
                      <span className="count">{row.count}x</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <footer>{accuracy.note}</footer>
          </>
        )}
      </section>

      <section className="panel">
        <header>
          <span className="title">wrong-bin sorting</span>
          <span className="spacer" />
          {misrouted && (
            <span className="meta">
              {misrouted.misrouted_count.toLocaleString()} of{" "}
              {misrouted.total_items.toLocaleString()} · {misrouted.misrouted_rate}%
            </span>
          )}
        </header>

        {!misrouted ? (
          <div className="empty">loading…</div>
        ) : misrouted.rows.length === 0 ? (
          <div className="empty">
            nothing in this scope went into a bin its catalog entry disagrees with
          </div>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>item</th>
                  <th>went into</th>
                  <th>belongs in</th>
                  <th className="n">items</th>
                  <th className="n">est. mass</th>
                </tr>
              </thead>
              <tbody>
                {misrouted.rows.map((row) => (
                  <tr key={`${row.item}-${row.logged_as}-${row.should_be}`}>
                    <td className="item">{row.item}</td>
                    <td>
                      <span className={`pill ${row.logged_as}`}>{row.logged_as}</span>
                    </td>
                    <td>
                      <span className={`pill ${row.should_be}`}>{row.should_be}</span>
                    </td>
                    <td className="n">{row.count}</td>
                    <td className="n">
                      {row.estimated_kg >= 1
                        ? `${row.estimated_kg.toFixed(1)} kg`
                        : `${Math.round(row.grams)} g`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <footer>{misrouted.note}</footer>
          </>
        )}
      </section>

      <style jsx>{`
        .wrap {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 10px;
          align-items: start;
        }
        .panel {
          display: flex;
          flex-direction: column;
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 3px;
          min-width: 0;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11px;
        }
        header {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 7px 10px;
          border-bottom: 1px solid var(--border-05);
        }
        .title {
          color: var(--text-primary);
          font-weight: 510;
        }
        .spacer {
          flex: 1;
        }
        .meta {
          color: var(--text-dim);
          font-size: 10px;
        }
        .empty {
          padding: 16px 10px;
          color: var(--text-dim);
          font-size: 10.5px;
          line-height: 15px;
        }
        .headline {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 12px 10px 8px;
        }
        .big {
          font-size: 26px;
          line-height: 28px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }
        .cap {
          color: var(--text-dim);
          font-size: 10px;
          line-height: 14px;
        }
        .sub {
          display: flex;
          align-items: baseline;
          gap: 6px;
          padding: 10px 10px 4px;
          color: var(--text-dim);
          font-size: 10px;
          border-top: 1px solid var(--border-05);
        }
        .hint {
          color: var(--text-dim);
          opacity: 0.75;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 10.5px;
        }
        th {
          text-align: left;
          font-weight: 400;
          color: var(--text-dim);
          font-size: 9.5px;
          padding: 2px 10px;
        }
        td {
          padding: 3px 10px;
          color: var(--text-secondary);
          border-top: 1px solid var(--border-05);
        }
        td.item {
          color: var(--text-primary);
          max-width: 160px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .n {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .warn {
          color: var(--status-in-progress);
          font-size: 9px;
        }
        .track {
          width: 90px;
        }
        .bar {
          display: block;
          height: 7px;
          background: var(--primary);
          border-radius: 2px;
        }
        .pill {
          display: inline-block;
          padding: 0 5px;
          border-radius: 2px;
          font-size: 9.5px;
          line-height: 15px;
          border: 1px solid var(--border-08);
          color: var(--text-muted);
        }
        .pill.recycling {
          color: var(--cat-recycling);
          border-color: var(--cat-recycling);
        }
        .pill.compost {
          color: var(--cat-compost);
          border-color: var(--cat-compost);
        }
        .pill.landfill {
          color: var(--cat-landfill);
          border-color: var(--cat-landfill);
        }
        .confusions {
          list-style: none;
          padding: 2px 10px 6px;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .confusions li {
          display: flex;
          align-items: baseline;
          gap: 6px;
          font-size: 10.5px;
        }
        .seen {
          color: var(--status-bug);
        }
        .arrow {
          color: var(--text-dim);
          font-size: 9.5px;
        }
        .actual {
          color: var(--status-done);
        }
        .count {
          margin-left: auto;
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        footer {
          padding: 7px 10px 9px;
          margin-top: auto;
          border-top: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 9.5px;
          line-height: 13px;
        }
        @media (max-width: 1240px) {
          .wrap {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
