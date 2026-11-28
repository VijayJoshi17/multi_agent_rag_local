import type { AnalysisTable } from './types'

export interface ChartSpec {
  kind: 'bar' | 'line'
  x: string
  series: string[]
  data: Record<string, string | number | null>[]
}

const isNum = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
const DATE_RE = /^\d{4}-\d{2}(-\d{2})?([ T].*)?$/

/** Pick a chart for a result table, or null when a chart would not help (one row, no numbers). */
export function chartFor(table: AnalysisTable | null | undefined): ChartSpec | null {
  if (!table || table.rows.length < 2 || table.columns.length < 2) return null
  const col = (i: number) => table.rows.map((r) => r[i])
  const numeric = table.columns.map((_, i) => col(i).every((v) => v === null || isNum(v)) && col(i).some(isNum))

  // x axis: the first non-numeric column, else the first column (e.g. a year)
  let xi = numeric.findIndex((n) => !n)
  if (xi === -1) xi = 0
  const series = table.columns.filter((_, i) => i !== xi && numeric[i]).slice(0, 3)
  if (!series.length) return null

  const xs = col(xi)
  const ordered =
    xs.every((v) => typeof v === 'string' && DATE_RE.test(v)) ||
    (xs.every(isNum) && xs.every((v, i) => i === 0 || (v as number) > (xs[i - 1] as number)))

  const x = table.columns[xi]
  const data = table.rows.map((r) =>
    Object.fromEntries(table.columns.map((c, i) => [c, i === xi ? String(r[i]) : (r[i] as number | null)])),
  )
  return { kind: ordered ? 'line' : 'bar', x, series, data }
}
