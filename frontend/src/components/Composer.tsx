import { useQuery } from '@tanstack/react-query'
import { ArrowUp, BarChart3, FileText, Globe, Signpost, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { ChatMode } from '@/lib/types'
import { cn } from '@/lib/utils'
import { DocumentPicker } from './DocumentPicker'
import { Segmented, Switch } from './ui'

export interface ChatOptions {
  mode: ChatMode
  verify: boolean
  top_k: number
  dataset_id: string | null
  document_ids: string[]
}

const MODES = [
  { value: 'auto' as const, label: 'Auto', icon: <Signpost className="size-3.5" />, title: 'The router picks documents or the web' },
  { value: 'documents' as const, label: 'Docs', icon: <FileText className="size-3.5" />, title: 'Answer only from your knowledge base' },
  { value: 'web' as const, label: 'Web', icon: <Globe className="size-3.5" />, title: 'Search the live web' },
  { value: 'data' as const, label: 'Data', icon: <BarChart3 className="size-3.5" />, title: 'Analyze a CSV/Excel dataset' },
]

export function Composer({
  options,
  onOptions,
  onSend,
  onStop,
  busy,
  autoFocus,
}: {
  options: ChatOptions
  onOptions: (o: ChatOptions) => void
  onSend: (text: string) => void
  onStop: () => void
  busy: boolean
  autoFocus?: boolean
}) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets, enabled: options.mode === 'data' })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 220) + 'px'
  }, [text])

  useEffect(() => {
    if (autoFocus) ref.current?.focus()
  }, [autoFocus])

  const submit = () => {
    const t = text.trim()
    if (!t || busy) return
    onSend(t)
    setText('')
  }

  const set = <K extends keyof ChatOptions>(k: K, v: ChatOptions[K]) => onOptions({ ...options, [k]: v })

  return (
    <div className="rounded-2xl border border-line bg-panel shadow-sm focus-within:border-accent/60 transition-colors">
      <textarea
        ref={ref}
        value={text}
        rows={1}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder={options.mode === 'data' ? 'Ask about your dataset' : 'Ask a question'}
        aria-label="Message"
        className="block w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-md placeholder:text-faint focus:outline-none"
        maxLength={4000}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 pb-3">
        <Segmented label="Answer source" value={options.mode} onChange={(v) => set('mode', v)} options={MODES} />
        {options.mode === 'data' ? (
          <select
            value={options.dataset_id ?? ''}
            onChange={(e) => set('dataset_id', e.target.value || null)}
            className="h-7 max-w-[200px] rounded-md border border-line bg-panel px-2 text-sm text-ink"
            aria-label="Dataset"
          >
            <option value="">Latest dataset</option>
            {datasets.data?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.filename}
              </option>
            ))}
          </select>
        ) : (
          <>
            {options.mode !== 'web' && (
              <DocumentPicker value={options.document_ids ?? []} onChange={(ids) => set('document_ids', ids)} />
            )}
            <Switch checked={options.verify} onChange={(v) => set('verify', v)} label="Verify" />
            <label className="inline-flex items-center gap-1.5 text-sm text-muted" title="Passages passed to the reasoner">
              Top-k
              <input
                type="number"
                min={1}
                max={20}
                value={options.top_k}
                onChange={(e) => set('top_k', Math.max(1, Math.min(20, Number(e.target.value) || 5)))}
                className="h-7 w-12 rounded-md border border-line bg-panel px-1.5 text-center text-ink tabular-nums"
              />
            </label>
          </>
        )}
        <div className="ml-auto">
          {busy ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              className="grid size-8 place-items-center rounded-lg bg-ink text-bg hover:opacity-85 cursor-pointer"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!text.trim()}
              aria-label="Send message"
              className={cn(
                'grid size-8 place-items-center rounded-lg transition-colors cursor-pointer',
                text.trim() ? 'bg-accent text-white dark:text-zinc-950 hover:opacity-90' : 'bg-sunken text-faint',
              )}
            >
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
