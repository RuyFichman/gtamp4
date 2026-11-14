import { useState } from 'react'
import { api } from '../lib/api'
import { formatDateTime, formatDuration, formatViews, sourceAt } from '../lib/format'
import type { Clip, ClipStatus, Source } from '../lib/types'

type Props = {
  clip: Clip
  onStatus: (id: number, status: ClipStatus) => void
  onSource: (source: Source) => void
}

export function ClipCard({ clip, onStatus, onSource }: Props) {
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { source } = clip

  async function refresh() {
    setRefreshing(true)
    setError(null)
    try {
      onSource(await api.refreshViews(source.id))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <article className="flex flex-col overflow-hidden rounded-xl border border-pink-500/40 bg-indigo-950/60 shadow-lg shadow-pink-500/10">
      {clip.video_url ? (
        <video
          src={clip.video_url}
          controls
          preload="metadata"
          className="aspect-[9/16] w-full bg-black object-contain"
        />
      ) : (
        <div className="grid aspect-[9/16] place-items-center bg-black text-xs text-zinc-500">
          sem arquivo
        </div>
      )}

      <div className="flex flex-1 flex-col gap-2 p-3 text-xs">
        <h3 className="text-sm font-semibold leading-snug">{clip.title}</h3>

        <div className="space-y-0.5 text-zinc-400">
          <p className="line-clamp-2" title={source.title}>
            Do vídeo: <span className="text-zinc-300">{source.title}</span>
            {source.channel && ` · ${source.channel}`}
          </p>
          <p className="font-medium text-zinc-200">{formatViews(source.views)}</p>
          <p>Consulta: {formatDateTime(source.views_checked_at)}</p>
          <p>
            <a
              href={sourceAt(source.url, clip.start_s)}
              target="_blank"
              rel="noreferrer"
              className="text-cyan-300 underline"
            >
              Ver fonte no YouTube
            </a>{' '}
            · trecho {formatDuration(clip.start_s)}–{formatDuration(clip.end_s)}
          </p>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="mt-1 rounded border border-white/20 px-2 py-0.5 text-zinc-200 hover:bg-white/10 disabled:opacity-50"
          >
            {refreshing ? 'Atualizando…' : 'Atualizar views'}
          </button>
          {error && <p className="text-orange-400">{error}</p>}
        </div>

        <p className="font-semibold text-orange-400">
          Potencial {clip.potential}/100 · {clip.potential_reason}
        </p>

        <p className="whitespace-pre-line text-zinc-300">
          {clip.description}
          {clip.hashtags.length > 0 && (
            <span className="block text-zinc-400">
              {clip.hashtags.map((h) => `#${h}`).join(' ')}
            </span>
          )}
        </p>

        <div className="mt-auto grid grid-cols-3 gap-1.5 pt-2">
          <button
            onClick={() => onStatus(clip.id, 'approved')}
            className="rounded bg-pink-500 py-1.5 font-semibold text-white hover:bg-pink-400"
          >
            Aprovar
          </button>
          <button
            onClick={() => onStatus(clip.id, 'rejected')}
            className="rounded border border-white/20 py-1.5 hover:bg-white/10"
          >
            Recusar
          </button>
          <button
            disabled
            title="Em breve"
            className="rounded border border-white/20 py-1.5 opacity-40"
          >
            Estúdio
          </button>
          <a
            href={api.clipDownloadUrl(clip.id)}
            className="col-span-3 rounded border border-white/20 py-1.5 text-center hover:bg-white/10"
          >
            Baixar
          </a>
        </div>
      </div>
    </article>
  )
}
