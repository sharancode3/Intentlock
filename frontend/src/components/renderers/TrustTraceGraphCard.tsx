import React, { useState, useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ShieldCheck,
  AlertCircle,
  Hash,
  ListTree,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import type {
  TrustTraceGraphPayload,
  TrustTraceNode as TrustTraceNodeType,
} from '../../types/payloads';
import { validateTrustTraceGraphPayload } from './validation';
import { TrustTraceNode } from './TrustTraceNode';
import { TrustTraceDetails } from './TrustTraceDetails';

const nodeTypes: NodeTypes = {
  trustTraceNode: TrustTraceNode,
};

/**
 * Deterministic layered DAG layout generator.
 * Places nodes in topological ranks (top-to-bottom) with horizontal spacing for branches.
 */
function computeDeterministicLayout(
  rawNodes: TrustTraceNodeType[],
  rawEdges: Array<{ id: string; source: string; target: string; animated?: boolean; label?: string }>
): { nodes: Node[]; edges: Edge[] } {
  if (rawNodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  // Build adjacency and in-degree maps
  const inDegree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  rawNodes.forEach((n) => {
    inDegree.set(n.id, 0);
    adj.set(n.id, []);
  });

  rawEdges.forEach((e) => {
    if (adj.has(e.source) && inDegree.has(e.target)) {
      adj.get(e.source)!.push(e.target);
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
    }
  });

  // Compute node ranks using longest path / BFS from roots (in-degree 0)
  const nodeRank = new Map<string, number>();
  const queue: string[] = [];

  rawNodes.forEach((n) => {
    if ((inDegree.get(n.id) || 0) === 0) {
      queue.push(n.id);
      nodeRank.set(n.id, 0);
    }
  });

  // If cyclic or no roots, seed queue with first node to guarantee termination
  if (queue.length === 0 && rawNodes.length > 0) {
    queue.push(rawNodes[0].id);
    nodeRank.set(rawNodes[0].id, 0);
  }

  let head = 0;
  while (head < queue.length) {
    const currId = queue[head++];
    const currRank = nodeRank.get(currId) || 0;
    const neighbors = adj.get(currId) || [];
    for (const nextId of neighbors) {
      const existingRank = nodeRank.get(nextId);
      if (existingRank === undefined || currRank + 1 > existingRank) {
        nodeRank.set(nextId, currRank + 1);
        queue.push(nextId);
      }
    }
  }

  // Handle disconnected or unvisited nodes
  rawNodes.forEach((n, idx) => {
    if (!nodeRank.has(n.id)) {
      nodeRank.set(n.id, idx);
    }
  });

  // Group nodes by assigned rank
  const rankBuckets = new Map<number, TrustTraceNodeType[]>();
  rawNodes.forEach((n) => {
    const r = nodeRank.get(n.id) || 0;
    if (!rankBuckets.has(r)) {
      rankBuckets.set(r, []);
    }
    rankBuckets.get(r)!.push(n);
  });

  // Position nodes
  const flowNodes: Node[] = [];
  rankBuckets.forEach((nodesInRank, rank) => {
    const count = nodesInRank.length;
    const yPos = rank * 130 + 30;
    nodesInRank.forEach((n, idx) => {
      // Horizontal centering around x = 200
      const xPos = (idx - (count - 1) / 2) * 270 + 200;
      flowNodes.push({
        id: n.id,
        type: 'trustTraceNode',
        position: { x: xPos, y: yPos },
        data: n as unknown as Record<string, unknown>,
        draggable: false,
      });
    });
  });

  // Build presentation edges
  const flowEdges: Edge[] = rawEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: e.animated ?? true,
    label: e.label,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 14,
      height: 14,
      color: '#64748b',
    },
    style: {
      strokeWidth: 2,
      stroke: '#64748b',
    },
  }));

  return { nodes: flowNodes, edges: flowEdges };
}

/**
 * TrustTraceGraphCard — Primary Result Renderer for TRUST_TRACE_GRAPH blocks.
 *
 * Implements Stage 6 requirements:
 * - Validates incoming TrustTraceGraphPayload
 * - Renders a deterministic directed security execution graph using @xyflow/react
 * - Provides read-only node inspection via TrustTraceDetails
 * - Accessible event list for screen-reader and non-canvas users
 * - Full light/dark mode and responsive viewports support
 * - Zero raw JSON dumps, zero client-side fake authorization
 */
export const TrustTraceGraphCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateTrustTraceGraphPayload(block.payload);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showAccessibleList, setShowAccessibleList] = useState(false);

  const payload = validation.isValid ? (block.payload as unknown as TrustTraceGraphPayload) : null;

  // Selected node lookup
  const selectedNode = useMemo(() => {
    if (!payload || !selectedNodeId) return null;
    return payload.nodes.find((n) => n.id === selectedNodeId) || null;
  }, [payload, selectedNodeId]);

  // Compute graph presentation model
  const { nodes: flowNodes, edges: flowEdges } = useMemo(() => {
    if (!payload || payload.nodes.length === 0) {
      return { nodes: [], edges: [] };
    }
    const rawEdges = payload.edges || [];
    return computeDeterministicLayout(payload.nodes, rawEdges);
  }, [payload]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  }, []);

  const handleCloseDetails = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // Validation Failure State
  if (!validation.isValid) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors"
        aria-label="Trust Trace Error"
      >
        <div className="flex items-start gap-3 text-ink-muted dark:text-slate-400 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-semibold text-ink-primary dark:text-slate-200">
              Trust trace could not be displayed
            </p>
            <p className="mt-1 text-slate-500 dark:text-slate-400">
              {validation.error || 'The security telemetry record is malformed or incomplete.'}
            </p>
          </div>
        </div>
      </article>
    );
  }

  // Safe Empty Trace State
  if (!payload || payload.nodes.length === 0) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-6 text-center transition-colors"
        aria-label="Empty Trust Trace"
      >
        <ListTree className="w-8 h-8 text-slate-400 dark:text-slate-500 mx-auto mb-2 opacity-60" aria-hidden="true" />
        <h4 className="text-sm font-semibold text-ink-primary dark:text-slate-200">
          No trust trace events available
        </h4>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
          No security checkpoint telemetry was reported for this conversational turn.
        </p>
      </article>
    );
  }

  // Verdict Stats Calculation
  const passCount = payload.nodes.filter((n) => n.status === 'PASS' || n.status === 'SUCCESS').length;
  const failCount = payload.nodes.filter((n) => n.status === 'FAIL' || n.status === 'DENIED' || n.status === 'ABORTED').length;
  const pendingCount = payload.nodes.filter((n) => n.status === 'PENDING').length;

  return (
    <article
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-3.5 sm:p-4 transition-colors space-y-3.5"
      aria-label={`Security Trust Trace: ${payload.trace_id || 'Active Turn'}`}
    >
      {/* Header Bar */}
      <div className="border-b border-surface-border/60 dark:border-surface-darkBorder/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-brand-700/10 text-brand-700 dark:bg-blue-500/20 dark:text-blue-300">
              <ShieldCheck className="w-3 h-3 text-brand-700 dark:text-blue-300" aria-hidden="true" />
              Security Trust Trace
            </span>
            {payload.final_verdict && (
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded ${
                  payload.final_verdict === 'ALLOW'
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300'
                }`}
              >
                Verdict: {payload.final_verdict}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs text-slate-500 dark:text-slate-400">
            {payload.trace_id && (
              <span className="inline-flex items-center gap-1 font-mono text-[11px]" title="Trace Correlation ID">
                <Hash className="w-3 h-3 text-slate-400" aria-hidden="true" />
                <span className="text-ink-primary dark:text-slate-200">{payload.trace_id}</span>
              </span>
            )}
          </div>
        </div>

        {/* Trace Summary & Checkpoint Counters */}
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-ink-primary dark:text-slate-100">
            {payload.summary || 'Security Pipeline Execution Graph'}
          </h3>
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{passCount} PASS</span>
            {failCount > 0 && (
              <span className="text-red-600 dark:text-red-400 font-semibold">• {failCount} FAIL</span>
            )}
            {pendingCount > 0 && (
              <span className="text-amber-600 dark:text-amber-400 font-semibold">• {pendingCount} PENDING</span>
            )}
            <span className="text-slate-400">({payload.nodes.length} total)</span>
          </div>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div
        className="h-80 sm:h-96 w-full rounded-md border border-surface-border dark:border-surface-darkBorder bg-slate-50 dark:bg-slate-950/50 overflow-hidden relative shadow-inner"
        role="region"
        aria-label="Interactive Security Decision Graph"
      >
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          zoomOnScroll={false}
          panOnScroll={true}
          minZoom={0.3}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#94a3b8" gap={18} size={1} />
          <Controls showInteractive={false} position="bottom-right" className="!bg-white dark:!bg-slate-800 !border-slate-300 dark:!border-slate-700 !shadow-sm" />
        </ReactFlow>
      </div>

      {/* Selected Node Details Drawer */}
      {selectedNode && (
        <TrustTraceDetails node={selectedNode} onClose={handleCloseDetails} />
      )}

      {/* Accessible Textual Event List Toggle */}
      <div className="border-t border-surface-border/50 dark:border-surface-darkBorder/50 pt-2.5">
        <button
          type="button"
          onClick={() => setShowAccessibleList((prev) => !prev)}
          className="w-full flex items-center justify-between text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-brand-700 dark:hover:text-blue-400 transition-colors py-1 focus:outline-none focus:ring-1 focus:ring-brand-700"
          aria-expanded={showAccessibleList}
          aria-controls="accessible-trust-trace-table"
        >
          <span className="flex items-center gap-1.5">
            <ListTree className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Accessible Event Log ({payload.nodes.length} Checkpoints)</span>
          </span>
          {showAccessibleList ? (
            <ChevronUp className="w-4 h-4 text-slate-400" aria-hidden="true" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" aria-hidden="true" />
          )}
        </button>

        {showAccessibleList && (
          <div
            id="accessible-trust-trace-table"
            className="mt-2.5 overflow-x-auto rounded border border-surface-border dark:border-surface-darkBorder"
          >
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 uppercase text-[10px] font-bold border-b border-surface-border dark:border-surface-darkBorder">
                <tr>
                  <th scope="col" className="py-2 px-3">Step</th>
                  <th scope="col" className="py-2 px-3">Stage</th>
                  <th scope="col" className="py-2 px-3">Security Checkpoint</th>
                  <th scope="col" className="py-2 px-3 text-center">Verdict</th>
                  <th scope="col" className="py-2 px-3">Detail</th>
                  <th scope="col" className="py-2 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40 dark:divide-surface-darkBorder/40">
                {payload.nodes.map((n, idx) => (
                  <tr key={n.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="py-2 px-3 font-mono text-slate-400 text-[11px]">{idx + 1}</td>
                    <td className="py-2 px-3 uppercase text-[10px] font-bold text-slate-500 dark:text-slate-400">
                      {n.stage}
                    </td>
                    <td className="py-2 px-3 font-medium text-ink-primary dark:text-slate-100">
                      {n.label}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span
                        className={`inline-block text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                          n.status === 'PASS' || n.status === 'SUCCESS'
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'
                            : n.status === 'FAIL' || n.status === 'DENIED' || n.status === 'ABORTED'
                            ? 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300'
                            : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                        }`}
                      >
                        {n.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-600 dark:text-slate-300 truncate max-w-xs">
                      {n.detail || '—'}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => setSelectedNodeId(n.id)}
                        className="text-brand-700 dark:text-blue-400 hover:underline text-[11px] font-semibold focus:outline-none"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Security & Audit Integrity Footer */}
      <div className="pt-1.5 border-t border-surface-border/40 dark:border-surface-darkBorder/40 flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
        <span>Authoritative security trace captured server-side.</span>
        <span>Zero client-side verification fabrication.</span>
      </div>
    </article>
  );
};
