import { describe, expect, it } from 'vitest'
import { reduceTurn, type LiveTurn } from '@/hooks/useChatStream'
import { parseSSE } from './api'
import { formatBytes, linkCitations } from './utils'

describe('parseSSE', () => {
  it('parses complete events and keeps the partial remainder', () => {
    const buf = 'event: token\ndata: {"type":"token","text":"Hi"}\n\nevent: token\ndata: {"type":"tok'
    const { events, rest } = parseSSE(buf)
    expect(events).toEqual([{ type: 'token', text: 'Hi' }])
    expect(rest).toBe('event: token\ndata: {"type":"tok')
  })

  it('handles CRLF line endings', () => {
    const { events } = parseSSE('data: {"type":"answer_reset","reason":"x"}\r\n\r\n')
    expect(events[0].type).toBe('answer_reset')
  })
})

describe('linkCitations', () => {
  it('links in-range citation markers only', () => {
    expect(linkCitations('Paris [1][2]. See [9].', 2)).toBe('Paris [1](#cite-1)[2](#cite-2). See [9].')
  })
  it('leaves code untouched', () => {
    expect(linkCitations('`arr[1]` and [1]', 1)).toBe('`arr[1]` and [1](#cite-1)')
  })
  it('leaves existing markdown links untouched', () => {
    expect(linkCitations('[1](http://x)', 1)).toBe('[1](http://x)')
  })
})

describe('reduceTurn', () => {
  const base: LiveTurn = { question: 'q', nodes: {}, logs: [], code: [], answer: '', status: 'streaming', startedAt: 0 }

  it('tracks node lifecycle, tokens and regeneration', () => {
    let t = reduceTurn(base, { type: 'node_start', node: 'reason' })
    expect(t.nodes.reason?.status).toBe('active')
    t = reduceTurn(t, { type: 'token', text: 'Hello ' })
    t = reduceTurn(t, { type: 'token', text: 'world' })
    expect(t.answer).toBe('Hello world')
    t = reduceTurn(t, { type: 'node_end', node: 'reason', duration_ms: 100, summary: null })
    t = reduceTurn(t, { type: 'answer_reset', reason: 'verification_failed' })
    expect(t.answer).toBe('')
    t = reduceTurn(t, { type: 'node_end', node: 'reason', duration_ms: 50, summary: null })
    expect(t.nodes.reason).toMatchObject({ status: 'done', runs: 2, duration_ms: 150 })
  })

  it('captures errors', () => {
    const t = reduceTurn(base, { type: 'error', code: 'x', message: 'boom' })
    expect(t).toMatchObject({ status: 'error', error: 'boom' })
  })
})

describe('formatBytes', () => {
  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(25 * 1024 * 1024)).toBe('25 MB')
  })
})
