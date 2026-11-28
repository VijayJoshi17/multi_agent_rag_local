import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { cn, linkCitations } from '@/lib/utils'

export function Markdown({
  content,
  sourceCount = 0,
  onCite,
  className,
}: {
  content: string
  sourceCount?: number
  onCite?: (n: number) => void
  className?: string
}) {
  return (
    <div className={cn('answer', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('#cite-')) {
              const n = Number(href.slice(6))
              return (
                <sup>
                  <button
                    type="button"
                    onClick={() => onCite?.(n)}
                    // <sup> has line-height 0; inline-block + padding keeps a clickable target
                    className="-mx-0.5 inline-block rounded px-1 py-0.5 font-mono text-[0.68em] leading-none text-accent-ink underline-offset-2 hover:bg-accent-soft hover:underline cursor-pointer"
                    aria-label={`Source ${n}`}
                  >
                    {n}
                  </button>
                </sup>
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            )
          },
        }}
      >
        {linkCitations(content, sourceCount)}
      </ReactMarkdown>
    </div>
  )
}
