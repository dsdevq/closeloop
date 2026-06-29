import type { ReactNode } from 'react';

export function ModalShell({ children, onClose, title }: { children: ReactNode; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 p-4" onMouseDown={onClose}>
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <h2 className="mb-4 text-base font-bold text-slate-950">{title}</h2>
        {children}
      </div>
    </div>
  );
}
