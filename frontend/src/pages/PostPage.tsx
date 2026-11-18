import { useCallback, useEffect, useState } from 'react'
import { ClipCard } from '../components/ClipCard'
import { PostCard } from '../components/PostCard'
import { PostedList } from '../components/PostedList'
import { StudioModal } from '../components/StudioModal'
import { api } from '../lib/api'
import type { Account, Clip, ClipStatus, RejectReason, Source } from '../lib/types'

// `archived` turns this into the "Pré-lançamento" tab: the same posting flow for the clips
// shelved there, plus the ones still waiting for review
type Props = { archived?: boolean }

export function PostPage({ archived = false }: Props) {
  const [review, setReview] = useState<Clip[]>([])
  const [queue, setQueue] = useState<Clip[]>([])
  const [posted, setPosted] = useState<Clip[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [rejectReasons, setRejectReasons] = useState<RejectReason[]>([])
  const [error, setError] = useState<string | null>(null)
  const [studioId, setStudioId] = useState<number | null>(null)

  const load = useCallback(() => {
    Promise.all([
      archived ? api.clips('pending_review', 'potential', true) : Promise.resolve([]),
      api.clips('approved', 'potential', archived),
      api.clips('posted', 'posted', archived),
      api.accounts(),
    ])
      .then(([r, q, p, a]) => {
        setReview(r)
        setQueue(q)
        setPosted(p)
        setAccounts(a)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [archived])

  useEffect(load, [load])
  useEffect(() => {
    if (archived) api.rejectReasons().then(setRejectReasons).catch(() => {})
  }, [archived])

  function onPosted(clip: Clip) {
    setQueue((list) => list.filter((c) => c.id !== clip.id))
    setPosted((list) => [clip, ...list])
  }

  function moveTo(id: number, status: ClipStatus, rejectReason: string | null = null) {
    api
      .setClipStatus(id, status, rejectReason)
      .then(load)
      .catch((err: Error) => setError(err.message))
  }

  function shelf(id: number) {
    api
      .setClipArchived(id, !archived)
      .then(load)
      .catch((err: Error) => setError(err.message))
  }

  function updateSource(source: Source) {
    setReview((list) => list.map((c) => (c.source.id === source.id ? { ...c, source } : c)))
  }

  return (
    <div className="space-y-8">
      {error && <p className="text-orange-400">{error}</p>}
      {archived && (
        <p className="text-sm text-zinc-400">
          Cortes guardados de antes do lançamento (curiosidades). Ficam fora das abas Aprovar e
          Postagem, mas continuam ensinando a IA e contando no histórico dos canais do Radar.
        </p>
      )}

      {review.length > 0 && (
        <section>
          <h2 className="text-xl font-bold">Esperando aprovação ({review.length})</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {review.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                rejectReasons={rejectReasons}
                onStatus={moveTo}
                onSource={updateSource}
                onStudio={setStudioId}
              />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-xl font-bold">Prontos para postar ({queue.length})</h2>
        <p className="text-sm text-zinc-400">
          Baixe o vídeo, copie o texto, poste você mesmo no app e depois marque aqui.
        </p>
        {queue.length === 0 ? (
          <p className="mt-8 text-center text-zinc-500">
            {archived
              ? 'Nenhum corte de pré-lançamento esperando postagem.'
              : 'Nenhum corte aprovado esperando. Aprove alguns na aba Aprovar.'}
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
                onStudio={setStudioId}
                onShelf={shelf}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xl font-bold">Já postados ({posted.length})</h2>
        <PostedList clips={posted} accounts={accounts} onUndo={(id) => moveTo(id, 'approved')} />
      </section>

      {studioId != null && (
        <StudioModal clipId={studioId} onClose={() => setStudioId(null)} onSaved={load} />
      )}
    </div>
  )
}
