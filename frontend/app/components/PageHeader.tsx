"use client";

export default function PageHeader({
  title,
  breadcrumb,
  right,
}: {
  title: string;
  breadcrumb?: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="left">
        {breadcrumb && <span className="crumb">{breadcrumb}</span>}
        {breadcrumb && <span className="sep">/</span>}
        <span className="title">{title}</span>
      </div>
      {right && <div className="right">{right}</div>}
      <style jsx>{`
        .page-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 7px 16px;
          border-bottom: 1px solid var(--border-05);
          background: var(--bg);
          min-height: 34px;
          flex-shrink: 0;
          font-family: ui-monospace, Menlo, monospace;
          font-size: 11.5px;
        }
        .left {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .crumb {
          color: var(--text-dim);
        }
        .sep {
          color: var(--text-dim);
        }
        .title {
          color: var(--text-primary);
          font-weight: 510;
        }
        .right {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      `}</style>
    </header>
  );
}
