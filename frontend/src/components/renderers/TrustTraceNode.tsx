import React from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  MinusCircle,
  AlertOctagon,
  Shield,
  Radio,
  UserCheck,
  FileCheck,
  KeyRound,
  Database,
  Network,
} from 'lucide-react';
import type { TrustTraceNode as TrustTraceNodeType } from '../../types/payloads';

export type CustomTraceNodeProps = NodeProps & {
  data: TrustTraceNodeType;
};

function getStageIcon(stage: string) {
  const s = stage.toLowerCase();
  if (s.includes('ingress') || s.includes('mic')) return <Radio className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('deepfake')) return <Shield className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('speaker')) return <UserCheck className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('policy')) return <FileCheck className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('grant')) return <KeyRound className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('commit') || s.includes('tx')) return <Database className="w-3 h-3" aria-hidden="true" />;
  if (s.includes('handshake') || s.includes('agent')) return <Network className="w-3 h-3" aria-hidden="true" />;
  return <Shield className="w-3 h-3" aria-hidden="true" />;
}

function getStatusStyling(status: string) {
  const st = status.toUpperCase();
  if (st === 'PASS' || st === 'SUCCESS') {
    return {
      container:
        'border-emerald-600 bg-emerald-50 text-emerald-950 dark:bg-emerald-950/40 dark:border-emerald-500 dark:text-emerald-100',
      badge:
        'bg-emerald-200/70 text-emerald-900 dark:bg-emerald-900/60 dark:text-emerald-200',
      icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" aria-hidden="true" />,
    };
  }
  if (st === 'FAIL' || st === 'DENIED') {
    return {
      container:
        'border-red-600 bg-red-50 text-red-950 dark:bg-red-950/40 dark:border-red-500 dark:text-red-100',
      badge:
        'bg-red-200/70 text-red-900 dark:bg-red-900/60 dark:text-red-200',
      icon: <XCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 shrink-0" aria-hidden="true" />,
    };
  }
  if (st === 'PENDING') {
    return {
      container:
        'border-amber-500 bg-amber-50 text-amber-950 dark:bg-amber-950/40 dark:border-amber-400 dark:text-amber-100',
      badge:
        'bg-amber-200/70 text-amber-900 dark:bg-amber-900/60 dark:text-amber-200',
      icon: <Clock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" aria-hidden="true" />,
    };
  }
  if (st === 'SKIPPED') {
    return {
      container:
        'border-slate-300 bg-slate-100 text-slate-500 line-through dark:bg-slate-800/60 dark:border-slate-700 dark:text-slate-400',
      badge:
        'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
      icon: <MinusCircle className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500 shrink-0" aria-hidden="true" />,
    };
  }
  if (st === 'ABORTED') {
    return {
      container:
        'border-rose-400 bg-rose-50/50 text-rose-900 dark:bg-rose-950/30 dark:border-rose-600 dark:text-rose-200',
      badge:
        'bg-rose-200/70 text-rose-900 dark:bg-rose-900/60 dark:text-rose-200',
      icon: <AlertOctagon className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400 shrink-0" aria-hidden="true" />,
    };
  }
  // Default / Unknown
  return {
    container:
      'border-slate-300 bg-slate-50 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300',
    badge:
      'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
    icon: <Shield className="w-3.5 h-3.5 text-slate-500 shrink-0" aria-hidden="true" />,
  };
}

export const TrustTraceNode: React.FC<CustomTraceNodeProps> = ({ data, selected }) => {
  const { label, stage, status, detail, timestamp } = data;
  const style = getStatusStyling(status);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Security checkpoint ${label}: status ${status}`}
      className={`w-60 rounded-md border-2 p-2.5 transition-all shadow-sm ${style.container} ${
        selected ? 'ring-2 ring-brand-700 dark:ring-blue-400 ring-offset-1' : ''
      }`}
    >
      {/* React Flow Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-slate-400 dark:!bg-slate-500 !border-2 !border-white dark:!border-slate-900"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-slate-400 dark:!bg-slate-500 !border-2 !border-white dark:!border-slate-900"
      />

      {/* Header: Stage Pill & Verdict Badge */}
      <div className="flex items-center justify-between gap-1.5 mb-1.5">
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider opacity-80">
          {getStageIcon(stage || '')}
          <span>{stage}</span>
        </span>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${style.badge}`}>
          {style.icon}
          <span>{status}</span>
        </span>
      </div>

      {/* Main Label */}
      <div className="text-xs font-bold leading-tight line-clamp-2">
        {label}
      </div>

      {/* Detail or Subtext */}
      {detail && (
        <div className="mt-1 text-[11px] font-mono leading-tight opacity-90 truncate" title={detail}>
          {detail}
        </div>
      )}

      {/* Timestamp Footer */}
      {timestamp && (
        <div className="mt-1 text-[9px] opacity-60 text-right">
          {timestamp}
        </div>
      )}
    </div>
  );
};
