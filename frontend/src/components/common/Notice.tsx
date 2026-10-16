import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

export type NoticeVariant = 'info' | 'warning' | 'danger' | 'success' | 'neutral';

interface NoticeProps {
  variant?: NoticeVariant;
  title?: string;
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export const Notice: React.FC<NoticeProps> = ({
  variant = 'neutral',
  title,
  children,
  onDismiss,
  className = '',
}) => {
  const getVariantStyles = () => {
    switch (variant) {
      case 'info':
        return {
          container: 'bg-state-infoBg border-state-infoBorder text-blue-900 dark:bg-blue-950/40 dark:border-blue-800 dark:text-blue-200',
          icon: <Info className="w-5 h-5 text-brand-700 dark:text-blue-400 shrink-0 mt-0.5" aria-hidden="true" />,
        };
      case 'warning':
        return {
          container: 'bg-state-warningBg border-state-warningBorder text-amber-950 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-200',
          icon: <AlertTriangle className="w-5 h-5 text-state-warning dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />,
        };
      case 'danger':
        return {
          container: 'bg-state-dangerBg border-state-dangerBorder text-red-950 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200',
          icon: <AlertCircle className="w-5 h-5 text-state-danger dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />,
        };
      case 'success':
        return {
          container: 'bg-state-successBg border-state-successBorder text-emerald-950 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-200',
          icon: <CheckCircle2 className="w-5 h-5 text-state-success dark:text-emerald-400 shrink-0 mt-0.5" aria-hidden="true" />,
        };
      case 'neutral':
      default:
        return {
          container: 'bg-slate-50 border-slate-200 text-slate-800 dark:bg-slate-800/60 dark:border-slate-700 dark:text-slate-200',
          icon: <Info className="w-5 h-5 text-slate-500 dark:text-slate-400 shrink-0 mt-0.5" aria-hidden="true" />,
        };
    }
  };

  const { container, icon } = getVariantStyles();

  return (
    <div
      role={variant === 'danger' ? 'alert' : 'status'}
      className={`rounded-flat border p-3 flex items-start gap-3 transition-colors ${container} ${className}`}
    >
      {icon}
      <div className="flex-1 text-sm leading-relaxed min-w-0">
        {title && <h4 className="font-semibold mb-0.5 tracking-tight">{title}</h4>}
        <div className="break-words">{children}</div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 p-1 rounded-sm focus:outline-none focus:ring-2 focus:ring-brand-700"
          aria-label="Dismiss notice"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};
