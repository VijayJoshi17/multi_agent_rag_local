import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '@/lib/api'
import type { NodeState } from '@/lib/agents'
import type { ChatEvent, ChatRequest, Message, NodeName } from '@/lib/types'

export interface LogLine {
  node: NodeName
  message: string
  at: number
}

export interface LiveTurn {
  question: string
  conversationId?: string
  userMessageId?: string
  nodes: Partial<Record<NodeName, NodeState>>
  logs: LogLine[]
  code: { code: string; attempt: number }[]
  answer: string
  status: 'streaming' | 'done' | 'error'
  error?: string
  final?: Message
  startedAt: number
}

export function reduceTurn(turn: LiveTurn, e: ChatEvent): LiveTurn {
  switch (e.type) {
    case 'start':
      return { ...turn, conversationId: e.conversation_id, userMessageId: e.user_message_id }
    case 'node_start': {
      const prev = turn.nodes[e.node]
      return { ...turn, nodes: { ...turn.nodes, [e.node]: { ...prev, status: 'active' } } }
    }
    case 'node_end': {
      const prev = turn.nodes[e.node]
      const runs = (prev?.runs ?? 0) + 1
      const duration_ms = (prev?.duration_ms ?? 0) + e.duration_ms
      return {
        ...turn,
        nodes: { ...turn.nodes, [e.node]: { status: 'done', duration_ms, summary: e.summary, runs } },
      }
    }
    case 'log':
      return { ...turn, logs: [...turn.logs, { node: e.node, message: e.message, at: Date.now() - turn.startedAt }] }
    case 'code':
      return { ...turn, code: [...turn.code, { code: e.code, attempt: e.attempt }] }
    case 'token':
      return { ...turn, answer: turn.answer + e.text }
    case 'answer_reset':
      return { ...turn, answer: '' }
    case 'final':
      return { ...turn, status: 'done', final: e.message, answer: e.message.content }
    case 'error':
      return { ...turn, status: 'error', error: e.message }
  }
}

export function useChatStream(opts: { onStart?: (conversationId: string) => void; onDone?: (turn: LiveTurn) => void }) {
  const [turn, setTurn] = useState<LiveTurn | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const optsRef = useRef(opts)
  useEffect(() => {
    optsRef.current = opts
  })

  const send = useCallback(async (req: ChatRequest) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let current: LiveTurn = {
      question: req.message,
      nodes: {},
      logs: [],
      code: [],
      answer: '',
      status: 'streaming',
      startedAt: Date.now(),
    }
    setTurn(current)
    try {
      await streamChat(
        req,
        (e) => {
          current = reduceTurn(current, e)
          setTurn(current)
          if (e.type === 'start') optsRef.current.onStart?.(e.conversation_id)
        },
        ctrl.signal,
      )
      if (current.status === 'streaming') {
        current = { ...current, status: 'error', error: 'The connection closed before the answer finished.' }
        setTurn(current)
      }
    } catch (err) {
      if (ctrl.signal.aborted) {
        current = { ...current, status: 'error', error: 'Stopped.' }
      } else {
        current = { ...current, status: 'error', error: err instanceof Error ? err.message : String(err) }
      }
      setTurn(current)
    } finally {
      optsRef.current.onDone?.(current)
    }
  }, [])

  const stop = useCallback(() => abortRef.current?.abort(), [])
  const reset = useCallback(() => setTurn(null), [])

  return { turn, send, stop, reset }
}
