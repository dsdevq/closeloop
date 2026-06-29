import { Search } from 'lucide-react';
import type { SavedView } from '../../types';

export function SavedViewsBar({
  views,
  activeName,
  onApply,
  onClear,
}: {
  views: SavedView[];
  activeName?: string;
  onApply: (id: number, name: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="panel mb-4 flex flex-wrap items-center gap-2 px-3 py-2">
      <div className="flex items-center gap-2 pr-2 text-xs font-bold uppercase text-slate-500">
        <Search size={14} aria-hidden="true" />
        Saved Views
      </div>
      {views.length === 0 && <span className="text-sm text-slate-400">No saved views</span>}
      {views.map((view) => (
        <button key={view.id} className="secondary-button h-8 px-2.5 text-xs" onClick={() => onApply(view.id, view.name)} type="button">
          {view.name}
        </button>
      ))}
      {activeName && (
        <>
          <span className="ml-auto text-sm text-blue-700">Showing: {activeName}</span>
          <button className="secondary-button h-8 px-2.5 text-xs" onClick={onClear} type="button">
            Clear
          </button>
        </>
      )}
    </div>
  );
}
