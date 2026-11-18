import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'
import { formatTime } from '../lib/format'

type Props = {
  side: 'start' | 'end'
  x: number // left edge in px (already kept inside the track)
  bad: boolean
  time: number
  onPointerDown: (e: ReactPointerEvent) => void
  onKeyDown: (e: ReactKeyboardEvent) => void
}

export function TrimHandle({ side, x, bad, time, onPointerDown, onKeyDown }: Props) {
  const isStart = side === 'start'
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label={isStart ? 'Início do corte' : 'Fim do corte'}
      aria-valuetext={formatTime(time)}
      aria-valuenow={time}
      title={`${isStart ? 'Início' : 'Fim'} ${formatTime(time)} · setas: ±0,1 s, Shift+setas: ±1 s`}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      className={`absolute inset-y-0 flex w-3.5 cursor-ew-resize items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${
        bad ? 'bg-orange-400' : 'bg-amber-300'
      } ${isStart ? 'rounded-l-md' : 'rounded-r-md'}`}
      style={{ left: x }}
    >
      <span className="h-5 w-0.5 rounded bg-black/60" />
    </div>
  )
}
