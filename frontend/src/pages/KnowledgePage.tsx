import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, FileText, Globe, Library, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Dropzone } from '@/components/Dropzone'
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import type { DocumentInfo } from '@/lib/types'
import { formatBytes, timeAgo } from '@/lib/utils'

const STATUS = {
  pending: { tone: 'neutral', label: 'Queued' },
  processing: { tone: 'accent', label: 'Indexing' },
  ready: { tone: 'ok', label: 'Ready' },
  failed: { tone: 'bad', label: 'Failed' },
} as const

export function KnowledgePage() {
  const qc = useQueryClient()
  const docs = useQuery({
    queryKey: ['documents'],
    queryFn: api.documents,
    // Poll while anything is still being ingested.
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === 'pending' || d.status === 'processing') ? 1500 : false),
  })
  const stats = useQuery({ queryKey: ['kb-stats', docs.dataUpdatedAt], queryFn: api.kbStats })

  const upload = useMutation({
    mutationFn: api.uploadDocuments,
    onSuccess: (r) => {
      if (r.documents.length) toast.success(`Queued ${r.documents.length} document${r.documents.length > 1 ? 's' : ''} for indexing`)
      if (r.skipped.length) toast.warning(`Skipped ${r.skipped.length}`, { description: r.skipped.slice(0, 5).join('\n') })
      qc.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (e) => toast.error('Upload failed', { description: e.message }),
  })
  const [url, setUrl] = useState('')
  const addUrl = useMutation({
    mutationFn: api.addUrl,
    onSuccess: (r) => {
      if (r.documents.length) toast.success('Page added for indexing')
      if (r.skipped.length) toast.warning('Already in the knowledge base', { description: r.skipped[0] })
      setUrl('')
      qc.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (e) => toast.error('Could not add the page', { description: e.message }),
  })
  const remove = useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
    onError: (e) => toast.error(e.message),
  })
  const reset = useMutation({
    mutationFn: api.resetKnowledgeBase,
    onSuccess: () => {
      toast.success('Knowledge base cleared')
      qc.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-5 py-8">
        <PageHeader
          title="Knowledge base"
          description="Documents are chunked, embedded locally and indexed for hybrid (semantic + keyword) search."
          actions={
            !!docs.data?.length && (
              <Button
                variant="danger"
                size="sm"
                loading={reset.isPending}
                onClick={() => confirm('Delete every document and its index? This cannot be undone.') && reset.mutate()}
              >
                <Trash2 className="size-3.5" /> Reset
              </Button>
            )
          }
        />

        <div className="mb-6 grid grid-cols-2 gap-3 sm:max-w-md">
          <Stat label="Documents" value={stats.data?.documents} />
          <Stat label="Indexed chunks" value={stats.data?.chunks} />
        </div>

        <Dropzone
          accept=".pdf,.docx,.pptx,.txt,.md,.zip"
          multiple
          busy={upload.isPending}
          onFiles={(f) => upload.mutate(f)}
          hint="PDF, DOCX, PPTX, TXT, Markdown or a ZIP of them · duplicates are skipped"
        />

        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) addUrl.mutate(url.trim())
          }}
        >
          <label className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-line bg-panel px-3 focus-within:border-accent/60">
            <Globe className="size-4 shrink-0 text-faint" />
            <span className="sr-only">Web page URL</span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Add a web page: https://…"
              className="h-full flex-1 bg-transparent text-sm placeholder:text-faint focus:outline-none"
            />
          </label>
          <Button type="submit" variant="secondary" loading={addUrl.isPending} disabled={!url.trim()}>
            Add page
          </Button>
        </form>

        <Card className="mt-6 overflow-hidden">
          {docs.isLoading ? (
            <div className="grid place-items-center py-14">
              <Spinner />
            </div>
          ) : !docs.data?.length ? (
            <EmptyState icon={<Library className="size-5" />} title="No documents yet">
              Upload files above, then ask questions about them in chat.
            </EmptyState>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-sunken/50 text-left text-sm text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="hidden px-4 py-2 font-medium sm:table-cell">Size</th>
                  <th className="hidden px-4 py-2 font-medium sm:table-cell">Chunks</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {docs.data.map((d) => (
                  <DocRow key={d.id} d={d} onDelete={() => remove.mutate(d.id)} />
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}

function DocRow({ d, onDelete }: { d: DocumentInfo; onDelete: () => void }) {
  const s = STATUS[d.status]
  return (
    <tr className="group">
      <td className="max-w-0 px-4 py-2.5">
        <div className="flex items-center gap-2">
          {d.content_type === 'url' ? <Globe className="size-4 shrink-0 text-muted" /> : <FileText className="size-4 shrink-0 text-muted" />}
          <span className="truncate font-medium" title={d.filename}>
            {d.filename}
          </span>
        </div>
        <div className="pl-6 text-xs text-faint">{timeAgo(d.created_at)}</div>
      </td>
      <td className="hidden px-4 py-2.5 text-muted tabular-nums sm:table-cell">{formatBytes(d.size_bytes)}</td>
      <td className="hidden px-4 py-2.5 text-muted tabular-nums sm:table-cell">{d.status === 'ready' ? d.chunk_count : '—'}</td>
      <td className="px-4 py-2.5">
        <Badge tone={s.tone}>
          {d.status === 'processing' || d.status === 'pending' ? (
            <Spinner className="size-3 text-current" />
          ) : d.status === 'ready' ? (
            <CheckCircle2 className="size-3" />
          ) : (
            <AlertCircle className="size-3" />
          )}
          {s.label}
        </Badge>
        {d.error && <p className="mt-1 max-w-[260px] text-xs text-bad">{d.error}</p>}
      </td>
      <td className="px-2">
        <button
          type="button"
          aria-label={`Delete ${d.filename}`}
          onClick={() => confirm(`Delete ${d.filename}?`) && onDelete()}
          className="grid size-7 place-items-center rounded-md text-muted opacity-0 hover:bg-bad-soft hover:text-bad group-hover:opacity-100 focus:opacity-100 cursor-pointer"
        >
          <Trash2 className="size-3.5" />
        </button>
      </td>
    </tr>
  )
}

function Stat({ label, value }: { label: string; value?: number }) {
  return (
    <Card className="px-5 py-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-2 text-2xl font-medium tabular-nums">{value?.toLocaleString() ?? '—'}</p>
    </Card>
  )
}
