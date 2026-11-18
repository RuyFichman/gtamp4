import { useState } from 'react'
import { api } from '../lib/api'
import { captionText, formatViews, PLATFORM_LABEL, sourceAt } from '../lib/format'
import type { Account, Clip } from '../lib/types'
import { CopyButton } from './CopyButton'

type Props = {
  clip: Clip
  accounts: Account[]
  onPosted: (clip: Clip) => void
  onUnapprove: (id: number) => void
  onStudio: (id: number) => void
  onShelf: (id: number) => void // in/out of the "Pré-lançamento" tab
}

export function PostCard({ clip, accounts, onPosted, onUnapprove, onStudio, onShelf }: Props) {
  const [accountId, setAccountId] = useState<number | ''>('')
  const [postUrl, setPostUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const caption = captionText(clip.description, clip.hashtags)

  async function markPosted() {
    setSaving(true)
    setError(null)
    try {
      onPosted(await api.markPosted(clip.id, accountId === '' ? null : accountId, postUrl))
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <article className="flex flex-col overflow-hidden rounded-xl border border-white/15 bg-indigo-950/60 sm:flex-row">
      {clip.video_url && (
        <video
          src={clip.video_url}
          controls
          preload="metadata"
          className="aspect-[9/16] w-full shrink-0 bg-black object-contain sm:w-48"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col gap-3 p-4 text-xs">
        <div>
          <h3 className="text-sm font-semibold leading-snug">{clip.title}</h3>
          <p className="mt-0.5 text-zinc-400">
            Potencial {clip.potential}/100 · {formatViews(clip.source.views)} ·{' '}
            <a
              href={sourceAt(clip.source.url, clip.start_s)}
              target="_blank"
              rel="noreferrer"
              className="text-cyan-300 underline"
            >
              fonte
            </a>
          </p>
          <p className="truncate text-zinc-500" title={clip.source.title}>
            Do vídeo: {clip.source.title}
            {clip.source.channel && ` · ${clip.source.channel}`}
          </p>
        </div>

        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-sans text-zinc-300">
          {caption || 'Sem legenda.'}
        </pre>

        <div className="flex flex-wrap gap-1.5">
          <a
            href={api.clipDownloadUrl(clip.id)}
            className="rounded bg-white/10 px-2 py-1 font-semibold hover:bg-white/20"
          >
            Baixar vídeo
          </a>
          <button
            type="button"
            onClick={() => onStudio(clip.id)}
            className="rounded border border-white/15 bg-white/5 px-2 py-1 hover:border-white/25 hover:bg-white/10"
          >
            Estúdio
          </button>
          <CopyButton text={clip.title} label="Copiar título" />
          <CopyButton text={caption} label="Copiar legenda" />
          <CopyButton
            text={[clip.title, caption].filter(Boolean).join('\n\n')}
            label="Copiar tudo"
          />
        </div>

        <div className="mt-auto grid gap-2 border-t border-white/10 pt-3 sm:grid-cols-[1fr_1.4fr]">
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value === '' ? '' : Number(e.target.value))}
            className="rounded border border-white/15 bg-black/30 px-2 py-1.5 text-zinc-100"
          >
            <option value="">
              {accounts.length ? 'Conta onde postou…' : 'Sem contas (cadastre em Contas)'}
            </option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                @{a.handle} · {PLATFORM_LABEL[a.platform] ?? a.platform}
              </option>
            ))}
          </select>
          <input
            value={postUrl}
            onChange={(e) => setPostUrl(e.target.value)}
            placeholder="Link do post (opcional)"
            className="rounded border border-white/15 bg-black/30 px-2 py-1.5 text-zinc-100 placeholder:text-zinc-500"
          />
        </div>
        {error && <p className="text-orange-400">{error}</p>}
        <div className="flex gap-1.5">
          <button
            onClick={markPosted}
            disabled={saving}
            className="flex-1 rounded bg-pink-500 py-1.5 font-semibold text-white hover:bg-pink-400 disabled:opacity-50"
          >
            {saving ? 'Salvando…' : 'Marcar como postado'}
          </button>
          <button
            onClick={() => onUnapprove(clip.id)}
            title="Volta para a aba Aprovar"
            className="rounded border border-white/15 bg-white/5 px-3 py-1.5 hover:border-white/25 hover:bg-white/10"
          >
            Devolver
          </button>
          <button
            onClick={() => onShelf(clip.id)}
            title={
              clip.archived
                ? 'Volta para a aba Postagem'
                : 'Guarda na aba Pré-lançamento (continua ensinando a IA)'
            }
            className="rounded border border-white/15 bg-white/5 px-3 py-1.5 hover:border-white/25 hover:bg-white/10"
          >
            {clip.archived ? 'Para Postagem' : 'Pré-lançamento'}
          </button>
        </div>
      </div>
    </article>
  )
}
