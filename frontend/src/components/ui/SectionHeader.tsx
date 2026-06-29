import type { ReactNode } from 'react';

export function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h1 className="text-base font-bold text-slate-950">{title}</h1>
      {action}
    </div>
  );
}
