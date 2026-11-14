import { type FormEvent, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { Frames } from '../lib/types'

export function FrameUpload({ onUploaded }: { onUploaded: (f: Frames) => void }) {
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      onUploaded(await api.uploadFrame(name || file.name.replace(/\.png$/i, ''), file))
      setName('')
      setFile(null)
      if (input.current) input.current.value = ''
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm"
    >
      <h3 className="font-semibold">Nova moldura</h3>
      <p className="text-zinc-400">
        PNG vertical <strong>1080x1920</strong> com <strong>fundo transparente</strong> onde o
        vídeo aparece. O vídeo 16:9 fica na faixa do meio (de y=656 a y=1264); use as bordas de
        cima e de baixo para logo, @ da conta ou chamada.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nome (ex.: Neon VI)"
          className="rounded border border-white/15 bg-black/30 px-2 py-1.5"
        />
        <input
          ref={input}
          type="file"
          accept="image/png"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-zinc-300 file:mr-2 file:rounded file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-zinc-100"
        />
        <button
          disabled={!file || busy}
          className="rounded bg-pink-500 px-4 py-1.5 font-semibold text-white hover:bg-pink-400 disabled:opacity-40"
        >
          {busy ? 'Enviando…' : 'Enviar'}
        </button>
      </div>
      {error && <p className="text-orange-400">{error}</p>}
    </form>
  )
}
