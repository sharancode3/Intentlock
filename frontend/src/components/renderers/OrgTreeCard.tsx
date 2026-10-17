import { useMemo } from 'react';
import { ReactFlow, Background, Controls, type Edge, type Node } from '@xyflow/react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import { validateOrgTreePayload } from './validation';

export function OrgTreeCard({ block, onAction, selectedEntity }: ResultRendererProps) {
  const checked = validateOrgTreePayload(block.payload);
  const payload = checked.isValid ? checked.data : null;
  const graph = useMemo(() => {
    if (!payload) return { nodes: [] as Node[], edges: [] as Edge[] };
    const children = new Map<string, string[]>();
    payload.edges.forEach(edge => children.set(edge.source, [...(children.get(edge.source) || []), edge.target]));
    const positions = new Map<string, { x: number; y: number }>();
    const queue = [{ id: payload.root_id, depth: 0 }];
    let row = 0;
    while (queue.length) {
      const item = queue.shift()!;
      if (positions.has(item.id)) continue;
      positions.set(item.id, { x: item.depth * 220, y: row++ * 95 });
      (children.get(item.id) || []).forEach(id => queue.push({ id, depth: item.depth + 1 }));
    }
    const nodes: Node[] = payload.nodes.map(person => {
      const isSelected = selectedEntity?.type === 'employee' && selectedEntity.id === person.id;
      return {
        id: person.id, position: positions.get(person.id) || { x: 0, y: row++ * 95 },
        data: { label: <button type="button" className={`text-left text-xs focus-visible:outline-2 p-1 rounded transition-colors ${isSelected ? 'ring-2 ring-brand-700 bg-brand-50 dark:bg-blue-950/70 font-semibold' : ''}`} onClick={() => onAction?.('open_profile', { target_id: person.id, name: person.name, source_result_id: block.id })}>
          <strong className="block break-words">{person.name} {isSelected && '✓'}</strong><span className="block break-words">{person.title}</span>
          <span className="block text-slate-500">{person.direct_count} direct</span>
        </button> }, draggable: false, selectable: false,
      };
    });
    const edges: Edge[] = payload.edges.map((edge, index) => ({ id: `report-${index}`, source: edge.source, target: edge.target }));
    return { nodes, edges };
  }, [payload, block.id, onAction, selectedEntity]);
  if (!checked.isValid) return <p role="alert" className="text-sm text-ink-muted">{checked.error}</p>;
  if (!payload) return null;
  return <article aria-label={block.title} className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 text-ink-primary dark:text-white">
    <h3 className="font-bold">{block.title}</h3>
    <p className="text-xs text-ink-muted dark:text-slate-400 mb-3">{payload.direct_count} direct reports · {payload.descendant_count} descendants shown</p>
    <div className="hidden sm:block h-[360px] max-w-full border border-surface-border dark:border-surface-darkBorder rounded-flat" aria-label="Reporting graph">
      <ReactFlow nodes={graph.nodes} edges={graph.edges} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} fitView attributionPosition="bottom-left">
        <Background /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
    <ol className="sm:hidden space-y-2" aria-label="Reporting list">
      {payload.nodes.map(person => {
        const isSelected = selectedEntity?.type === 'employee' && selectedEntity.id === person.id;
        return (
          <li key={person.id} className={`border rounded-flat p-2 text-sm transition-colors ${isSelected ? 'border-brand-700 bg-brand-50/70 dark:bg-blue-950/40' : 'border-surface-border dark:border-surface-darkBorder'}`}>
            <button type="button" className="text-brand-700 dark:text-blue-400 underline text-left font-semibold" onClick={() => onAction?.('open_profile', { target_id: person.id, name: person.name, source_result_id: block.id })}>
              {person.name} {isSelected && '✓'}
            </button>
            <span className="block text-xs">{person.title} · {person.direct_count} direct</span>
          </li>
        );
      })}
    </ol>
  </article>;
}
