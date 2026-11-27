import { useQueryClient } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiKey, onUnauthorized } from '@/lib/api'
import { Button } from './ui'

/** Shown automatically whenever the API answers 401. */
export function ApiKeyDialog() {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const qc = useQueryClient()

  useEffect(() => onUnauthorized(() => setOpen(true)), [])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm" role="dialog" aria-modal aria-labelledby="key-title">
      <form
        className="w-full max-w-sm rounded-2xl border border-line bg-panel p-6 shadow-xl"
        onSubmit={(e) => {
          e.preventDefault()
          apiKey.set(value.trim())
          setOpen(false)
          qc.invalidateQueries()
        }}
      >
        <div className="mb-4 grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
          <KeyRound className="size-5" />
        </div>
        <h2 id="key-title" className="text-base font-semibold">
          API key required
        </h2>
        <p className="mt-1 text-[13px] text-muted">
          This server is protected. Enter the <code className="rounded bg-sunken px-1">API_KEY</code> from its <code className="rounded bg-sunken px-1">.env</code>.
        </p>
        <input
          autoFocus
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-4 h-10 w-full rounded-lg border border-line bg-panel px-3 text-sm"
          placeholder="API key"
          aria-label="API key"
        />
        <Button type="submit" variant="primary" className="mt-4 w-full justify-center" disabled={!value.trim()}>
          Continue
        </Button>
      </form>
    </div>
  )
}
