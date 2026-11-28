// Mirrors backend/app/schemas/api.py

export type ChatMode = 'auto' | 'documents' | 'web' | 'data'
export type SourceKind = 'document' | 'web' | 'tool' | 'analysis' | 'system'
export type NodeName =
  | 'contextualize'
  | 'router'
  | 'retrieve'
  | 'web_search'
  | 'data_analyst'
  | 'reason'
  | 'verify'

export interface ChatRequest {
  message: string
  conversation_id?: string | null
  mode: ChatMode
  top_k: number
  verify: boolean
  dataset_id?: string | null
  document_ids?: string[] | null
}

export interface Source {
  text: string
  source: string
  kind: SourceKind
  document_id?: string | null
  page?: number | null
  url?: string | null
  score?: number | null
}

export interface Verification {
  verdict: 'supported' | 'unsupported' | 'skipped'
  reason: string
}

export interface TimelineEntry {
  node: NodeName
  duration_ms: number
  summary: string | null
}

export interface AnalysisTable {
  columns: string[]
  rows: (string | number | boolean | null)[][]
}

export interface MessageMeta {
  trace_id?: string
  route?: 'retrieve' | 'web_search' | 'data_analyst'
  query?: string
  attempts?: number
  verification?: Verification
  timeline?: TimelineEntry[]
  duration_ms?: number
  analysis?: {
    code: string
    ok: boolean
    output: string
    error: string | null
    dataset_id: string
    table?: AnalysisTable | null
  }
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: Source[]
  meta: MessageMeta
  feedback: number | null
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface DocumentInfo {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  chunk_count: number
  error: string | null
  created_at: string
  updated_at: string
}

export interface UploadResult {
  documents: DocumentInfo[]
  skipped: string[]
}

export interface Dataset {
  id: string
  filename: string
  size_bytes: number
  row_count: number
  columns: { name: string; dtype: string }[]
  created_at: string
}

export interface DatasetPreview {
  columns: string[]
  rows: unknown[][]
}

export interface KnowledgeBaseStats {
  documents: number
  chunks: number
}

export interface Health {
  status: 'ok' | 'degraded'
  checks: Record<string, boolean>
  version: string
  llm_model: string
}

// ---- Streaming events (text/event-stream from POST /chat/stream) ----
export type ChatEvent =
  | { type: 'start'; trace_id: string; conversation_id: string; user_message_id: string }
  | { type: 'node_start'; node: NodeName }
  | { type: 'node_end'; node: NodeName; duration_ms: number; summary: string | null }
  | { type: 'log'; node: NodeName; message: string }
  | { type: 'code'; node: NodeName; code: string; attempt: number }
  | { type: 'token'; text: string }
  | { type: 'answer_reset'; reason: string }
  | { type: 'final'; message: Message }
  | { type: 'error'; code: string; message: string; trace_id?: string }
