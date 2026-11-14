import { useState } from 'react'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/format'
import type { RadarConfig, RadarStatus } from '../lib/types'

const INTERVALS = [15, 30, 60, 120, 360]

type Props = { status: RadarStatus; onChange: (s: RadarStatus) => void; onScan: () => void }

export function RadarControls({ status, onChange, onScan }: Props) {
  const [error, setError] = useState<string | null>(null)
  const { config } = status

  function save(patch: Partial<RadarConfig>) {
    setError(null)
    api
      .setRadarConfig({ ...config, ...patch })
      .then(onChange)
      .catch((err: Error) => setError(err.message))
  }

  function scan() {
    setError(null)
    api
      .radarScan()
      .then(onScan)
      .catch((err: Error) => setError(err.message))
  }

  return (
    <section className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => save({ enabled: !config.enabled })}
          className={`rounded px-4 py-1.5 font-semibold ${
            config.enabled
              ? 'bg-emerald-500 text-white hover:bg-emerald-400'
              : 'border border-white/20 hover:bg-white/10'
          }`}
        >
          {config.enabled ? 'Radar ligado' : 'Radar desligado'}
        </button>

        <label className="flex items-center gap-2 text-zinc-400">
          Buscar a cada
          <select
            value={config.interval_minutes}
            onChange={(e) => save({ interval_minutes: Number(e.target.value) })}
            className="rounded border border-white/15 bg-indigo-950 px-2 py-1 text-zinc-100"
          >
            {INTERVALS.map((m) => (
              <option key={m} value={m}>
                {m < 60 ? `${m} min` : `${m / 60} h`}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 text-zinc-400">
          Máx. por dia
          <input
            type="number"
            min={0}
            max={200}
            defaultValue={config.daily_limit}
            key={config.daily_limit}
            onBlur={(e) => {
              const n = Number(e.target.value)
              if (n !== config.daily_limit && n >= 0) save({ daily_limit: n })
            }}
            className="w-16 rounded border border-white/15 bg-black/30 px-2 py-1 text-zinc-100"
          />
          vídeos
        </label>

        <button
          onClick={scan}
          disabled={status.scanning}
          className="ml-auto rounded bg-pink-500 px-4 py-1.5 font-semibold text-white hover:bg-pink-400 disabled:opacity-50"
        >
          {status.scanning ? 'Buscando…' : 'Buscar agora'}
        </button>
      </div>

      <p className="text-zinc-400">
        Enviados para corte nas últimas 24 h:{' '}
        <span className="font-semibold text-zinc-100">
          {status.sent_last_24h}/{config.daily_limit}
        </span>
        {' · '}Última busca: {formatDateTime(status.last_scan_at)}
        {config.enabled && status.next_scan_at && (
          <> · Próxima: {formatDateTime(status.next_scan_at)}</>
        )}
      </p>
      <p className="text-xs text-zinc-500">
        Cada vídeo enviado gasta uma análise da IA (Sonnet). A triagem dos títulos usa o Haiku,
        que é bem mais barato. O limite diário protege sua conta da Anthropic.
      </p>
      {error && <p className="text-orange-400">{error}</p>}
    </section>
  )
}
