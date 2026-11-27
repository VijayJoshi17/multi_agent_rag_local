import {
  BarChart3,
  Brain,
  Globe,
  type LucideIcon,
  MessageSquareText,
  Search,
  ShieldCheck,
  Signpost,
} from 'lucide-react'
import type { MessageMeta, NodeName } from './types'

export type NodeStatus = 'idle' | 'active' | 'done'

export interface NodeState {
  status: NodeStatus
  duration_ms?: number
  summary?: string | null
  runs?: number
}

export const NODE_META: Record<NodeName, { label: string; icon: LucideIcon; description: string }> = {
  contextualize: { label: 'Contextualize', icon: MessageSquareText, description: 'Rewrites follow-ups into standalone questions' },
  router: { label: 'Router', icon: Signpost, description: 'Chooses documents, web or data analysis' },
  retrieve: { label: 'Hybrid Retrieval', icon: Search, description: 'Dense + BM25 search, fused and reranked' },
  web_search: { label: 'Web Search', icon: Globe, description: 'Live search plus stock quotes' },
  data_analyst: { label: 'Data Analyst', icon: BarChart3, description: 'Writes pandas code, runs it in a sandbox' },
  reason: { label: 'Reasoner', icon: Brain, description: 'Writes a cited, grounded answer' },
  verify: { label: 'Verifier', icon: ShieldCheck, description: 'Fact-checks the answer against sources' },
}

export function nodesFromTimeline(meta: MessageMeta): Partial<Record<NodeName, NodeState>> {
  const out: Partial<Record<NodeName, NodeState>> = {}
  for (const t of meta.timeline ?? []) {
    const prev = out[t.node]
    out[t.node] = {
      status: 'done',
      duration_ms: (prev?.duration_ms ?? 0) + t.duration_ms,
      summary: t.summary,
      runs: (prev?.runs ?? 0) + 1,
    }
  }
  return out
}
