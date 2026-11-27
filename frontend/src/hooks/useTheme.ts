import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'

function apply(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('rag.theme') as Theme) || 'system')

  useEffect(() => {
    localStorage.setItem('rag.theme', theme)
    apply(theme)
    if (theme !== 'system') return
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => apply('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  return [theme, setTheme] as const
}
