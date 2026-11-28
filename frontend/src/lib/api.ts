import type {
  ChatEvent,
  ChatRequest,
  Conversation,
  ConversationDetail,
  Dataset,
  DatasetPreview,
  DocumentInfo,
  Health,
  KnowledgeBaseStats,
  Message,
  UploadResult,
} from './types'

const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1'
const KEY_STORAGE = 'rag.apiKey'

export const apiKey = {
  get: () => localStorage.getItem(KEY_STORAGE) ?? '',
  set: (v: string) => (v ? localStorage.setItem(KEY_STORAGE, v) : localStorage.removeItem(KEY_STORAGE)),
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()
export const onUnauthorized = (fn: Listener) => {
  unauthorizedListeners.add(fn)
  return () => void unauthorizedListeners.delete(fn)
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  const key = apiKey.get()
  if (key) h.set('X-API-Key', key)
  return h
}

async function toError(res: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
    } else if (body?.detail) {
      message = typeof body.detail === 'string' ? body.detail : message
    }
  } catch {
    /* non-JSON body */
  }
  if (res.status === 401) unauthorizedListeners.forEach((fn) => fn())
  return new ApiError(res.status, code, message)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, { ...init, headers: headers(init.headers) })
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
  headers: { 'Content-Type': 'application/json' },
})

export const api = {
  health: () => request<Health>('/health/ready').catch((e: ApiError) => {
    if (e.status === 503) return { status: 'degraded', checks: {}, version: '?', llm_model: '?' } as Health
    throw e
  }),

  conversations: () => request<Conversation[]>('/conversations'),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, json('PATCH', { title })),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
  feedback: (messageId: string, value: 1 | -1 | 0) =>
    request<Message>(`/messages/${messageId}/feedback`, json('POST', { value })),

  documents: () => request<DocumentInfo[]>('/documents'),
  uploadDocuments: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<UploadResult>('/documents', { method: 'POST', body: form })
  },
  addUrl: (url: string) => request<UploadResult>('/documents/url', json('POST', { url })),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  kbStats: () => request<KnowledgeBaseStats>('/knowledge-base/stats'),
  resetKnowledgeBase: () => request<void>('/knowledge-base', { method: 'DELETE' }),

  datasets: () => request<Dataset[]>('/datasets'),
  uploadDataset: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Dataset>('/datasets', { method: 'POST', body: form })
  },
  datasetPreview: (id: string) => request<DatasetPreview>(`/datasets/${id}/preview`),
  deleteDataset: (id: string) => request<void>(`/datasets/${id}`, { method: 'DELETE' }),
}

/** Parse a text/event-stream body into events. Exported for tests. */
export function parseSSE(buffer: string): { events: ChatEvent[]; rest: string } {
  const events: ChatEvent[] = []
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    const data = block
      .split('\n')
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.slice(5).trimStart())
      .join('\n')
    if (data) events.push(JSON.parse(data) as ChatEvent)
  }
  return { events, rest }
}

/** POST /chat/stream and invoke `onEvent` for each server-sent event. */
export async function streamChat(
  body: ChatRequest,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw await toError(res)

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const { events, rest } = parseSSE(buffer)
    buffer = rest
    events.forEach(onEvent)
  }
  if (buffer.trim()) parseSSE(buffer + '\n\n').events.forEach(onEvent)
}
