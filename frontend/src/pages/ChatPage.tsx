import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AssistantMessage } from '@/components/AssistantMessage'
import { nodesFromTimeline } from '@/lib/agents'
import { Composer, type ChatOptions } from '@/components/Composer'
import { Spinner } from '@/components/ui'
import { useChatStream } from '@/hooks/useChatStream'
import { usePersistentState } from '@/hooks/usePersistentState'
import { api } from '@/lib/api'

const DEFAULT_OPTIONS: ChatOptions = { mode: 'auto', verify: true, top_k: 5, dataset_id: null }

const EXAMPLES: { text: string; mode: ChatOptions['mode']; label: string }[] = [
  { text: 'Summarize the key points of my uploaded documents', mode: 'documents', label: 'docs' },
  { text: 'What changed in open-source language models this month?', mode: 'web', label: 'web' },
  { text: 'Which category has the highest average value?', mode: 'data', label: 'data' },
]

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [options, setOptions] = usePersistentState<ChatOptions>('rag.chatOptions', DEFAULT_OPTIONS)
  const bottomRef = useRef<HTMLDivElement>(null)
  const liveConversation = useRef<string | null>(null)

  const conv = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.conversation(conversationId!),
    enabled: !!conversationId,
  })

  const { turn, send, stop, reset } = useChatStream({
    onStart: (id) => {
      liveConversation.current = id
      if (id !== conversationId) navigate(`/c/${id}`, { replace: true })
    },
    onDone: async (t) => {
      const id = t.conversationId
      if (!id) return
      qc.invalidateQueries({ queryKey: ['conversations'] })
      // Swap the live turn for the persisted messages once the server copy has arrived.
      await qc.refetchQueries({ queryKey: ['conversation', id] })
      if (t.final) reset()
    },
  })

  // Switching to another conversation (or "new chat") discards the live turn.
  useEffect(() => {
    if (conversationId !== liveConversation.current) {
      stop()
      reset()
      liveConversation.current = conversationId ?? null
    }
  }, [conversationId, stop, reset])

  // While a turn is live, its user message is already persisted server-side; render it once.
  const messages = (conversationId ? (conv.data?.messages ?? []) : []).filter(
    (m) => !turn || m.id !== turn.userMessageId,
  )
  const busy = turn?.status === 'streaming'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, turn?.answer, turn?.status])

  const onSend = (text: string) =>
    send({
      message: text,
      conversation_id: conversationId ?? null,
      mode: options.mode,
      top_k: options.top_k,
      verify: options.verify,
      dataset_id: options.mode === 'data' ? options.dataset_id : null,
    })

  const empty = !conversationId && !turn

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 pt-8 pb-6">
          {empty && (
            <div className="pt-[12vh]">
              <h1 className="max-w-xl text-3xl font-medium">Ask your documents, the web or a spreadsheet</h1>
              <p className="mt-3 max-w-xl text-md text-muted">
                Answers cite the passages they come from, and a second model checks every claim against
                them before you read it.
              </p>
              <ul className="mt-10 divide-y divide-line border-y border-line">
                {EXAMPLES.map((e) => (
                  <li key={e.text}>
                    <button
                      type="button"
                      onClick={() => {
                        setOptions({ ...options, mode: e.mode })
                        send({ ...options, mode: e.mode, message: e.text, conversation_id: null })
                      }}
                      className="group flex w-full items-center gap-3 py-3 text-left text-base text-muted transition-colors hover:text-ink cursor-pointer"
                    >
                      <span className="flex-1">{e.text}</span>
                      <span className="font-mono text-xs text-faint">{e.label}</span>
                      <ArrowUpRight className="size-4 text-faint transition-colors group-hover:text-accent" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {conversationId && conv.isLoading && !turn && (
            <div className="grid place-items-center py-20">
              <Spinner />
            </div>
          )}
          {conv.isError && !turn && (
            <p className="py-20 text-center text-sm text-muted">This conversation could not be loaded.</p>
          )}

          <div className="space-y-8">
            {messages.map((m) =>
              m.role === 'user' ? (
                <UserBubble key={m.id} text={m.content} />
              ) : (
                <AssistantMessage
                  key={m.id}
                  content={m.content}
                  sources={m.sources}
                  meta={m.meta}
                  nodes={nodesFromTimeline(m.meta)}
                  message={m}
                />
              ),
            )}
            {turn && (
              <>
                <UserBubble text={turn.question} />
                <AssistantMessage
                  content={turn.answer}
                  sources={turn.final?.sources ?? []}
                  meta={turn.final?.meta}
                  nodes={turn.nodes}
                  logs={turn.logs}
                  code={turn.code}
                  streaming={turn.status === 'streaming'}
                  error={turn.error}
                  message={turn.final}
                />
              </>
            )}
          </div>
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="border-t border-line/60 bg-bg/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl px-4 py-3">
          <Composer options={options} onOptions={setOptions} onSend={onSend} onStop={stop} busy={busy} autoFocus />
          <p className="mt-2 text-center text-xs text-faint">Answers are generated by an LLM and can be wrong. Check the cited sources.</p>
        </div>
      </div>
    </div>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-sunken px-4 py-2.5 text-md">{text}</div>
    </div>
  )
}
