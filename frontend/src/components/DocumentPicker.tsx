import { useQuery } from '@tanstack/react-query'
import { Check, ChevronDown, FileText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Restrict a question to some documents. An empty selection means "all documents". */
export function DocumentPicker({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const docs = useQuery({ queryKey: ['documents'], queryFn: api.documents, enabled: open || value.length > 0 })
  const ready = (docs.data ?? []).filter((d) => d.status === 'ready')

  // Drop ids of documents that were deleted since they were picked.
  useEffect(() => {
    if (docs.data && value.some((id) => !ready.some((d) => d.id === id))) {
      onChange(value.filter((id) => ready.some((d) => d.id === id)))
    }
  }, [docs.data]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  const label = value.length === 0 ? 'All documents' : value.length === 1 ? (ready.find((d) => d.id === value[0])?.filename ?? '1 document') : `${value.length} documents`

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cn(
          'inline-flex h-7 max-w-[200px] items-center gap-1.5 rounded-md border px-2 text-sm transition-colors cursor-pointer',
          value.length ? 'border-accent/40 bg-accent-soft text-accent-ink' : 'border-line text-muted hover:text-ink',
        )}
      >
        <FileText className="size-3.5 shrink-0" />
        <span className="truncate">{label}</span>
        <ChevronDown className="size-3.5 shrink-0" />
      </button>
      {open && (
        <div className="absolute bottom-9 left-0 z-20 w-72 rounded-xl border border-line bg-panel p-1 shadow-[0_8px_24px_rgba(0,0,0,0.08)]">
          <p className="px-2.5 pt-1.5 pb-1 text-xs text-faint">Search only in</p>
          <ul role="listbox" aria-multiselectable className="max-h-64 overflow-y-auto">
            <li>
              <button
                type="button"
                role="option"
                aria-selected={value.length === 0}
                onClick={() => onChange([])}
                className="flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-left text-sm hover:bg-sunken cursor-pointer"
              >
                <Check className={cn('size-3.5 shrink-0', value.length === 0 ? 'text-accent' : 'invisible')} />
                All documents
              </button>
            </li>
            {ready.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={value.includes(d.id)}
                  onClick={() => toggle(d.id)}
                  title={d.filename}
                  className="flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-left text-sm hover:bg-sunken cursor-pointer"
                >
                  <Check className={cn('size-3.5 shrink-0', value.includes(d.id) ? 'text-accent' : 'invisible')} />
                  <span className="truncate">{d.filename}</span>
                </button>
              </li>
            ))}
            {docs.isSuccess && ready.length === 0 && <li className="px-2.5 py-2 text-sm text-muted">No documents yet</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
