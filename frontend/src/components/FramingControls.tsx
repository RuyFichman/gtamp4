import type { Framing } from '../lib/types'
import { RangeField as Slider } from './RangeField'

type Props = {
  value: Framing
  onChange: (f: Framing) => void
  onAuto: (() => void) | null // null = original not on disk
  autoBusy: boolean
  autoMessage: string | null
}

const side = (v: number, neg: string, pos: string) =>
  Math.abs(v) < 0.01 ? 'meio' : `${Math.round(Math.abs(v) * 100)}% ${v < 0 ? neg : pos}`

export function FramingControls({ value, onChange, onAuto, autoBusy, autoMessage }: Props) {
  const set = (patch: Partial<Framing>) => onChange({ ...value, ...patch })

  return (
    <div className="space-y-2">
      <Slider
        label="Zoom"
        min={1}
        max={3}
        step={0.05}
        value={value.zoom}
        shown={`${value.zoom.toFixed(2)}x`}
        onChange={(zoom) => set({ zoom })}
      />
      <Slider
        label="Horizontal"
        min={-1}
        max={1}
        step={0.02}
        value={value.pan_x}
        shown={side(value.pan_x, 'esq.', 'dir.')}
        onChange={(pan_x) => set({ pan_x })}
      />
      <Slider
        label="Vertical"
        min={-1}
        max={1}
        step={0.02}
        value={value.pan_y}
        shown={side(value.pan_y, 'cima', 'baixo')}
        onChange={(pan_y) => set({ pan_y })}
      />
      <p className="text-xs text-zinc-500">
        A posição só muda algo quando o zoom deixa o vídeo maior que a tela (o vertical, a partir
        de ~3x).
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {onAuto && (
          <button
            type="button"
            onClick={onAuto}
            disabled={autoBusy}
            className="rounded bg-white/10 px-3 py-1 hover:bg-white/20 disabled:opacity-50"
          >
            {autoBusy ? 'Analisando…' : 'Automático (barras pretas)'}
          </button>
        )}
        <button
          type="button"
          onClick={() => onChange({ zoom: 1, pan_x: 0, pan_y: 0 })}
          className="rounded border border-white/15 bg-white/5 px-3 py-1 hover:border-white/25 hover:bg-white/10"
        >
          Sem zoom
        </button>
      </div>
      {autoMessage && <p className="text-xs text-zinc-300">{autoMessage}</p>}
    </div>
  )
}
