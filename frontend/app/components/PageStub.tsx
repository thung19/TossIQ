"use client";

import PageHeader from "./PageHeader";

export default function PageStub({
  breadcrumb,
  title,
  summary,
  sections,
}: {
  breadcrumb: string;
  title: string;
  summary: string;
  sections: { title: string; body: string }[];
}) {
  return (
    <>
      <PageHeader breadcrumb={breadcrumb} title={title} />
      <div className="page">
        <section className="panel">
          <div className="row">
            <span className="k">Status</span>
            <span className="v">Not implemented</span>
          </div>
          <div className="row">
            <span className="k">Summary</span>
            <span className="v muted">{summary}</span>
          </div>
        </section>

        <section className="list">
          {sections.map((s) => (
            <article key={s.title} className="item">
              <span className="t">{s.title}</span>
              <span className="d">{s.body}</span>
            </article>
          ))}
        </section>
      </div>

      <style jsx>{`
        .page {
          padding: 20px 24px 32px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          max-width: 920px;
        }
        .panel {
          background: var(--bg-surface);
          border: 1px solid var(--border-08);
          border-radius: 8px;
          padding: 14px 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .row {
          display: grid;
          grid-template-columns: 90px 1fr;
          gap: 12px;
          font-size: 13px;
          align-items: baseline;
        }
        .k {
          color: var(--text-dim);
          font-size: 11.5px;
        }
        .v {
          color: var(--text-secondary);
        }
        .v.muted {
          color: var(--text-muted);
          line-height: 20px;
        }
        .list {
          display: flex;
          flex-direction: column;
          border: 1px solid var(--border-08);
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-surface);
        }
        .item {
          padding: 12px 16px;
          display: flex;
          flex-direction: column;
          gap: 2px;
          border-bottom: 1px solid var(--border-05);
        }
        .item:last-child {
          border-bottom: none;
        }
        .t {
          font-size: 13px;
          font-weight: 510;
          color: var(--text-primary);
        }
        .d {
          font-size: 12.5px;
          color: var(--text-dim);
          line-height: 18px;
        }
      `}</style>
    </>
  );
}
