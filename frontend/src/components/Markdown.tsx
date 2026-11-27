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
                <button
                  type="button"
                  onClick={() => onCite?.(n)}
                  className="mx-0.5 inline-grid h-[18px] min-w-[18px] place-items-center rounded bg-accent-soft px-1 align-[1px] text-[10.5px] font-semibold text-accent-ink no-underline hover:bg-accent hover:text-white cursor-pointer"
                  aria-label={`Source ${n}`}
                >
                  {n}
                </button>
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
