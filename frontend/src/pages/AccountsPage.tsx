import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { PLATFORM_LABEL } from '../lib/format'
import type { Account, AccountInput, Platform } from '../lib/types'

const EMPTY: AccountInput = { platform: 'tiktok', handle: '', name: '', notes: '' }
const INPUT =
  'rounded border border-white/15 bg-black/30 px-2 py-1.5 text-zinc-100 placeholder:text-zinc-500'
const SMALL_BTN = 'rounded border border-white/15 bg-white/5 px-2 py-0.5 text-xs hover:border-white/25 hover:bg-white/10'

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [form, setForm] = useState<AccountInput>(EMPTY)
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .accounts()
      .then(setAccounts)
      .catch((err: Error) => setError(err.message))
  }, [])
  useEffect(load, [load])

  function reset() {
    setEditing(null)
    setForm(EMPTY)
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      if (editing) await api.updateAccount(editing, form)
      else await api.createAccount(form)
      reset()
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  function edit(a: Account) {
    setEditing(a.id)
    setForm({ platform: a.platform, handle: a.handle, name: a.name, notes: a.notes })
  }

  async function remove(a: Account) {
    try {
      await api.deleteAccount(a.id)
      if (editing === a.id) reset()
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-xl font-bold">Suas contas</h2>
        <p className="text-sm text-zinc-400">
          Só para organizar onde cada corte foi postado. O app não faz login nem posta nada.
        </p>
      </section>

      <form
        onSubmit={save}
        className="grid gap-2 rounded-lg border border-white/10 bg-white/5 p-4 text-sm sm:grid-cols-[auto_1fr_1fr]"
      >
        <select
          value={form.platform}
          onChange={(e) => setForm({ ...form, platform: e.target.value as Platform })}
          className="rounded border border-white/15 bg-black/30 px-2 py-1.5"
        >
          {Object.entries(PLATFORM_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          value={form.handle}
          onChange={(e) => setForm({ ...form, handle: e.target.value })}
          placeholder="@usuario"
          required
          className={INPUT}
        />
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Apelido (opcional)"
          className={INPUT}
        />
        <input
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          placeholder="Notas (opcional): nicho, melhor horário…"
          className={`${INPUT} sm:col-span-2`}
        />
        <div className="flex gap-2">
          <button className="flex-1 rounded bg-pink-500 px-3 py-1.5 font-semibold text-white hover:bg-pink-400">
            {editing ? 'Salvar' : 'Adicionar'}
          </button>
          {editing && (
            <button
              type="button"
              onClick={reset}
              className="rounded border border-white/15 bg-white/5 px-3 py-1.5 hover:border-white/25 hover:bg-white/10"
            >
              Cancelar
            </button>
          )}
        </div>
        {error && <p className="text-orange-400 sm:col-span-3">{error}</p>}
      </form>

      {accounts.length === 0 ? (
        <p className="text-center text-zinc-500">Nenhuma conta cadastrada.</p>
      ) : (
        <ul className="divide-y divide-white/10 rounded-lg border border-white/10 bg-white/5 text-sm">
          {accounts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5">
              <span className="w-28 text-zinc-400">{PLATFORM_LABEL[a.platform] ?? a.platform}</span>
              <span className="font-semibold">@{a.handle}</span>
              {a.name && <span className="text-zinc-300">{a.name}</span>}
              <span className="min-w-0 flex-1 truncate text-zinc-500">{a.notes}</span>
              <span className="text-zinc-400">{a.posted_count} postado(s)</span>
              <button onClick={() => edit(a)} className={SMALL_BTN}>
                Editar
              </button>
              <button onClick={() => remove(a)} className={SMALL_BTN}>
                Remover
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
