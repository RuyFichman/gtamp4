import { useEffect, useState } from 'react'
import { WarmupCard } from '../components/WarmupCard'
import { api } from '../lib/api'
import type { Warmup } from '../lib/types'

export function WarmupPage({ onOpenAccounts }: { onOpenAccounts: () => void }) {
  const [list, setList] = useState<Warmup[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .warmup()
      .then(setList)
      .catch((err: Error) => setError(err.message))
  }, [])

  function replace(w: Warmup) {
    setList((l) => l && l.map((x) => (x.account_id === w.account_id ? w : x)))
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-xl font-bold">Aquecimento de contas novas</h2>
        <p className="max-w-3xl text-sm text-zinc-400">
          Checklist para você seguir <strong>manualmente</strong> no celular, por 14 dias. O app
          não entra nas contas, não curte, não rola o feed e não posta nada: automatizar isso
          viola as regras do TikTok/Instagram e derruba contas. É uma sugestão de rotina, não uma
          regra oficial das plataformas.
        </p>
      </section>
      {error && <p className="text-orange-400">{error}</p>}
      {list && list.length === 0 && (
        <p className="text-zinc-500">
          Nenhuma conta cadastrada.{' '}
          <button type="button" onClick={onOpenAccounts} className="text-cyan-300 hover:underline">
            Cadastre em Contas
          </button>
          .
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list?.map((w) => (
          <WarmupCard key={w.account_id} warmup={w} onChange={replace} />
        ))}
      </div>
    </div>
  )
}
