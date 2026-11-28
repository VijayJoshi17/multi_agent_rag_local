import { Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { memo, useMemo } from 'react'
import { NODE_META, type NodeState } from '@/lib/agents'
import type { NodeName } from '@/lib/types'
import { cn, formatMs } from '@/lib/utils'

const POSITIONS: Record<NodeName, { x: number; y: number }> = {
  contextualize: { x: 0, y: 70 },
  router: { x: 170, y: 70 },
  retrieve: { x: 340, y: 0 },
  web_search: { x: 340, y: 70 },
  data_analyst: { x: 340, y: 140 },
  reason: { x: 510, y: 70 },
  verify: { x: 680, y: 70 },
}

const EDGES: [NodeName, NodeName][] = [
  ['contextualize', 'router'],
  ['router', 'retrieve'],
  ['router', 'web_search'],
  ['router', 'data_analyst'],
  ['retrieve', 'web_search'],
  ['retrieve', 'reason'],
  ['web_search', 'reason'],
  ['data_analyst', 'reason'],
  ['reason', 'verify'],
]

type AgentNodeData = { name: NodeName; state: NodeState }

const AgentNode = memo(function AgentNode({ data }: NodeProps<Node<AgentNodeData>>) {
  const { label, icon: Icon } = NODE_META[data.name]
  const { status, duration_ms, runs } = data.state
  return (
    <div
      className={cn(
        'flex w-[150px] items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm transition-colors duration-300 ease-out',
        status === 'idle' && 'border-line bg-panel text-faint',
        status === 'active' && 'border-accent bg-accent-soft text-accent-ink',
        status === 'done' && 'border-ok/40 bg-ok-soft text-ink',
      )}
      title={data.state.summary ?? undefined}
    >
      <Handle type="target" position={Position.Left} />
      <Icon className={cn('size-3.5 shrink-0', status === 'done' && 'text-ok', status === 'active' && 'text-accent')} />
      <div className="min-w-0 leading-tight">
        <div className="truncate font-medium">{label}</div>
        <div className="text-xs text-muted tabular-nums h-3.5">
          {status === 'active' ? 'running…' : duration_ms != null ? formatMs(duration_ms) + (runs && runs > 1 ? ` · ×${runs}` : '') : ''}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
})

const nodeTypes = { agent: AgentNode }

export function AgentGraph({ states, className }: { states: Partial<Record<NodeName, NodeState>>; className?: string }) {
  const nodes = useMemo<Node<AgentNodeData>[]>(
    () =>
      (Object.keys(POSITIONS) as NodeName[]).map((name) => ({
        id: name,
        type: 'agent',
        position: POSITIONS[name],
        data: { name, state: states[name] ?? { status: 'idle' } },
        draggable: false,
        selectable: false,
      })),
    [states],
  )
  const edges = useMemo<Edge[]>(
    () =>
      EDGES.map(([a, b]) => {
        const sa = states[a]?.status
        const sb = states[b]?.status
        const cls = sa === 'done' && sb === 'active' ? 'active' : sa === 'done' && sb === 'done' ? 'done' : ''
        return { id: `${a}-${b}`, source: a, target: b, className: cls, animated: cls === 'active' }
      }),
    [states],
  )

  return (
    <div className={cn('h-[200px] w-full', className)} aria-label="Agent execution graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        nodesConnectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
      />
    </div>
  )
}
