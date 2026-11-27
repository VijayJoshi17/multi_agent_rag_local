import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, FileSearch, Globe, ShieldCheck } from 'lucide-react'
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

const SUGGESTIONS = [
  { icon: FileSearch, title: 'Ask your documents', text: 'Summarize the key points of my uploaded documents' },
  { icon: Globe, title: 'Search the web', text: "What's the latest news about open-source LLMs?" },
  { icon: BarChart3, title: 'Analyze data', text: 'Which category has the highest average value?', mode: 'data' as const },
  { icon: ShieldCheck, title: 'Fact-checked answers', text: 'What is the capital of France and when was the Eiffel Tower built?' },
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
            <div className="pt-[8vh]">
              <h1 className="text-center text-2xl font-semibold tracking-tight">What do you want to know?</h1>
              <p className="mt-2 text-center text-sm text-muted">
                A team of agents retrieves, searches, analyzes and fact-checks before answering.
              </p>
              <div className="mt-8 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.title}
                    type="button"
                    onClick={() => {
                      if (s.mode) setOptions({ ...options, mode: s.mode })
                      send({ ...options, mode: s.mode ?? options.mode, message: s.text, conversation_id: null })
                    }}
                    className="group rounded-xl border border-line bg-panel p-3.5 text-left transition-colors hover:border-accent/40 hover:bg-accent-soft/40 cursor-pointer"
                  >
                    <div className="flex items-center gap-2 text-[13px] font-medium">
                      <s.icon className="size-4 text-accent" />
                      {s.title}
                    </div>
                    <p className="mt-1 text-[12.5px] text-muted">{s.text}</p>
                  </button>
                ))}
              </div>
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
          <p className="mt-2 text-center text-[11px] text-faint">Answers are generated by an LLM and can be wrong. Check the cited sources.</p>
        </div>
      </div>
    </div>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-sunken px-4 py-2.5 text-[14.5px]">{text}</div>
    </div>
  )
}
