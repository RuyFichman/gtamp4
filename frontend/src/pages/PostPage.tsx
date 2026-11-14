import { useCallback, useEffect, useState } from 'react'
import { PostCard } from '../components/PostCard'
import { PostedList } from '../components/PostedList'
import { api } from '../lib/api'
import type { Account, Clip } from '../lib/types'

export function PostPage() {
  const [queue, setQueue] = useState<Clip[]>([])
  const [posted, setPosted] = useState<Clip[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    Promise.all([api.clips('approved', 'potential'), api.clips('posted', 'posted'), api.accounts()])
      .then(([q, p, a]) => {
        setQueue(q)
        setPosted(p)
        setAccounts(a)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(load, [load])

  function onPosted(clip: Clip) {
    setQueue((list) => list.filter((c) => c.id !== clip.id))
    setPosted((list) => [clip, ...list])
  }

  function moveTo(id: number, status: 'pending_review' | 'approved') {
    api
      .setClipStatus(id, status)
      .then(load)
      .catch((err: Error) => setError(err.message))
  }

  return (
    <div className="space-y-8">
      {error && <p className="text-orange-400">{error}</p>}
      <section>
        <h2 className="text-xl font-bold">Prontos para postar ({queue.length})</h2>
        <p className="text-sm text-zinc-400">
          Baixe o vídeo, copie o texto, poste você mesmo no app e depois marque aqui.
        </p>
        {queue.length === 0 ? (
          <p className="mt-8 text-center text-zinc-500">
            Nenhum corte aprovado esperando. Aprove alguns na aba Aprovar.
          </p>
        ) : (
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            {queue.map((clip) => (
              <PostCard
                key={clip.id}
                clip={clip}
                accounts={accounts}
                onPosted={onPosted}
                onUnapprove={(id) => moveTo(id, 'pending_review')}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xl font-bold">Já postados ({posted.length})</h2>
        <PostedList clips={posted} accounts={accounts} onUndo={(id) => moveTo(id, 'approved')} />
      </section>
    </div>
  )
}
