import { useEffect, useState } from 'react'
import { CaptionSettings } from '../components/CaptionSettings'
import { FrameCard } from '../components/FrameCard'
import { FrameUpload } from '../components/FrameUpload'
import { api } from '../lib/api'
import type { Captions, Frames } from '../lib/types'

export function FramePage() {
  const [data, setData] = useState<Frames | null>(null)
  const [captions, setCaptions] = useState<Captions | null>(null)
  const [sample, setSample] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmRerender, setConfirmRerender] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api
      .frames()
      .then(setData)
      .catch((err: Error) => setError(err.message))
    api
      .captions()
      .then(setCaptions)
      .catch((err: Error) => setError(err.message))
    // a real clip under the overlay shows how it will look (it may already carry an old frame)
    api
      .clips('pending_review', 'potential')
      .then((clips) => setSample(clips.find((c) => c.video_url)?.video_url ?? null))
      .catch(() => setSample(null))
  }, [])

  function run(action: Promise<Frames>) {
    setError(null)
    setMessage(null)
    action.then(setData).catch((err: Error) => setError(err.message))
  }

  async function rerender() {
    setConfirmRerender(false)
    try {
      const { queued } = await api.rerenderWithFrame()
      setMessage(`${queued} corte(s) na fila de render. Acompanhe na aba Aprovar.`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!data) return <p className="text-zinc-400">{error ?? 'Carregando…'}</p>

  const noFrame = !data.frames.some((f) => f.is_default)

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-xl font-bold">Moldura</h2>
        <p className="max-w-3xl text-sm text-zinc-400">
          A moldura em uso é aplicada por cima de todo corte novo (e dos re-renderizados no
          Estúdio). Cortes já prontos não mudam sozinhos.
        </p>
      </section>

      <FrameUpload onUploaded={setData} />

      {error && <p className="text-orange-400">{error}</p>}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <FrameCard
          name="Sem moldura"
          detail="Só o vídeo com fundo desfocado"
          overlayUrl={null}
          sampleVideoUrl={sample}
          isDefault={noFrame}
          onMakeDefault={() => run(api.setDefaultFrame(null))}
        />
        {data.frames.map((f) => (
          <FrameCard
            key={f.id}
            name={f.name}
            detail={f.width ? `${f.width}x${f.height}` : 'arquivo não encontrado'}
            overlayUrl={f.url}
            sampleVideoUrl={sample}
            isDefault={f.is_default}
            onMakeDefault={() => run(api.setDefaultFrame(f.id))}
            onDelete={() => run(api.deleteFrame(f.id))}
          />
        ))}
      </div>

      {captions && (
        <CaptionSettings
          data={captions}
          sampleVideoUrl={sample}
          frameUrl={data.frames.find((f) => f.is_default)?.url ?? null}
          onSaved={setCaptions}
        />
      )}

      <section className="space-y-2 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
        <h3 className="font-semibold">Aplicar nos cortes que já existem</h3>
        <p className="text-zinc-400">
          Renderiza de novo os {data.live_clips} corte(s) aguardando aprovação ou postagem com a
          moldura e a legenda em uso. Os já postados ou recusados não são tocados. Cada corte leva
          alguns segundos (a primeira legenda de cada corte leva mais: o Whisper ouve o trecho).
        </p>
        {message && <p className="text-emerald-400">{message}</p>}
        {confirmRerender ? (
          <div className="flex flex-wrap items-center gap-2">
            <span>Re-renderizar {data.live_clips} corte(s)?</span>
            <button
              type="button"
              onClick={rerender}
              className="rounded bg-pink-500 px-3 py-1 font-semibold text-white hover:bg-pink-400"
            >
              Sim
            </button>
            <button
              type="button"
              onClick={() => setConfirmRerender(false)}
              className="rounded border border-white/15 bg-white/5 px-3 py-1 hover:border-white/25 hover:bg-white/10"
            >
              Cancelar
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={data.live_clips === 0}
            onClick={() => setConfirmRerender(true)}
            className="rounded border border-white/15 bg-white/5 px-3 py-1 hover:border-white/25 hover:bg-white/10 disabled:opacity-40"
          >
            Re-renderizar cortes
          </button>
        )}
      </section>
    </div>
  )
}
