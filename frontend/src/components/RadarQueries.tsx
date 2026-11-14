import { type FormEvent, useState } from 'react'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/format'
import type { RadarQuery, RadarQueryKind } from '../lib/types'

const SUGGESTIONS = ['GTA 6', 'GTA VI', 'GTA 6 trailer', 'GTA 6 leak']
const SMALL_BTN = 'rounded border border-white/20 px-2 py-0.5 text-xs hover:bg-white/10'

type Props = { queries: RadarQuery[]; onChange: () => void }

export function RadarQueries({ queries, onChange }: Props) {
  const [kind, setKind] = useState<RadarQueryKind>('search')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const existing = new Set(queries.map((q) => q.query.toLowerCase()))

  async function add(value: string, k: RadarQueryKind = kind) {
    setError(null)
    try {
      await api.addRadarQuery(k, value)
      setText('')
      onChange()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    add(text)
  }

  function run(action: Promise<unknown>) {
    action.then(onChange).catch((err: Error) => setError(err.message))
  }

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-bold">O que buscar</h2>
      <form onSubmit={submit} className="flex flex-wrap gap-2 text-sm">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as RadarQueryKind)}
          className="rounded border border-white/15 bg-indigo-950 px-2 py-1.5"
        >
          <option value="search">Termo de busca</option>
          <option value="channel">Canal</option>
        </select>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={kind === 'search' ? 'ex.: GTA 6 leak' : 'ex.: @RockstarGames ou link do canal'}
          className="min-w-48 flex-1 rounded border border-white/15 bg-black/30 px-2 py-1.5 placeholder:text-zinc-500"
        />
        <button className="rounded bg-pink-500 px-4 py-1.5 font-semibold text-white hover:bg-pink-400">
          Adicionar
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5 text-xs">
        {SUGGESTIONS.filter((s) => !existing.has(s.toLowerCase())).map((s) => (
          <button key={s} onClick={() => add(s, 'search')} className={SMALL_BTN}>
            + {s}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-orange-400">{error}</p>}

      {queries.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Nenhuma busca cadastrada. Adicione um termo ou canal para o Radar funcionar.
        </p>
      ) : (
        <ul className="divide-y divide-white/10 rounded-lg border border-white/10 bg-white/5 text-sm">
          {queries.map((q) => (
            <li key={q.id} className="px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="w-28 text-zinc-400">{q.kind === 'channel' ? 'Canal' : 'Busca'}</span>
                <span className={`font-semibold ${q.enabled ? '' : 'text-zinc-500 line-through'}`}>
                  {q.query}
                </span>
                <span className="flex-1 text-xs text-zinc-500">
                  última: {formatDateTime(q.last_run_at)}
                </span>
                <button
                  onClick={() => run(api.toggleRadarQuery(q.id, !q.enabled))}
                  className={SMALL_BTN}
                >
                  {q.enabled ? 'Pausar' : 'Ativar'}
                </button>
                <button onClick={() => run(api.deleteRadarQuery(q.id))} className={SMALL_BTN}>
                  Remover
                </button>
              </div>
              {q.last_error && (
                <p className="mt-1 truncate text-xs text-orange-400" title={q.last_error}>
                  Falhou na última busca: {q.last_error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
