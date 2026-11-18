import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { formatTime } from '../lib/format'
import {
  DEFAULT_PAD_INDEX,
  PADS,
  type View,
  clamp,
  needsRecentre,
  round1,
  snap,
  tickStep,
  viewAround,
} from '../lib/timeline'
import type { Segment } from '../lib/types'
import { Filmstrip } from './Filmstrip'
import { TrimHandle } from './TrimHandle'

type Props = {
  start: number
  end: number
  duration: number | null
  segments: Segment[]
  videoUrl: string | null
  /** player time, read every frame for the playhead */
  currentTime: () => number
  minS: number
  maxS: number
  onChange: (start: number, end: number) => void
  onSeek: (t: number) => void
  /** show the frame at t while dragging (pauses the player) */
  onScrub: (t: number) => void
}

type Drag = {
  mode: 'start' | 'end' | 'move' | 'seek'
  pointerX: number
  start: number
  end: number
  view: View
}

const TRACK_H = 56
const HANDLE_W = 14
const SNAP_PX = 8
const MIN_LEN = 1 // the handles never cross; the real limits are shown as an error
const ZOOM_BTN =
  'rounded border border-white/15 bg-white/5 px-2 py-0.5 text-xs hover:border-white/25 hover:bg-white/10 disabled:opacity-40'

/** CapCut-style trim bar: drag the edges or the whole clip, scrub the player while dragging. */
export function TrimTimeline(props: Props) {
  const { start, end, segments, videoUrl, currentTime, minS, maxS, onChange, onSeek, onScrub } =
    props
  const duration = props.duration ?? Math.max(end + 60, 1)
  const track = useRef<HTMLDivElement>(null)
  const playhead = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [padIndex, setPadIndex] = useState(DEFAULT_PAD_INDEX)
  // the window is centred on where the clip was when last re-centred (zoom, or an edge that
  // left it); it never moves mid-drag, so the handle stays under the mouse
  const [anchor, setAnchor] = useState({ start, end })
  const [drag, setDrag] = useState<Drag | null>(null)
  const [snapAt, setSnapAt] = useState<number | null>(null)

  let view = viewAround(anchor.start, anchor.end, PADS[padIndex], duration)
  if (!drag && needsRecentre(view, start, end, duration)) {
    setAnchor({ start, end }) // render-time update: React re-renders before painting
    view = viewAround(start, end, PADS[padIndex], duration)
  }

  const edges = useMemo(() => segments.flatMap((s) => [s.start, s.end]), [segments])
  const span = view.to - view.from
  const toX = (t: number) => ((t - view.from) / span) * width
  const secondsPerPx = width > 0 ? span / width : 0

  useEffect(() => {
    const el = track.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // playhead follows the player every frame without re-rendering React
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const el = playhead.current
      if (el && width > 0) {
        const t = currentTime()
        const inside = t >= view.from && t <= view.to
        el.style.display = inside ? 'block' : 'none'
        el.style.transform = `translateX(${((t - view.from) / span) * width}px)`
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [currentTime, view.from, view.to, span, width])

  function zoom(dir: 1 | -1) {
    setPadIndex((i) => clamp(i + dir, 0, PADS.length - 1))
    setAnchor({ start, end })
  }

  function timeAt(clientX: number, v: View = view): number {
    const rect = track.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return v.from
    return v.from + ((clientX - rect.left) / rect.width) * (v.to - v.from)
  }

  function snapped(t: number, free: boolean): number {
    if (free) {
      setSnapAt(null)
      return round1(t)
    }
    const r = snap(t, edges, SNAP_PX * secondsPerPx)
    setSnapAt(r.snapped ? r.t : null)
    return r.snapped ? r.t : round1(t)
  }

  function begin(mode: Drag['mode'], e: ReactPointerEvent) {
    if (e.button !== 0) return
    e.preventDefault()
    e.stopPropagation()
    track.current?.setPointerCapture(e.pointerId)
    setDrag({ mode, pointerX: e.clientX, start, end, view })
    if (mode === 'seek') {
      const t = clamp(timeAt(e.clientX), 0, duration)
      onSeek(t)
    }
  }

  function move(e: ReactPointerEvent) {
    if (!drag) return
    const t = clamp(timeAt(e.clientX, drag.view), 0, duration)
    const free = e.shiftKey
    if (drag.mode === 'seek') {
      onScrub(t)
    } else if (drag.mode === 'start') {
      const s = Math.min(snapped(t, free), end - MIN_LEN)
      onChange(Math.max(0, s), end)
      onScrub(s)
    } else if (drag.mode === 'end') {
      const en = Math.max(snapped(t, free), start + MIN_LEN)
      onChange(start, Math.min(duration, en))
      onScrub(en)
    } else {
      const len = drag.end - drag.start
      const dt = (e.clientX - drag.pointerX) * ((drag.view.to - drag.view.from) / (width || 1))
      const s = round1(clamp(drag.start + dt, 0, duration - len))
      onChange(s, round1(s + len))
      onScrub(s)
    }
  }

  function finish(e: ReactPointerEvent) {
    if (!drag) return
    track.current?.releasePointerCapture(e.pointerId)
    setDrag(null)
    setSnapAt(null)
  }

  function nudge(edge: 'start' | 'end', e: ReactKeyboardEvent) {
    const step = e.shiftKey ? 1 : 0.1
    const dir = e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0
    if (!dir) return
    e.preventDefault()
    if (edge === 'start') {
      const s = round1(clamp(start + dir * step, 0, end - MIN_LEN))
      onChange(s, end)
      onScrub(s)
    } else {
      const en = round1(clamp(end + dir * step, start + MIN_LEN, duration))
      onChange(start, en)
      onScrub(en)
    }
  }

  const length = end - start
  const bad = length < minS || length > maxS
  const left = toX(start)
  const right = toX(end)
  const step = tickStep(span)
  const ticks: number[] = []
  for (let t = Math.ceil(view.from / step) * step; t <= view.to; t += step) ticks.push(t)
  const thumbCount = Math.max(1, Math.round(width / ((TRACK_H * 16) / 9)))
  const visibleEdges = segments.filter((s) => s.start >= view.from && s.start <= view.to)

  return (
    <div className="space-y-1 select-none">
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <span>Arraste as pontas ou o meio do trecho · Shift solta o ímã das frases</span>
        <span className="ml-auto">Zoom</span>
        <button
          type="button"
          className={ZOOM_BTN}
          disabled={padIndex === PADS.length - 1}
          onClick={() => zoom(1)}
          aria-label="Afastar"
        >
          −
        </button>
        <button
          type="button"
          className={ZOOM_BTN}
          disabled={padIndex === 0}
          onClick={() => zoom(-1)}
          aria-label="Aproximar"
        >
          +
        </button>
      </div>

      {/* ruler */}
      <div className="relative h-4 text-[10px] text-zinc-500">
        {width > 0 &&
          ticks.map((t) => (
            <span
              key={t}
              className="absolute -translate-x-1/2 font-mono"
              style={{ left: toX(t) }}
            >
              {formatTime(t).replace(/\.0$/, '')}
            </span>
          ))}
      </div>

      <div
        ref={track}
        onPointerDown={(e) => begin('seek', e)}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={finish}
        className="relative cursor-pointer overflow-hidden rounded-md bg-black/40"
        style={{ height: TRACK_H, touchAction: 'none' }}
      >
        {videoUrl && width > 0 && (
          <Filmstrip
            videoUrl={videoUrl}
            from={view.from}
            to={view.to}
            count={thumbCount}
            height={TRACK_H}
          />
        )}

        {/* sentence starts from the transcript (what the magnet snaps to) */}
        {width > 0 &&
          visibleEdges.map((s) => (
            <div
              key={s.start}
              title={s.text}
              className="pointer-events-none absolute bottom-0 h-2 w-px bg-cyan-300/70"
              style={{ left: toX(s.start) }}
            />
          ))}

        {width > 0 && (
          <>
            {/* everything outside the clip is dimmed */}
            <div
              className="pointer-events-none absolute inset-y-0 left-0 bg-black/65"
              style={{ width: Math.max(0, left) }}
            />
            <div
              className="pointer-events-none absolute inset-y-0 right-0 bg-black/65"
              style={{ width: Math.max(0, width - right) }}
            />

            {/* the clip: drag the middle to move it, the handles to trim */}
            <div
              onPointerDown={(e) => begin('move', e)}
              className={`absolute inset-y-0 cursor-grab border-y-[3px] active:cursor-grabbing ${
                bad ? 'border-orange-400' : 'border-amber-300'
              }`}
              style={{ left, width: Math.max(0, right - left) }}
            >
              <span className="pointer-events-none absolute top-0.5 left-1/2 -translate-x-1/2 rounded bg-black/70 px-1.5 font-mono text-[11px] text-white">
                {length.toFixed(1)} s
              </span>
            </div>
            <TrimHandle
              side="start"
              x={Math.max(0, left - HANDLE_W)}
              bad={bad}
              time={start}
              onPointerDown={(e) => begin('start', e)}
              onKeyDown={(e) => nudge('start', e)}
            />
            <TrimHandle
              side="end"
              x={Math.min(width - HANDLE_W, right)}
              bad={bad}
              time={end}
              onPointerDown={(e) => begin('end', e)}
              onKeyDown={(e) => nudge('end', e)}
            />

            {snapAt != null && (
              <div
                className="pointer-events-none absolute inset-y-0 w-0.5 bg-cyan-300"
                style={{ left: toX(snapAt) }}
              />
            )}
          </>
        )}

        <div
          ref={playhead}
          className="pointer-events-none absolute inset-y-0 left-0 w-0.5 bg-white shadow-[0_0_4px_rgba(0,0,0,0.8)]"
        />
      </div>

      {drag && drag.mode !== 'seek' && (
        <p className="text-center font-mono text-xs text-zinc-300">
          {formatTime(start)} → {formatTime(end)}
        </p>
      )}
    </div>
  )
}
