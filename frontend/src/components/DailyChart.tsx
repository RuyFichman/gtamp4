import { useEffect, useRef, useState } from 'react'
import { formatDayMonth } from '../lib/format'
import type { DayStat } from '../lib/types'

// validated with the dataviz palette checker on the app's dark surface (#1e1b4b)
const SERIES = [
  { key: 'generated', label: 'Gerados', color: '#db2777' },
  { key: 'posted', label: 'Postados', color: '#0891b2' },
] as const

const H = 200
const PAD = { top: 12, right: 8, bottom: 24, left: 28 }
const PLOT_H = H - PAD.top - PAD.bottom

/** Bar with 4px rounded top, flat on the baseline. */
function barPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0) return ''
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

function niceMax(n: number): number {
  if (n <= 4) return 4
  const step = 10 ** Math.floor(Math.log10(n))
  return Math.ceil(n / step) * step
}

export function DailyChart({ days }: { days: DayStat[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [asTable, setAsTable] = useState(false)
  // draw at the real pixel width so text and bars keep their size (no viewBox stretching)
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(700)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const obs = new ResizeObserver(([entry]) => setW(Math.max(280, entry.contentRect.width)))
    obs.observe(el)
    return () => obs.disconnect()
  }, [asTable])
  const PLOT_W = W - PAD.left - PAD.right
  const max = niceMax(Math.max(...days.map((d) => Math.max(d.generated, d.posted))))
  const slot = PLOT_W / days.length
  const barW = Math.min(14, (slot - 8) / 2)
  const y = (v: number) => PAD.top + PLOT_H - (v / max) * PLOT_H
  const ticks = [0, max / 2, max]
  const empty = days.every((d) => d.generated === 0 && d.posted === 0)

  return (
    <section className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Cortes por dia · últimos {days.length} dias</h3>
        <div className="flex items-center gap-4 text-xs text-zinc-300">
          {SERIES.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
          <button
            type="button"
            onClick={() => setAsTable(!asTable)}
            className="rounded border border-white/20 px-2 py-0.5 hover:bg-white/10"
          >
            {asTable ? 'Ver gráfico' : 'Ver tabela'}
          </button>
        </div>
      </div>

      {asTable ? (
        <table className="mt-3 w-full text-sm tabular-nums">
          <thead className="text-left text-zinc-400">
            <tr>
              <th className="py-1 font-normal">Dia</th>
              <th className="py-1 text-right font-normal">Gerados</th>
              <th className="py-1 text-right font-normal">Postados</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {days.map((d) => (
              <tr key={d.date}>
                <td className="py-1">{formatDayMonth(d.date)}</td>
                <td className="py-1 text-right">{d.generated}</td>
                <td className="py-1 text-right">{d.posted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div ref={box} className="relative mt-3">
          <svg
            width={W}
            height={H}
            className="block"
            role="img"
            aria-label="Cortes gerados e postados por dia"
          >
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left}
                  x2={W - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke="rgba(255,255,255,0.08)"
                />
                <text
                  x={PAD.left - 6}
                  y={y(t) + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="#a1a1aa"
                >
                  {t}
                </text>
              </g>
            ))}
            {days.map((d, i) => {
              const cx = PAD.left + slot * i + slot / 2
              return (
                <g key={d.date}>
                  {hover === i && (
                    <rect
                      x={cx - slot / 2}
                      y={PAD.top}
                      width={slot}
                      height={PLOT_H}
                      fill="rgba(255,255,255,0.05)"
                    />
                  )}
                  {SERIES.map((s, j) => {
                    const v = d[s.key]
                    // 2px gap between the pair
                    const x = j === 0 ? cx - barW - 1 : cx + 1
                    return <path key={s.key} d={barPath(x, y(v), barW, y(0) - y(v))} fill={s.color} />
                  })}
                  {((days.length - 1 - i) % (slot < 40 ? 2 : 1) === 0) && (
                    <text x={cx} y={H - 6} textAnchor="middle" fontSize="10" fill="#a1a1aa">
                      {formatDayMonth(d.date)}
                    </text>
                  )}
                  {/* hit target: the whole column, bigger than the bars */}
                  <rect
                    x={cx - slot / 2}
                    y={PAD.top}
                    width={slot}
                    height={PLOT_H + PAD.bottom}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                  />
                </g>
              )
            })}
          </svg>
          {empty && (
            <p className="absolute inset-0 grid place-items-center text-sm text-zinc-500">
              Nenhum corte nesses dias.
            </p>
          )}
          {hover != null && (
            <div
              className={`pointer-events-none absolute top-0 z-10 rounded border border-white/15 bg-zinc-900 px-2.5 py-1.5 text-xs shadow-lg ${
                // keep the tooltip inside the chart at both ends
                hover < 2 ? '' : hover > days.length - 3 ? '-translate-x-full' : '-translate-x-1/2'
              }`}
              style={{ left: PAD.left + slot * hover + slot / 2 }}
            >
              <p className="mb-0.5 font-semibold text-zinc-100">{formatDayMonth(days[hover].date)}</p>
              {SERIES.map((s) => (
                <p key={s.key} className="flex items-center gap-1.5 text-zinc-300">
                  <span className="size-2 rounded-sm" style={{ background: s.color }} />
                  {s.label}: <span className="font-semibold text-zinc-100">{days[hover][s.key]}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
