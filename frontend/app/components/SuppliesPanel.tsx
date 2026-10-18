"use client";

import BarList from "./BarList";
import { MEASURE_LABEL, formatMeasure, type CatalogRollup, type Measure } from "../../lib/api";

/**
 * The supplies view: what is being thrown away, by SKU.
 *
 * This is the table the purchasing conversation happens over, which is why
 * it carries the case pack and the case-equivalent count rather than only
 * unit counts. "4.2 cases of 12 oz hot cups went in the bin this month" is a
 * sentence someone can act on; "1,260 cups" is not, because nobody orders
 * cups singly.
 *
 * Unit cost and reference mass are shown next to the totals they produced, so
 * a surprising total can be traced to the catalog number behind it rather
 * than taken on faith.
 */
export default function SuppliesPanel({
  catalog,
  measure,
}: {
  catalog: CatalogRollup | null;
  measure: Measure;
}) {
  if (!catalog) {
    return (
      <section className="panel">
        <div className="empty">loading supplies…</div>
        <style jsx>{`
          .panel {
            background: var(--bg-surface);
            border: 1px solid var(--border-08);
            border-radius: 3px;
          }
          .empty {
            padding: 16px 10px;
            color: var(--text-dim);
            font-family: ui-monospace, Menlo, monospace;
            font-size: 11px;
          }
        `}</style>
      </section>
    );
  }

  const matched = catalog.skus.filter((row) => row.sku !== "unmatched");
  const unmatched = catalog.skus.find((row) => row.sku === "unmatched");

  return (
    <div className="wrap">
    <section className="panel">
      <header>
        <span className="title">discarded supplies by SKU</span>
        <span className="spacer" />
        <span className="meta">
          {matched.length} SKU{matched.length === 1 ? "" : "s"} seen of{" "}
          {catalog.catalog_size} in catalog
          {unmatched ? ` · ${unmatched.count.toLocaleString()} items unmatched` : ""}
        </span>
      </header>

      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>SKU</th>
              <th>product</th>
              <th>supplier</th>
              <th>material</th>
              <th>stream</th>
              <th className="n">items</th>
              <th className="n">cases</th>
              <th className="n">unit</th>
              <th className="n">est. cost</th>
              <th className="n">est. mass</th>
            </tr>
          </thead>
          <tbody>
            {matched.map((row) => (
              <tr key={row.sku}>
                <td className="sku">{row.sku}</td>
                <td className="name">
                  {row.product_name ?? "—"}
                  {row.variant_label && <span className="variant">{row.variant_label}</span>}
                </td>
                <td className="dim">{row.supplier ?? "—"}</td>
                <td className="dim">
                  {row.material ?? "—"}
                  {row.material_subtype && (
                    <span className="variant">{row.material_subtype}</span>
                  )}
                </td>
                <td>
                  {row.intended_stream ? (
                    <span className={`pill ${row.intended_stream}`}>{row.intended_stream}</span>
                  ) : (
                    <span className="dim">—</span>
                  )}
                </td>
                <td className="n strong">{row.count.toLocaleString()}</td>
                <td className="n">
                  {row.cases_equivalent != null ? (
                    <span title={`case pack of ${row.case_pack_qty}`}>
                      {row.cases_equivalent.toFixed(2)}
                    </span>
                  ) : (
                    <span className="dim">—</span>
                  )}
                </td>
                <td className="n dim">
                  {row.unit_cost != null ? `$${row.unit_cost.toFixed(3)}` : "—"}
                  {row.unit_weight_grams != null && (
                    <span className="variant">{row.unit_weight_grams} g</span>
                  )}
                </td>
                <td className="n strong">{formatMeasure(row.estimated_cost, "cost")}</td>
                <td className="n">{formatMeasure(row.estimated_kg, "mass")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {unmatched && (
        <div className="unmatched">
          {unmatched.count.toLocaleString()} item{unmatched.count === 1 ? "" : "s"} matched no
          catalog entry and contribute to no cost or mass total above. Adding them to the
          catalog is what would bring them in.
        </div>
      )}

      <footer>
        Unit cost is the loss from discarding, which is $0 for consumed residue such as peels
        and spent grounds. Mass is the catalog&rsquo;s reference weight per unit, multiplied by
        the count &mdash; no can has a weight sensor, so nothing here is weighed.
        {measure !== "count" && " Totals follow the measure selected above."}
      </footer>
    </section>

      <section className="panel">
        <header>
          <span className="title">by supplier</span>
          <span className="spacer" />
          <span className="meta">
            {catalog.by_supplier.length} supplier
            {catalog.by_supplier.length === 1 ? "" : "s"}
          </span>
        </header>
        {/* Rolling the same figures up by supplier is what turns this page
            into a procurement conversation: it names who to talk to, where
            the SKU table only names what to talk about. */}
        <BarList
          rows={catalog.by_supplier}
          measure={measure}
          emptyLabel="nothing matched to a supplier in this scope"
        />
        <footer>
          Measured in {MEASURE_LABEL[measure]}. Items with no catalog match have no supplier
          and are grouped as unknown.
        </footer>
      </section>

      <style jsx>{`
        .wrap {
          display: grid;
          grid-template-columns: minmax(0, 2.2fr) minmax(0, 1fr);
          gap: 10px;
          align-items: start;
        }
        @media (max-width: 1240px) {
          .wrap {
            grid-template-columns: 1fr;
          }
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
        /* The table is wide by nature -- ten columns of procurement detail --
           so it scrolls inside its own box rather than pushing the page
           sideways. */
        .scroll {
          overflow-x: auto;
          max-height: 540px;
          overflow-y: auto;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 10.5px;
          white-space: nowrap;
        }
        thead th {
          position: sticky;
          top: 0;
          background: var(--bg-card);
          text-align: left;
          font-weight: 400;
          color: var(--text-dim);
          font-size: 9.5px;
          padding: 4px 9px;
          border-bottom: 1px solid var(--border-08);
          z-index: 1;
        }
        td {
          padding: 3px 9px;
          color: var(--text-secondary);
          border-top: 1px solid var(--border-05);
          vertical-align: top;
        }
        tr:hover td {
          background: var(--overlay-02);
        }
        .sku {
          color: var(--mention-text);
        }
        .name {
          color: var(--text-primary);
          max-width: 230px;
          white-space: normal;
        }
        .variant {
          display: block;
          color: var(--text-dim);
          font-size: 9px;
          line-height: 12px;
        }
        .dim {
          color: var(--text-muted);
        }
        .n {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .strong {
          color: var(--text-primary);
        }
        .pill {
          display: inline-block;
          padding: 0 5px;
          border-radius: 2px;
          font-size: 9px;
          line-height: 14px;
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
        .unmatched {
          padding: 7px 10px;
          border-top: 1px solid var(--border-05);
          color: var(--status-in-progress);
          font-size: 10px;
          line-height: 14px;
        }
        footer {
          padding: 7px 10px 9px;
          border-top: 1px solid var(--border-05);
          color: var(--text-dim);
          font-size: 9.5px;
          line-height: 13px;
        }
      `}</style>
    </div>
  );
}
