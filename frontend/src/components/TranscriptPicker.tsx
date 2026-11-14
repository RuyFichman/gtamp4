import { useEffect, useRef } from 'react'
import { formatTime } from '../lib/format'
import type { Segment } from '../lib/types'

const CONTEXT_S = 60 // how much speech to show around the clip

type Props = {
  segments: Segment[]
  start: number
  end: number
  onSeek: (t: number) => void
  onStart: (t: number) => void
  onEnd: (t: number) => void
}

export function TranscriptPicker({ segments, start, end, onSeek, onStart, onEnd }: Props) {
  const firstInside = useRef<HTMLLIElement>(null)
  const shown = segments.filter((s) => s.end >= start - CONTEXT_S && s.start <= end + CONTEXT_S)

  const list = useRef<HTMLUListElement>(null)

  // scroll only the list (scrollIntoView would also move the modal/page)
  useEffect(() => {
    const ul = list.current
    const li = firstInside.current
    if (ul && li) ul.scrollTop = li.offsetTop - 8 // ul is `relative`: offsetTop is inside it
  }, [])

  if (shown.length === 0) {
    return <p className="text-sm text-zinc-500">Sem transcrição para esse trecho.</p>
  }

  const isInside = (seg: Segment) => seg.end > start && seg.start < end
  const firstIndex = shown.findIndex(isInside)
  return (
    <ul
      ref={list}
      className="relative max-h-72 space-y-0.5 overflow-y-auto rounded border border-white/10 bg-black/20 p-1 text-sm">
      {shown.map((seg, i) => {
        const inside = isInside(seg)
        const ref = i === firstIndex ? firstInside : undefined
        return (
          <li
            key={seg.start}
            ref={ref}
            className={`group flex items-start gap-2 rounded px-2 py-1 ${
              inside ? 'bg-pink-500/15' : 'opacity-60'
            }`}
          >
            <button
              type="button"
              onClick={() => onSeek(seg.start)}
              className="shrink-0 font-mono text-xs text-cyan-300 hover:underline"
            >
              {formatTime(seg.start)}
            </button>
            <span className="flex-1">{seg.text}</span>
            <span className="flex shrink-0 gap-1 opacity-0 transition group-hover:opacity-100">
              <button
                type="button"
                onClick={() => onStart(seg.start)}
                className="rounded border border-white/20 px-1.5 text-xs hover:bg-white/10"
              >
                início
              </button>
              <button
                type="button"
                onClick={() => onEnd(seg.end)}
                className="rounded border border-white/20 px-1.5 text-xs hover:bg-white/10"
              >
                fim
              </button>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
