import { ResponsiveContainer, LineChart, AreaChart, Line, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import type { MetricDataPoint } from '../../types/payloads';

export function MetricTimeChart({ data, variant }: { data: MetricDataPoint[]; variant: 'LINE' | 'AREA' }) {
  if (!data.length) return <p className="py-8 text-center text-xs text-ink-muted dark:text-slate-400">No dated ticket events are available for this chart.</p>;
  const common = <><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fontSize: 10 }} /><Tooltip /></>;
  return <div className="w-full h-64" role="img" aria-label={`Ticket creation counts over time: ${data.map(point => `${point.label}: ${point.count}`).join(', ')}`}>
    <ResponsiveContainer width="100%" height="100%">
      {variant === 'LINE' ? <LineChart data={data}>{common}<Line type="monotone" dataKey="count" stroke="#1d4ed8" strokeWidth={2} isAnimationActive={false} /></LineChart>
        : <AreaChart data={data}>{common}<Area type="monotone" dataKey="count" stroke="#1d4ed8" fill="#93c5fd" isAnimationActive={false} /></AreaChart>}
    </ResponsiveContainer>
  </div>;
}
