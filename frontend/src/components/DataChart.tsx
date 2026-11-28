import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ChartSpec } from '@/lib/chart'

// First series carries the accent; the rest are neutral steps so one thing leads.
const SERIES_COLORS = ['var(--color-accent)', 'var(--color-faint)', 'var(--color-muted)']
const AXIS = { fontSize: 12, fontFamily: 'var(--font-mono)', fill: 'var(--color-faint)' }
const fmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

export default function DataChart({ spec }: { spec: ChartSpec }) {
  const common = {
    data: spec.data,
    margin: { top: 8, right: 8, bottom: 0, left: 0 },
  }
  const axes = (
    <>
      <CartesianGrid stroke="var(--color-line)" vertical={false} />
      <XAxis dataKey={spec.x} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--color-line)' }} interval="preserveStartEnd" />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => fmt.format(v)} />
      <Tooltip
        cursor={{ fill: 'var(--color-sunken)' }}
        formatter={(v) => (typeof v === 'number' ? fmt.format(v) : String(v))}
        contentStyle={{
          background: 'var(--color-panel)',
          border: '1px solid var(--color-line)',
          borderRadius: 8,
          fontSize: 13,
          color: 'var(--color-ink)',
        }}
      />
    </>
  )
  return (
    <figure className="mt-4 rounded-xl border border-line bg-panel p-4" aria-label={`Chart of ${spec.series.join(', ')} by ${spec.x}`}>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {spec.kind === 'line' ? (
            <LineChart {...common}>
              {axes}
              {spec.series.map((s, i) => (
                <Line key={s} type="monotone" dataKey={s} stroke={SERIES_COLORS[i]} strokeWidth={2} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          ) : (
            <BarChart {...common}>
              {axes}
              {spec.series.map((s, i) => (
                <Bar key={s} dataKey={s} fill={SERIES_COLORS[i]} radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false} />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      {spec.series.length > 1 && (
        <figcaption className="mt-2 flex gap-4 text-xs text-muted">
          {spec.series.map((s, i) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: SERIES_COLORS[i] }} />
              {s}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  )
}
