import { BarChart3, ExternalLink, FileText, Globe, TrendingUp } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Source } from '@/lib/types'
import { cn } from '@/lib/utils'

const KIND_ICON = { document: FileText, web: Globe, tool: TrendingUp, analysis: BarChart3, system: FileText }

export function SourceList({ sources, highlighted }: { sources: Source[]; highlighted: number | null }) {
  const refs = useRef<(HTMLLIElement | null)[]>([])

  useEffect(() => {
    if (highlighted != null) refs.current[highlighted - 1]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [highlighted])

  if (!sources.length) return null
  return (
    <ol className="grid gap-2 sm:grid-cols-2">
      {sources.map((s, i) => {
        const Icon = KIND_ICON[s.kind] ?? FileText
        return (
          <li
            key={i}
            ref={(el) => {
              refs.current[i] = el
            }}
            className={cn(
              'group rounded-lg border bg-panel p-2.5 text-[12.5px] transition-colors',
              highlighted === i + 1 ? 'border-accent ring-2 ring-accent/20' : 'border-line',
            )}
          >
            <div className="mb-1 flex items-center gap-1.5 text-muted">
              <span className="grid size-4 place-items-center rounded bg-sunken text-[10px] font-semibold text-ink">{i + 1}</span>
              <Icon className="size-3.5 shrink-0" />
              <span className="truncate font-medium text-ink" title={s.source}>
                {s.source}
              </span>
              {s.page != null && <span className="shrink-0">p.{s.page}</span>}
              {s.url && (
                <a href={s.url} target="_blank" rel="noreferrer noopener" className="ml-auto shrink-0 hover:text-accent" aria-label="Open source">
                  <ExternalLink className="size-3.5" />
                </a>
              )}
            </div>
            <p className="line-clamp-3 text-muted leading-relaxed whitespace-pre-line">{s.text}</p>
          </li>
        )
      })}
    </ol>
  )
}
