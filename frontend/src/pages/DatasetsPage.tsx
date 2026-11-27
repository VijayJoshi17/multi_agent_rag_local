import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, MessageSquare, Table2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import type { ChatOptions } from '@/components/Composer'
import { Dropzone } from '@/components/Dropzone'
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import type { Dataset } from '@/lib/types'
import { cn, formatBytes, timeAgo } from '@/lib/utils'

export function DatasetsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string | null>(null)
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets })
  const current = datasets.data?.find((d) => d.id === selected) ?? datasets.data?.[0]

  const upload = useMutation({
    mutationFn: (files: File[]) => api.uploadDataset(files[0]),
    onSuccess: (d) => {
      toast.success(`${d.filename} uploaded`, { description: `${d.row_count.toLocaleString()} rows · ${d.columns.length} columns` })
      setSelected(d.id)
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
    onError: (e) => toast.error('Upload failed', { description: e.message }),
  })
  const remove = useMutation({
    mutationFn: api.deleteDataset,
    onSuccess: () => {
      setSelected(null)
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
  })

  const analyze = (d: Dataset) => {
    const raw = localStorage.getItem('rag.chatOptions')
    const opts: Partial<ChatOptions> = raw ? JSON.parse(raw) : {}
    localStorage.setItem('rag.chatOptions', JSON.stringify({ ...opts, mode: 'data', dataset_id: d.id }))
    navigate('/')
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-8">
        <PageHeader
          title="Datasets"
          description="The Data Analyst agent writes pandas code for your question and runs it in an isolated, network-less sandbox."
        />
        <Dropzone accept=".csv,.xlsx" busy={upload.isPending} onFiles={(f) => upload.mutate(f)} hint="CSV or Excel (.xlsx)" />

        {datasets.isLoading ? (
          <div className="grid place-items-center py-14">
            <Spinner />
          </div>
        ) : !datasets.data?.length ? (
          <Card className="mt-6">
            <EmptyState icon={<BarChart3 className="size-5" />} title="No datasets yet">
              Upload a spreadsheet, then switch the chat to <b>Data</b> mode to analyze it.
            </EmptyState>
          </Card>
        ) : (
          <div className="mt-6 grid gap-4 lg:grid-cols-[260px_1fr]">
            <ul className="space-y-1.5">
              {datasets.data.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(d.id)}
                    className={cn(
                      'w-full rounded-lg border px-3 py-2.5 text-left transition-colors cursor-pointer',
                      current?.id === d.id ? 'border-accent/50 bg-accent-soft/40' : 'border-line bg-panel hover:bg-sunken',
                    )}
                  >
                    <div className="flex items-center gap-2 text-[13px] font-medium">
                      <Table2 className="size-4 shrink-0 text-muted" />
                      <span className="truncate">{d.filename}</span>
                    </div>
                    <p className="mt-0.5 pl-6 text-[11.5px] text-muted">
                      {d.row_count.toLocaleString()} rows · {formatBytes(d.size_bytes)} · {timeAgo(d.created_at)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
            {current && <DatasetDetail d={current} onAnalyze={() => analyze(current)} onDelete={() => remove.mutate(current.id)} />}
          </div>
        )}
      </div>
    </div>
  )
}

function DatasetDetail({ d, onAnalyze, onDelete }: { d: Dataset; onAnalyze: () => void; onDelete: () => void }) {
  const preview = useQuery({ queryKey: ['dataset-preview', d.id], queryFn: () => api.datasetPreview(d.id) })
  return (
    <Card className="min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="mr-auto truncate text-sm font-semibold">{d.filename}</h2>
        <Button size="sm" variant="primary" onClick={onAnalyze}>
          <MessageSquare className="size-3.5" /> Analyze in chat
        </Button>
        <Button size="sm" variant="danger" onClick={() => confirm(`Delete ${d.filename}?`) && onDelete()} aria-label="Delete dataset">
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1.5 border-b border-line px-4 py-3">
        {d.columns.map((c) => (
          <Badge key={c.name}>
            <span className="text-ink">{c.name}</span>
            <span className="text-faint">{c.dtype}</span>
          </Badge>
        ))}
      </div>
      <div className="max-h-[420px] overflow-auto">
        {preview.isLoading ? (
          <div className="grid place-items-center py-10">
            <Spinner />
          </div>
        ) : preview.data ? (
          <table className="w-full text-[12.5px]">
            <thead className="sticky top-0 bg-sunken text-left">
              <tr>
                {preview.data.columns.map((c) => (
                  <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {preview.data.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((v, j) => (
                    <td key={j} className={cn('whitespace-nowrap px-3 py-1.5', typeof v === 'number' && 'text-right tabular-nums')}>
                      {v == null ? <span className="text-faint">null</span> : String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="p-4 text-sm text-muted">Preview unavailable.</p>
        )}
      </div>
      <p className="border-t border-line px-4 py-2 text-[11.5px] text-muted">
        Showing first {preview.data?.rows.length ?? 0} of {d.row_count.toLocaleString()} rows
      </p>
    </Card>
  )
}
