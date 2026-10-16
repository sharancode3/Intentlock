import React from 'react';
import { Mic, Loader2, AlertCircle, AlertTriangle, CheckCircle, ShieldCheck } from 'lucide-react';
import type { TurnStatusType, TurnStatusNotice } from '../../types';

interface TurnStatusProps {
  status: TurnStatusNotice;
  className?: string;
}

export const TurnStatus: React.FC<TurnStatusProps> = ({ status, className = '' }) => {
  if (status.type === 'idle') {
    return null;
  }

  const getStatusConfig = (type: TurnStatusType) => {
    switch (type) {
      case 'listening':
        return {
          bg: 'bg-brand-50 border-brand-200 text-brand-900 dark:bg-blue-950/50 dark:border-blue-800 dark:text-blue-200',
          icon: <Mic className="w-4 h-4 text-brand-700 animate-pulse shrink-0" aria-hidden="true" />,
          defaultText: 'Listening to your speech...',
        };
      case 'silence':
        return {
          bg: 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/50 dark:border-amber-800 dark:text-amber-200',
          icon: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" aria-hidden="true" />,
          defaultText: 'No speech detected. Please speak closer to the microphone.',
        };
      case 'transcribing':
        return {
          bg: 'bg-slate-100 border-slate-300 text-slate-800 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200',
          icon: <Loader2 className="w-4 h-4 text-slate-600 dark:text-slate-400 animate-spin shrink-0" aria-hidden="true" />,
          defaultText: 'Transcribing speech in memory...',
        };
      case 'reasoning':
        return {
          bg: 'bg-brand-50 border-brand-200 text-brand-900 dark:bg-blue-950/50 dark:border-blue-800 dark:text-blue-200',
          icon: <Loader2 className="w-4 h-4 text-brand-700 animate-spin shrink-0" aria-hidden="true" />,
          defaultText: 'Analyzing request & checking policy...',
        };
      case 'verifying':
        return {
          bg: 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/50 dark:border-amber-800 dark:text-amber-200',
          icon: <ShieldCheck className="w-4 h-4 text-amber-600 animate-pulse shrink-0" aria-hidden="true" />,
          defaultText: 'Evaluating voice authenticity & speaker profile...',
        };
      case 'clarification':
        return {
          bg: 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/50 dark:border-amber-800 dark:text-amber-200',
          icon: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" aria-hidden="true" />,
          defaultText: 'Please clarify your statement or employee ID.',
        };
      case 'result_ready':
        return {
          bg: 'bg-emerald-50 border-emerald-200 text-emerald-900 dark:bg-emerald-950/50 dark:border-emerald-800 dark:text-emerald-200',
          icon: <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden="true" />,
          defaultText: 'Response ready.',
        };
      case 'denial':
        return {
          bg: 'bg-red-50 border-red-200 text-red-900 dark:bg-red-950/50 dark:border-red-800 dark:text-red-200',
          icon: <AlertCircle className="w-4 h-4 text-red-600 shrink-0" aria-hidden="true" />,
          defaultText: 'Access denied under policy.',
        };
      case 'error':
        return {
          bg: 'bg-red-50 border-red-200 text-red-900 dark:bg-red-950/50 dark:border-red-800 dark:text-red-200',
          icon: <AlertCircle className="w-4 h-4 text-red-600 shrink-0" aria-hidden="true" />,
          defaultText: 'An operational error occurred.',
        };
      default:
        return {
          bg: 'bg-slate-100 border-slate-200 text-slate-700',
          icon: <Loader2 className="w-4 h-4 animate-spin shrink-0" />,
          defaultText: 'Processing...',
        };
    }
  };

  const config = getStatusConfig(status.type);

  return (
    <div
      aria-live="polite"
      className={`rounded-flat border px-3 py-2 flex items-center gap-2 text-xs sm:text-sm font-medium transition-all ${config.bg} ${className}`}
    >
      {config.icon}
      <span className="truncate flex-1">{status.message || config.defaultText}</span>
      {status.countdownSeconds !== undefined && status.countdownSeconds > 0 && (
        <span className="font-mono text-xs opacity-75 shrink-0">
          {status.countdownSeconds}s
        </span>
      )}
    </div>
  );
};
