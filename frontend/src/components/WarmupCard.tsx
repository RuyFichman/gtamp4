import { useState } from 'react'
import { api } from '../lib/api'
import { formatDayMonth, PLATFORM_LABEL } from '../lib/format'
import type { Warmup } from '../lib/types'

const TOTAL_DAYS = 14

type Props = { warmup: Warmup; onChange: (w: Warmup) => void }

export function WarmupCard({ warmup: w, onChange }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  function run(action: Promise<Warmup>) {
    setError(null)
    action.then(onChange).catch((err: Error) => setError(err.message))
  }

  const header = (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="font-semibold">
        @{w.handle}{' '}
        <span className="text-sm font-normal text-zinc-400">
          {PLATFORM_LABEL[w.platform] ?? w.platform}
        </span>
      </h3>
      {w.started_on && (
        <span className="text-sm text-zinc-400">
          {w.finished ? 'Aquecimento concluído' : `Dia ${w.day_number} de ${TOTAL_DAYS}`}
        </span>
      )}
    </div>
  )

  if (!w.started_on) {
    return (
      <article className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
        {header}
        <p className="text-zinc-400">Conta ainda não está em aquecimento.</p>
        <button
          type="button"
          onClick={() => run(api.startWarmup(w.account_id))}
          className="rounded bg-pink-500 px-3 py-1.5 font-semibold text-white hover:bg-pink-400"
        >
          Começar hoje
        </button>
        {error && <p className="text-orange-400">{error}</p>}
      </article>
    )
  }

  const progress = Math.min(1, (w.day_number ?? 0) / TOTAL_DAYS)

  return (
    <article className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
      {header}
      <div className="h-1.5 overflow-hidden rounded bg-white/10">
        <div
          className="h-full bg-gradient-to-r from-orange-400 to-pink-500"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {w.finished ? (
        <p className="text-emerald-400">
          Pronto: a conta passou pelos {TOTAL_DAYS} dias. Agora é manter 1–2 posts por dia.
        </p>
      ) : (
        <>
          <div>
            <p className="font-semibold text-zinc-100">Hoje · {w.phase_title}</p>
            <p className="text-xs text-zinc-500">{w.phase_tip}</p>
          </div>
          <ul className="space-y-1.5">
            {w.tasks.map((t) => (
              <li key={t.key}>
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    checked={t.done}
                    onChange={(e) => run(api.checkWarmup(w.account_id, t.key, e.target.checked))}
                    className="mt-0.5 size-4 accent-pink-500"
                  />
                  <span className={t.done ? 'text-zinc-500 line-through' : ''}>
                    {t.text}
                    {t.once && <span className="ml-1 text-xs text-zinc-500">(uma vez)</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}

      <div>
        <p className="mb-1 text-xs text-zinc-500">Dias até agora</p>
        <ol className="flex flex-wrap gap-1">
          {w.days.map((d) => {
            const full = d.total > 0 && d.done >= d.total
            const label = `Dia ${d.day_number} (${formatDayMonth(d.date)}): ${d.done} de ${d.total} tarefas`
            return (
              <li
                key={d.date}
                title={label}
                aria-label={label}
                className={`grid size-6 place-items-center rounded text-[10px] tabular-nums ${
                  full
                    ? 'bg-pink-500 text-white'
                    : d.done > 0
                      ? 'bg-pink-500/35 text-zinc-100'
                      : 'bg-white/10 text-zinc-400'
                }`}
              >
                {d.day_number}
              </li>
            )
          })}
        </ol>
      </div>

      {error && <p className="text-orange-400">{error}</p>}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {confirmReset ? (
          <>
            <span>Apagar o progresso e parar o aquecimento?</span>
            <button
              type="button"
              onClick={() => {
                setConfirmReset(false)
                run(api.stopWarmup(w.account_id))
              }}
              className="rounded border border-orange-400/60 px-2 py-0.5 text-orange-300 hover:bg-orange-500/10"
            >
              Sim, parar
            </button>
            <button
              type="button"
              onClick={() => setConfirmReset(false)}
              className="rounded border border-white/20 px-2 py-0.5 hover:bg-white/10"
            >
              Cancelar
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmReset(true)}
            className="rounded border border-white/20 px-2 py-0.5 text-zinc-400 hover:bg-white/10"
          >
            Parar / recomeçar
          </button>
        )}
      </div>
    </article>
  )
}
