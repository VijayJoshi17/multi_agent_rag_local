import { UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export function Dropzone({
  accept,
  multiple,
  onFiles,
  busy,
  hint,
}: {
  accept: string
  multiple?: boolean
  onFiles: (files: File[]) => void
  busy?: boolean
  hint: string
}) {
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const files = Array.from(e.dataTransfer.files)
        if (files.length) onFiles(multiple ? files : files.slice(0, 1))
      }}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors',
        over ? 'border-accent bg-accent-soft/50' : 'border-line hover:border-accent/50 hover:bg-sunken/60',
        busy && 'pointer-events-none opacity-60',
      )}
    >
      <UploadCloud className={cn('mb-2 size-6', over ? 'text-accent' : 'text-muted')} />
      <p className="text-sm font-medium">{busy ? 'Uploading…' : 'Drop files here or click to browse'}</p>
      <p className="mt-1 text-[12.5px] text-muted">{hint}</p>
      <input
        ref={input}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          if (files.length) onFiles(files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
