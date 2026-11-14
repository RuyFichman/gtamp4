import { useState, type FormEvent } from 'react'
import { api } from '../lib/api'

export function AddVideoForm({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.addVideo(url.trim())
      setUrl('')
      onAdded()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-1">
      <div className="flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Cole o link de um vídeo do YouTube para cortar"
          className="flex-1 rounded-lg border border-white/15 bg-white/5 px-4 py-3 text-sm outline-none placeholder:text-zinc-500 focus:border-pink-500"
        />
        <button
          disabled={busy}
          className="rounded-lg bg-pink-500 px-5 text-sm font-semibold text-white transition hover:bg-pink-400 disabled:opacity-50"
        >
          Cortar
        </button>
      </div>
      {error && <p className="text-sm text-orange-400">{error}</p>}
    </form>
  )
}
