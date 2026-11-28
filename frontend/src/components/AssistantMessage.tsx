import { useMutation } from '@tanstack/react-query'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  Workflow,
} from 'lucide-react'
import { lazy, Suspense, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import type { LogLine } from '@/hooks/useChatStream'
import type { Message, MessageMeta, NodeName, Source } from '@/lib/types'
import { cn, formatMs } from '@/lib/utils'
import { NODE_META, type NodeState } from '@/lib/agents'
import { Markdown } from './Markdown'
import { SourceList } from './Sources'
import { Badge, Spinner } from './ui'

const AgentGraph = lazy(() => import('./AgentGraph').then((m) => ({ default: m.AgentGraph })))

const ROUTE_LABEL = { retrieve: 'Documents', web_search: 'Web', data_analyst: 'Data analysis' } as const

interface Props {
  content: string
  sources: Source[]
  meta?: MessageMeta
  nodes: Partial<Record<NodeName, NodeState>>
  logs?: LogLine[]
  code?: { code: string; attempt: number }[]
  streaming?: boolean
  error?: string
  message?: Message
}

export function AssistantMessage({ content, sources, meta, nodes, logs = [], code = [], streaming, error, message }: Props) {
  const [showDetails, setShowDetails] = useState(!!streaming)
  const [showSources, setShowSources] = useState(false)
  const [cite, setCite] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(message?.feedback ?? null)

  const fb = useMutation({
    mutationFn: (v: 1 | -1 | 0) => api.feedback(message!.id, v),
    onMutate: (v) => setFeedback(v || null),
  })

  const activeNode = (Object.entries(nodes) as [NodeName, NodeState][]).find(([, s]) => s.status === 'active')?.[0]
  const verdict = meta?.verification?.verdict
  const allCode = code.length ? code : meta?.analysis?.code ? [{ code: meta.analysis.code, attempt: 1 }] : []
  const visibleSources = useMemo(() => sources.filter((s) => s.kind !== 'system'), [sources])

  const onCite = (n: number) => {
    setShowSources(true)
    setCite(n)
  }

  return (
    <div className="group/msg">
      {/* Header: route + verification + timing */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-sm">
        {streaming ? (
          <span className="inline-flex items-center gap-1.5 text-muted">
            <Spinner className="size-3.5 text-accent" />
            {activeNode ? `${NODE_META[activeNode].label}…` : 'Starting…'}
          </span>
        ) : (
          <>
            {meta?.route && <Badge tone="accent">{ROUTE_LABEL[meta.route]}</Badge>}
            {verdict === 'supported' && (
              <Badge tone="ok">
                <ShieldCheck className="size-3" /> Verified
              </Badge>
            )}
            {verdict === 'unsupported' && (
              <Badge tone="warn">
                <ShieldAlert className="size-3" /> Not fully supported
              </Badge>
            )}
            {(meta?.attempts ?? 1) > 1 && <Badge>Regenerated ×{(meta?.attempts ?? 1) - 1}</Badge>}
            {meta?.duration_ms != null && <span className="text-faint tabular-nums">{formatMs(meta.duration_ms)}</span>}
          </>
        )}
        <button
          type="button"
          onClick={() => setShowDetails((v) => !v)}
          className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-muted hover:bg-sunken hover:text-ink cursor-pointer"
          aria-expanded={showDetails}
        >
          <Workflow className="size-3.5" /> Agent trace
          <ChevronDown className={cn('size-3.5 transition-transform', showDetails && 'rotate-180')} />
        </button>
      </div>

      {showDetails && (
        <div className="mb-3 overflow-hidden rounded-xl border border-line bg-panel">
          {/* Below lg the chat column is too narrow for legible node labels (<11px); the timeline below shows the same steps */}
          <div className="hidden lg:block">
            <Suspense fallback={<div className="h-[200px]" />}>
              <AgentGraph states={nodes} className="bg-sunken/40" />
            </Suspense>
          </div>
          {(logs.length > 0 || allCode.length > 0 || meta?.query) && (
            <div className="max-h-64 overflow-auto border-line px-3 py-2 font-mono lg:border-t text-xs leading-relaxed">
              {meta?.query && !logs.length && (
                <div className="text-muted">
                  <span className="text-accent">query</span> {meta.query}
                </div>
              )}
              {logs.map((l, i) => (
                <div key={i} className="flex gap-2">
                  <span className="w-12 shrink-0 text-right text-faint tabular-nums">{(l.at / 1000).toFixed(1)}s</span>
                  <span className="w-24 shrink-0 truncate text-accent">{l.node}</span>
                  <span className="text-muted break-words min-w-0">{l.message}</span>
                </div>
              ))}
              {(meta?.timeline ?? []).length > 0 && !logs.length &&
                meta!.timeline!.map((t, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="w-24 shrink-0 truncate text-accent">{t.node}</span>
                    <span className="text-muted">
                      {t.summary} · {formatMs(t.duration_ms)}
                    </span>
                  </div>
                ))}
              {allCode.map((c, i) => (
                <div key={`c${i}`} className="mt-2">
                  <div className="mb-1 text-faint">generated code · attempt {c.attempt}</div>
                  <Markdown content={'```python\n' + c.code + '\n```'} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Answer */}
      {content ? (
        <Markdown content={content} sourceCount={visibleSources.length} onCite={onCite} />
      ) : streaming ? (
        <div className="space-y-2 py-1" aria-hidden>
          <div className="h-3 w-3/4 animate-pulse rounded bg-sunken" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-sunken" />
        </div>
      ) : null}
      {streaming && content && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" />}

      {error && (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          {error}
        </div>
      )}

      {!streaming && verdict === 'unsupported' && meta?.verification?.reason && (
        <p className="mt-2 text-sm text-warn">Verifier: {meta.verification.reason}</p>
      )}

      {/* Sources + actions */}
      {!streaming && (visibleSources.length > 0 || message) && (
        <div className="mt-3 flex items-center gap-1 text-sm text-muted">
          {visibleSources.length > 0 && (
            <button
              type="button"
              onClick={() => setShowSources((v) => !v)}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-sunken hover:text-ink cursor-pointer"
              aria-expanded={showSources}
            >
              {visibleSources.length} source{visibleSources.length > 1 && 's'}
              <ChevronDown className={cn('size-3.5 transition-transform', showSources && 'rotate-180')} />
            </button>
          )}
          {message && (
            <div className="ml-auto flex items-center gap-0.5 opacity-60 transition-opacity group-hover/msg:opacity-100">
              <IconBtn
                label="Copy answer"
                onClick={() => {
                  navigator.clipboard.writeText(content)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
              >
                {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />}
              </IconBtn>
              <IconBtn label="Good answer" active={feedback === 1} onClick={() => fb.mutate(feedback === 1 ? 0 : 1)}>
                <ThumbsUp className="size-3.5" />
              </IconBtn>
              <IconBtn label="Bad answer" active={feedback === -1} onClick={() => fb.mutate(feedback === -1 ? 0 : -1)}>
                <ThumbsDown className="size-3.5" />
              </IconBtn>
            </div>
          )}
        </div>
      )}
      {showSources && (
        <div className="mt-2">
          <SourceList sources={visibleSources} highlighted={cite} />
        </div>
      )}
    </div>
  )
}

function IconBtn({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn('grid size-7 place-items-center rounded-md hover:bg-sunken hover:text-ink cursor-pointer', active && 'text-accent')}
    >
      {children}
    </button>
  )
}
