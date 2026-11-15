import { useState } from 'react'
import { api } from '../lib/api'
import { formatDateTime, formatDuration } from '../lib/format'
import type { CandidateStatus, RadarCandidate } from '../lib/types'

const STATUS: Record<CandidateStatus, { label: string; className: string }> = {
  sent: { label: 'Enviado', className: 'bg-emerald-500/20 text-emerald-300' },
  waiting: { label: 'Na espera', className: 'bg-amber-500/20 text-amber-300' },
  rejected: { label: 'Descartado', className: 'bg-white/10 text-zinc-400' },
}

const FILTERS: { value: CandidateStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'sent', label: 'Enviados' },
  { value: 'waiting', label: 'Na espera' },
  { value: 'rejected', label: 'Descartados' },
]

const compact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })

type Props = { candidates: RadarCandidate[]; onChange: () => void }

export function CandidateList({ candidates, onChange }: Props) {
  const [filter, setFilter] = useState<CandidateStatus | 'all'>('all')
  const [error, setError] = useState<string | null>(null)
  const shown =
    filter === 'all'
      ? candidates
      : candidates
          .filter((c) => c.status === filter)
          // the waiting list in the order the Radar sends it
          .sort((a, b) => (a.queue_position ?? 0) - (b.queue_position ?? 0))

  function send(id: number) {
    setError(null)
    api
      .sendCandidate(id)
      .then(onChange)
      .catch((err: Error) => setError(err.message))
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-xl font-bold">Vídeos encontrados</h2>
          <p className="text-sm text-zinc-400">
            Na espera = passou na triagem e aguarda o limite diário liberar. A fila anda pelas
            views por hora desde a publicação (comparadas ao tamanho do canal) e pelo histórico do
            canal nas suas aprovações.
          </p>
        </div>
        <div className="flex gap-1 text-xs">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded px-2 py-1 ${
                filter === f.value ? 'bg-pink-500 text-white' : 'border border-white/15 bg-white/5 hover:border-white/25 hover:bg-white/10'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-sm text-orange-400">{error}</p>}

      {shown.length === 0 ? (
        <p className="text-sm text-zinc-500">Nada por aqui ainda.</p>
      ) : (
        <ul className="divide-y divide-white/10 rounded-lg border border-white/10 bg-white/5 text-sm">
          {shown.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS[c.status].className}`}
              >
                {STATUS[c.status].label}
                {c.queue_position != null && ` · ${c.queue_position}º`}
              </span>
              <div className="min-w-0 flex-1">
                <a
                  href={c.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate font-medium hover:underline"
                  title={c.title}
                >
                  {c.title}
                </a>
                <p className="truncate text-xs text-zinc-400">
                  {c.channel}
                  {c.subscribers != null && ` (${compact.format(c.subscribers)} inscritos)`}
                  {c.duration_s != null && ` · ${formatDuration(c.duration_s)}`}
                  {c.views != null && ` · ${compact.format(c.views)} views`}
                  {c.views_per_hour != null && (
                    <span title="Views por hora desde a publicação, quando o Radar achou o vídeo">
                      {` · ${compact.format(c.views_per_hour)}/h`}
                    </span>
                  )}
                  {' · '}
                  {formatDateTime(c.found_at)}
                </p>
                {c.channel_record && (
                  <p className="text-xs text-zinc-400">
                    Canal: {c.channel_record.approved} de {c.channel_record.decided}{' '}
                    {c.channel_record.decided === 1 ? 'corte aprovado' : 'cortes aprovados'} por você
                  </p>
                )}
                <p className="truncate text-xs text-zinc-500" title={c.reason}>
                  {c.reason}
                </p>
              </div>
              {c.status !== 'sent' && (
                <button
                  onClick={() => send(c.id)}
                  title="Ignora a triagem e o limite diário"
                  className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-xs hover:border-white/25 hover:bg-white/10"
                >
                  Cortar mesmo assim
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
