import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, Library, Menu, MessageSquare, Pencil, Plus, Settings, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type { Conversation } from '@/lib/types'
import { cn, timeAgo } from '@/lib/utils'

const NAV = [
  { to: '/knowledge', label: 'Knowledge base', icon: Library },
  { to: '/datasets', label: 'Datasets', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Layout() {
  // The mobile drawer is tied to the path it was opened on, so navigating closes it.
  const location = useLocation()
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === location.pathname
  const setOpen = (v: boolean) => setOpenOn(v ? location.pathname : null)

  return (
    <div className="flex h-full">
      {open && <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={() => setOpen(false)} />}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-line bg-panel transition-transform md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <Sidebar onClose={() => setOpen(false)} />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 border-b border-line px-3 md:hidden">
          <button type="button" onClick={() => setOpen(true)} aria-label="Open menu" className="grid size-8 place-items-center rounded-md hover:bg-sunken">
            <Menu className="size-4" />
          </button>
          <span className="text-sm font-semibold">Agentic RAG</span>
        </header>
        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function Sidebar({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })

  return (
    <>
      <div className="flex h-14 items-center gap-2.5 px-4">
        <img src="/favicon.svg" alt="" className="size-6" />
        <span className="text-[15px] font-semibold tracking-tight">Agentic RAG</span>
        <button type="button" onClick={onClose} aria-label="Close menu" className="ml-auto grid size-7 place-items-center rounded-md hover:bg-sunken md:hidden">
          <X className="size-4" />
        </button>
      </div>
      <div className="px-3">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex h-9 w-full items-center gap-2 rounded-lg border border-line bg-panel px-3 text-sm font-medium shadow-sm hover:bg-sunken cursor-pointer"
        >
          <Plus className="size-4" /> New chat
          <kbd className="ml-auto hidden rounded border border-line px-1 text-[10px] text-faint sm:block">⌘K</kbd>
        </button>
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-2">
        <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-faint">History</p>
        {conversations.data?.length === 0 && <p className="px-2 py-2 text-[12.5px] text-muted">No conversations yet.</p>}
        <ul className="space-y-px">
          {conversations.data?.map((c) => (
            <ConversationItem key={c.id} c={c} />
          ))}
        </ul>
      </div>

      <nav className="border-t border-line p-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] transition-colors',
                isActive ? 'bg-sunken font-medium text-ink' : 'text-muted hover:bg-sunken hover:text-ink',
              )
            }
          >
            <Icon className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  )
}

function ConversationItem({ c }: { c: Conversation }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(c.title)
  const active = conversationId === c.id

  const rename = useMutation({
    mutationFn: (t: string) => api.renameConversation(c.id, t),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conversations'] }),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteConversation(c.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      if (active) navigate('/')
      toast.success('Conversation deleted')
    },
  })

  if (editing) {
    return (
      <li>
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => {
            setEditing(false)
            if (title.trim() && title !== c.title) rename.mutate(title.trim())
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
            if (e.key === 'Escape') {
              setTitle(c.title)
              setEditing(false)
            }
          }}
          className="h-8 w-full rounded-md border border-accent bg-panel px-2 text-[13px]"
          aria-label="Conversation title"
        />
      </li>
    )
  }

  return (
    <li className="group relative">
      <NavLink
        to={`/c/${c.id}`}
        className={cn(
          'flex h-8 items-center gap-2 rounded-md px-2 pr-14 text-[13px] transition-colors',
          active ? 'bg-sunken text-ink' : 'text-muted hover:bg-sunken/70 hover:text-ink',
        )}
        title={`${c.title} · ${timeAgo(c.updated_at)}`}
      >
        <MessageSquare className="size-3.5 shrink-0 opacity-60" />
        <span className="truncate">{c.title}</span>
      </NavLink>
      <div className="absolute inset-y-0 right-1 hidden items-center gap-0.5 group-hover:flex group-focus-within:flex">
        <button type="button" aria-label="Rename" onClick={() => setEditing(true)} className="grid size-6 place-items-center rounded text-muted hover:bg-panel hover:text-ink cursor-pointer">
          <Pencil className="size-3" />
        </button>
        <button
          type="button"
          aria-label="Delete"
          onClick={() => confirm(`Delete “${c.title}”?`) && remove.mutate()}
          className="grid size-6 place-items-center rounded text-muted hover:bg-panel hover:text-bad cursor-pointer"
        >
          <Trash2 className="size-3" />
        </button>
      </div>
    </li>
  )
}
