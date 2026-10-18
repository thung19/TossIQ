"use client";

export default function CodeChip({ children }: { children: React.ReactNode }) {
  return (
    <code className="code-chip">
      {children}
      <style jsx>{`
        .code-chip {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 12.5px;
          background: var(--overlay-08);
          color: var(--text-secondary);
          padding: 1.5px 6px;
          border-radius: 4px;
          border: 1px solid var(--border-05);
          white-space: nowrap;
        }
      `}</style>
    </code>
  );
}
