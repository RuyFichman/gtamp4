import { useState } from 'react'
import { FramePreview } from './FramePreview'

type Props = {
  name: string
  detail: string
  overlayUrl: string | null
  sampleVideoUrl: string | null
  isDefault: boolean
  onMakeDefault: () => void
  onDelete?: () => void
}

export function FrameCard(p: Props) {
  const [confirm, setConfirm] = useState(false)

  return (
    <article
      className={`space-y-2 rounded-lg border p-3 text-sm ${
        p.isDefault ? 'border-pink-500/70 bg-pink-500/10' : 'border-white/10 bg-white/5'
      }`}
    >
      <FramePreview overlayUrl={p.overlayUrl} sampleVideoUrl={p.sampleVideoUrl} />
      <div>
        <p className="truncate font-semibold" title={p.name}>
          {p.name}
        </p>
        <p className="text-xs text-zinc-500">{p.detail}</p>
      </div>
      <div className="flex flex-wrap gap-1.5 text-xs">
        {p.isDefault ? (
          <span className="rounded bg-pink-500 px-2 py-1 font-semibold text-white">
            ✓ Em uso
          </span>
        ) : (
          <button
            type="button"
            onClick={p.onMakeDefault}
            className="rounded border border-white/15 bg-white/5 px-2 py-1 hover:border-white/25 hover:bg-white/10"
          >
            Usar esta
          </button>
        )}
        {p.onDelete &&
          (confirm ? (
            <>
              <button
                type="button"
                onClick={p.onDelete}
                className="rounded border border-orange-400/60 px-2 py-1 text-orange-300 hover:bg-orange-500/10"
              >
                Apagar mesmo
              </button>
              <button
                type="button"
                onClick={() => setConfirm(false)}
                className="rounded border border-white/15 bg-white/5 px-2 py-1 hover:border-white/25 hover:bg-white/10"
              >
                Não
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirm(true)}
              className="rounded border border-white/15 bg-white/5 px-2 py-1 text-zinc-400 hover:border-white/25 hover:bg-white/10"
            >
              Apagar
            </button>
          ))}
      </div>
    </article>
  )
}
