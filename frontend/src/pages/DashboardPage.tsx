import { useCallback, useEffect, useState } from 'react'
import { DailyChart } from '../components/DailyChart'
import { StatTile } from '../components/StatTile'
import { api } from '../lib/api'
import { formatBytes, formatDateTime, PLATFORM_LABEL } from '../lib/format'
import type { Stats } from '../lib/types'

export type NavTarget = 'Aprovar' | 'Postagem' | 'Contas' | 'Radar'

const PANEL = 'rounded-lg border border-white/10 bg-white/5 p-4 text-sm'

export function DashboardPage({ onNavigate }: { onNavigate: (tab: NavTarget) => void }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .stats()
      .then((s) => {
        setStats(s)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  if (!stats) return <p className="text-zinc-400">{error ?? 'Carregando…'}</p>
  const { clips, jobs, radar, disk } = stats
  const rate = stats.approval_rate == null ? '—' : `${Math.round(stats.approval_rate * 100)}%`

  return (
    <div className="space-y-6">
      {error && <p className="text-orange-400">{error}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Esperando aprovação"
          value={clips.pending_review}
          hint="Abrir a aba Aprovar"
          onClick={() => onNavigate('Aprovar')}
        />
        <StatTile
          label="Prontos para postar"
          value={clips.approved}
          hint="Abrir a aba Postagem"
          onClick={() => onNavigate('Postagem')}
        />
        <StatTile label="Postados" value={clips.posted} hint={`${clips.total} cortes gerados no total`} />
        <StatTile
          label="Taxa de aprovação"
          value={rate}
          hint={`${clips.approved + clips.posted} aprovados de ${
            clips.approved + clips.posted + clips.rejected
          } revisados`}
        />
      </div>

      <DailyChart days={stats.days} />

      <div className="grid gap-3 lg:grid-cols-3">
        <section className={PANEL}>
          <h3 className="font-semibold">A nota da IA está acertando?</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Potencial médio dos cortes que você aprovou vs. recusou. Se ficarem parecidos, a nota
            não está ajudando a decidir.
          </p>
          <dl className="mt-3 space-y-1 tabular-nums">
            <div className="flex justify-between">
              <dt className="text-zinc-400">Aprovados</dt>
              <dd className="font-semibold">{stats.avg_potential_kept ?? '—'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Recusados</dt>
              <dd className="font-semibold">{stats.avg_potential_rejected ?? '—'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Vídeos de origem</dt>
              <dd className="font-semibold">{stats.source_videos}</dd>
            </div>
          </dl>
        </section>

        <section className={PANEL}>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Postados por conta</h3>
            <button
              type="button"
              onClick={() => onNavigate('Contas')}
              className="text-xs text-cyan-300 hover:underline"
            >
              Contas
            </button>
          </div>
          {stats.accounts.length === 0 ? (
            <p className="mt-3 text-zinc-500">Nenhuma conta cadastrada.</p>
          ) : (
            <ul className="mt-3 space-y-1.5">
              {stats.accounts.map((a) => (
                <li key={a.id} className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate">
                    @{a.handle}{' '}
                    <span className="text-xs text-zinc-500">
                      {PLATFORM_LABEL[a.platform] ?? a.platform}
                    </span>
                  </span>
                  <span className="shrink-0 text-right tabular-nums">
                    <span className="font-semibold">{a.posted}</span>
                    <span className="block text-xs text-zinc-500">
                      {a.last_posted_at ? `último ${formatDateTime(a.last_posted_at)}` : 'nada ainda'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={PANEL}>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Sistema</h3>
            <button
              type="button"
              onClick={() => onNavigate('Radar')}
              className="text-xs text-cyan-300 hover:underline"
            >
              Radar
            </button>
          </div>
          <dl className="mt-3 space-y-1 tabular-nums">
            <div className="flex justify-between">
              <dt className="text-zinc-400">Radar</dt>
              <dd className={radar.enabled ? 'text-emerald-400' : 'text-zinc-400'}>
                {radar.enabled ? 'ligado' : 'desligado'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Enviados (24 h)</dt>
              <dd>
                {radar.sent_24h}/{radar.daily_limit}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Encontrados (24 h) · na espera</dt>
              <dd>
                {radar.found_24h} · {radar.waiting}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Fila de jobs</dt>
              <dd>
                {jobs.running ? `${jobs.running} rodando, ` : ''}
                {jobs.queued} na fila
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Jobs com falha</dt>
              <dd>
                {jobs.failed > 0 ? (
                  <button
                    type="button"
                    onClick={() => onNavigate('Aprovar')}
                    className="text-orange-400 hover:underline"
                  >
                    ⚠ {jobs.failed} (ver)
                  </button>
                ) : (
                  '0'
                )}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Vídeos originais</dt>
              <dd>
                {formatBytes(disk.videos_bytes)} ({disk.videos_files})
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-400">Cortes</dt>
              <dd>{formatBytes(disk.clips_bytes)}</dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  )
}
