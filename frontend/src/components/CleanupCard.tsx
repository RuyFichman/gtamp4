import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { formatBytes } from '../lib/format'
import type { CleanupPreview } from '../lib/types'

export function CleanupCard() {
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .cleanupPreview()
      .then(setPreview)
      .catch((err: Error) => setError(err.message))
  }, [])
  useEffect(load, [load])

  async function run() {
    setConfirming(false)
    setError(null)
    try {
      const freed = await api.cleanupOriginals()
      setMessage(`Apagados ${freed.files} vídeo(s), ${formatBytes(freed.bytes)} liberados.`)
      load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <section className="space-y-2 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
      <h3 className="font-semibold">Liberar espaço</h3>
      <p className="text-zinc-400">
        Apaga os vídeos originais baixados do YouTube cujos cortes já foram todos postados ou
        recusados. Os cortes prontos não são tocados. Se você abrir um desses cortes no Estúdio, o
        original é baixado de novo.
      </p>
      {preview && (
        <p>
          Dá para liberar:{' '}
          <span className="font-semibold">
            {preview.files} vídeo(s), {formatBytes(preview.bytes)}
          </span>
        </p>
      )}
      {preview?.blocked && <p className="text-amber-300">{preview.blocked}</p>}
      {message && <p className="text-emerald-400">{message}</p>}
      {error && <p className="text-orange-400">{error}</p>}
      {confirming ? (
        <div className="flex flex-wrap items-center gap-2">
          <span>Apagar {preview?.files} arquivo(s) do disco? Não dá para desfazer.</span>
          <button
            type="button"
            onClick={run}
            className="rounded bg-orange-600 px-3 py-1 font-semibold text-white hover:bg-orange-500"
          >
            Sim, apagar
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="rounded border border-white/20 px-3 py-1 hover:bg-white/10"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={!preview || preview.files === 0 || !!preview.blocked}
          className="rounded border border-white/20 px-3 py-1 hover:bg-white/10 disabled:opacity-40"
        >
          Apagar originais
        </button>
      )}
    </section>
  )
}
