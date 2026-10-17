import type { ResultRendererProps } from '../workspace/resultRegistry';
import { validateDataTablePayload } from './validation';

export function DataTableCard({ block, onAction, selectedEntity }: ResultRendererProps) {
  const checked = validateDataTablePayload(block.payload);
  if (!checked.isValid) return <p role="alert" className="text-sm text-ink-muted">{checked.error}</p>;
  const { columns, rows, total_count } = checked.data;
  return <article aria-label={block.title} className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 text-ink-primary dark:text-white">
    <h3 className="font-bold mb-1">{block.title}</h3>
    <p className="text-xs text-ink-muted dark:text-slate-400 mb-3">{total_count} authorized people</p>
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead><tr className="border-b border-surface-border dark:border-surface-darkBorder">
          {columns.map(column => <th key={column.key} scope="col" className="p-2 font-semibold">{column.label}</th>)}
        </tr></thead>
        <tbody>{rows.map(row => {
          const isSelected = selectedEntity?.id === row.id;
          return (
            <tr key={row.id} className={`border-b border-surface-border/60 dark:border-surface-darkBorder/60 transition-colors ${isSelected ? 'bg-blue-50/80 dark:bg-blue-950/60 font-semibold' : ''}`}>
              {columns.map(column => <td key={column.key} className="p-2 break-words max-w-56">
                {column.key === 'name' ? <button type="button" className="text-brand-700 dark:text-blue-400 underline focus-visible:outline-2" onClick={() => onAction?.('open_profile', { target_id: row.id, name: String(row.name), source_result_id: block.id })}>{row.name} {isSelected && '✓'}</button> : row[column.key]}
              </td>)}
            </tr>
          );
        })}</tbody>
      </table>
      {!rows.length && <p className="p-3 text-sm text-ink-muted">No people match this authorized view.</p>}
    </div>
  </article>;
}
