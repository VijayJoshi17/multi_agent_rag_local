import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, KeyRound, Monitor, Moon, RefreshCw, Sun, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button, Card, PageHeader, Segmented, Spinner } from '@/components/ui'
import { useTheme, type Theme } from '@/hooks/useTheme'
import { api, apiKey } from '@/lib/api'
import { NODE_META } from '@/lib/agents'
import type { NodeName } from '@/lib/types'

const CHECK_LABELS: Record<string, string> = {
  database: 'Database',
  vector_store: 'Vector store (Qdrant)',
  llm: 'LLM provider',
  sandbox: 'Code sandbox',
}

export function SettingsPage() {
  const qc = useQueryClient()
  const [theme, setTheme] = useTheme()
  const [key, setKey] = useState(apiKey.get())
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-5 py-8">
        <PageHeader title="Settings" />

        <section className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-medium">System status</h2>
              <Button size="sm" variant="ghost" onClick={() => health.refetch()} aria-label="Refresh status">
                <RefreshCw className={health.isFetching ? 'size-3.5 animate-spin' : 'size-3.5'} />
              </Button>
            </div>
            {health.isLoading ? (
              <Spinner className="mt-4" />
            ) : health.isError ? (
              <p className="mt-3 text-sm text-bad">Backend unreachable: {health.error.message}</p>
            ) : (
              <>
                <p className="mt-1 text-sm text-muted">
                  Model <code className="rounded bg-sunken px-1">{health.data!.llm_model}</code> · API v{health.data!.version}
                </p>
                <ul className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries(health.data!.checks).map(([k, ok]) => (
                    <li key={k} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                      {ok ? <CheckCircle2 className="size-4 text-ok" /> : <XCircle className="size-4 text-bad" />}
                      {CHECK_LABELS[k] ?? k}
                      <span className={ok ? 'ml-auto text-sm text-ok' : 'ml-auto text-sm text-bad'}>{ok ? 'Healthy' : 'Unavailable'}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="flex items-center gap-2 text-base font-medium">
              <KeyRound className="size-4" /> API key
            </h2>
            <p className="mt-1 text-sm text-muted">Stored in this browser only and sent as the X-API-Key header.</p>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                apiKey.set(key.trim())
                qc.invalidateQueries()
                toast.success(key.trim() ? 'API key saved' : 'API key cleared')
              }}
            >
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Paste your API key"
                autoComplete="off"
                className="h-9 flex-1 rounded-lg border border-line bg-panel px-3 text-sm"
                aria-label="API key"
              />
              <Button type="submit" variant="primary">
                Save
              </Button>
            </form>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-medium">Appearance</h2>
            <div className="mt-3">
              <Segmented<Theme>
                label="Theme"
                value={theme}
                onChange={setTheme}
                options={[
                  { value: 'light', label: 'Light', icon: <Sun className="size-3.5" /> },
                  { value: 'dark', label: 'Dark', icon: <Moon className="size-3.5" /> },
                  { value: 'system', label: 'System', icon: <Monitor className="size-3.5" /> },
                ]}
              />
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-medium">The agent team</h2>
            <ul className="mt-3 divide-y divide-line">
              {(Object.keys(NODE_META) as NodeName[]).map((n) => {
                const { label, icon: Icon, description } = NODE_META[n]
                return (
                  <li key={n} className="flex items-center gap-3 py-2.5 text-sm">
                    <span className="grid size-7 place-items-center rounded-md bg-sunken">
                      <Icon className="size-3.5 text-accent" />
                    </span>
                    <span className="w-36 font-medium">{label}</span>
                    <span className="text-muted">{description}</span>
                  </li>
                )
              })}
            </ul>
          </Card>
        </section>
      </div>
    </div>
  )
}
