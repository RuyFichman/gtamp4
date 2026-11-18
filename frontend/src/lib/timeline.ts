// Pure math for the Studio trim timeline (TrimTimeline / Filmstrip).

export type View = { from: number; to: number }

/** Context shown around the clip on each side, in seconds; the zoom buttons step through it. */
export const PADS = [2, 5, 10, 20, 45, 90]
export const DEFAULT_PAD_INDEX = 2

export const round1 = (t: number) => Math.round(t * 10) / 10

export const clamp = (t: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, t))

export function viewAround(start: number, end: number, pad: number, duration: number): View {
  const from = Math.max(0, start - pad)
  const to = Math.min(duration, end + pad)
  return to - from > 0.5 ? { from, to } : { from: 0, to: Math.max(duration, end, 1) }
}

/** True when an edge got so close to the border (or past it) that the view should follow.
 * A border that is already the video's start/end never asks (re-centring can't help there). */
export function needsRecentre(view: View, start: number, end: number, duration: number): boolean {
  const margin = (view.to - view.from) * 0.04
  return (
    (view.from > 0 && start < view.from + margin) ||
    (view.to < duration && end > view.to - margin)
  )
}

/** Ruler step: about 8 labels across, on round numbers. */
export function tickStep(span: number): number {
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
  return steps.find((s) => span / s <= 10) ?? 600
}

/** Nearest sentence edge within `radius` seconds, or the time itself. */
export function snap(t: number, edges: number[], radius: number): { t: number; snapped: boolean } {
  let best = t
  let dist = radius
  for (const e of edges) {
    const d = Math.abs(e - t)
    if (d < dist) {
      dist = d
      best = e
    }
  }
  return { t: best, snapped: best !== t }
}
