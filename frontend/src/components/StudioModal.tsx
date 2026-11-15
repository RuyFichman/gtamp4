import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { formatTime } from '../lib/format'
import type { Framing, Studio } from '../lib/types'
import { FramingControls } from './FramingControls'
import { FramingPreview } from './FramingPreview'
import { ModalShell as Shell } from './ModalShell'
import { TimeField } from './TimeField'
import { TranscriptPicker } from './TranscriptPicker'

type Props = { clipId: number; onClose: () => void; onSaved: () => void }

type Form = Framing & {
  captions: boolean
  title: string
  description: string
  hashtags: string
  start: number
  end: number
}

const sameFraming = (a: Framing, b: Framing) =>
  Math.abs(a.zoom - b.zoom) < 0.005 &&
  Math.abs(a.pan_x - b.pan_x) < 0.0005 &&
  Math.abs(a.pan_y - b.pan_y) < 0.0005

const INPUT = 'w-full rounded border border-white/15 bg-black/30 px-2 py-1.5 text-sm'

export function StudioModal({ clipId, onClose, onSaved }: Props) {
  const [studio, setStudio] = useState<Studio | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const requested = useRef<(Framing & { start: number; end: number; captions: boolean }) | null>(
    null,
  )
  const [autoBusy, setAutoBusy] = useState(false)
  const [autoMessage, setAutoMessage] = useState<string | null>(null)
  const player = useRef<HTMLVideoElement>(null)
  const stopAt = useRef<number | null>(null)

  const fill = useCallback((s: Studio) => {
    setStudio(s)
    setForm({
      title: s.clip.title,
      description: s.clip.description,
      hashtags: s.clip.hashtags.map((h) => `#${h}`).join(' '),
      start: s.clip.start_s,
      end: s.clip.end_s,
      zoom: s.clip.zoom,
      pan_x: s.clip.pan_x,
      pan_y: s.clip.pan_y,
      captions: s.clip.captions,
    })
  }, [])

  useEffect(() => {
    api
      .studio(clipId)
      .then(fill)
      .catch((err: Error) => setError(err.message))
  }, [clipId, fill])

  // while a re-render runs, poll; when it finishes, show the new version
  const rendering = studio?.render_job != null
  useEffect(() => {
    if (!rendering) return
    const id = setInterval(() => {
      api
        .studio(clipId)
        .then((s) => {
          setStudio(s)
          if (s.render_job) return
          const want = requested.current
          requested.current = null
          const ok =
            !want ||
            (Math.abs(s.clip.start_s - want.start) < 0.06 &&
              Math.abs(s.clip.end_s - want.end) < 0.06 &&
              sameFraming(s.clip, want) &&
              s.clip.captions === want.captions)
          if (ok) {
            setNotice('Nova versão pronta.')
            setForm((f) => f && { ...f, start: s.clip.start_s, end: s.clip.end_s })
          } else {
            setError('A renderização falhou. O erro aparece na fila da aba Aprovar.')
          }
          onSaved()
        })
        .catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [rendering, clipId, onSaved])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!studio || !form) {
    return (
      <Shell onClose={onClose}>
        <p className="p-6 text-zinc-400">{error ?? 'Carregando…'}</p>
      </Shell>
    )
  }

  const { clip } = studio
  const length = form.end - form.start
  const timesChanged =
    Math.abs(form.start - clip.start_s) > 0.05 || Math.abs(form.end - clip.end_s) > 0.05
  const framingChanged = !sameFraming(form, clip)
  const captionsChanged = form.captions !== clip.captions
  const needsRender = timesChanged || framingChanged || captionsChanged
  const captionStyle = studio.caption_style
  const maxEnd = studio.duration_s ?? Infinity
  const timeError =
    form.end <= form.start
      ? 'O fim precisa vir depois do início.'
      : form.end > maxEnd + 0.5
        ? `O vídeo original termina em ${formatTime(maxEnd)}.`
        : length < studio.min_s || length > studio.max_s
          ? `O corte precisa ter entre ${studio.min_s} e ${studio.max_s} segundos.`
          : null

  const set = (patch: Partial<Form>) => {
    setNotice(null)
    setForm({ ...form, ...patch })
  }

  function seek(t: number, playUntil: number | null = null) {
    const v = player.current
    if (!v) return
    v.currentTime = t
    stopAt.current = playUntil
    if (playUntil != null) v.play().catch(() => {})
  }

  function now(): number {
    return Math.round((player.current?.currentTime ?? 0) * 10) / 10
  }

  async function autoFrame() {
    if (!form) return
    setAutoBusy(true)
    setAutoMessage(null)
    try {
      const r = await api.autoframe(clipId, form.start, form.end)
      setAutoMessage(r.message)
      if (r.found) set({ zoom: r.zoom, pan_x: r.pan_x, pan_y: r.pan_y })
    } catch (err) {
      setAutoMessage((err as Error).message)
    } finally {
      setAutoBusy(false)
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!form || (timesChanged && timeError)) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const s = await api.editClip(clipId, {
        title: form.title,
        description: form.description,
        hashtags: [form.hashtags],
        start_s: form.start,
        end_s: form.end,
        zoom: form.zoom,
        pan_x: form.pan_x,
        pan_y: form.pan_y,
        captions: form.captions,
      })
      if (s.render_job) {
        const { start, end, zoom, pan_x, pan_y, captions } = form
        requested.current = { start, end, zoom, pan_x, pan_y, captions }
      }
      setStudio(s)
      setForm((f) => f && { ...f, hashtags: s.clip.hashtags.map((h) => `#${h}`).join(' ') })
      setNotice(s.render_job ? null : 'Texto salvo.')
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Shell onClose={onClose}>
      <form onSubmit={save} className="grid gap-5 p-5 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-3">
          {studio.source_video_url ? (
            <video
              ref={player}
              src={`${studio.source_video_url}#t=${clip.start_s}`}
              controls
              preload="metadata"
              onTimeUpdate={(e) => {
                const v = e.currentTarget
                if (stopAt.current != null && v.currentTime >= stopAt.current) {
                  v.pause()
                  stopAt.current = null
                }
              }}
              className="aspect-video w-full rounded bg-black"
            />
          ) : (
            <p className="rounded bg-black/40 p-4 text-sm text-zinc-400">
              O vídeo original não está mais no disco. Você ainda pode ajustar os tempos: ele será
              baixado de novo na hora de renderizar.
            </p>
          )}

          <div className="space-y-2 rounded border border-white/10 bg-white/5 p-3">
            <TimeField
              label="Início"
              value={form.start}
              onChange={(t) => set({ start: t })}
              onUseCurrent={() => set({ start: now() })}
            />
            <TimeField
              label="Fim"
              value={form.end}
              onChange={(t) => set({ end: t })}
              onUseCurrent={() => set({ end: now() })}
            />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className={timeError ? 'text-orange-400' : 'text-zinc-400'}>
                Duração: {length.toFixed(1)} s{timeError && ` · ${timeError}`}
              </span>
              <button
                type="button"
                onClick={() => seek(form.start, form.end)}
                className="ml-auto rounded bg-white/10 px-3 py-1 hover:bg-white/20"
              >
                ▶ Ouvir trecho
              </button>
              <button
                type="button"
                onClick={() => seek(Math.max(form.start, form.end - 3), form.end)}
                className="rounded border border-white/20 px-3 py-1 hover:bg-white/10"
              >
                Ouvir o final
              </button>
            </div>
          </div>

          <div className="space-y-2 rounded border border-white/10 bg-white/5 p-3">
            <p className="text-sm font-semibold">Enquadramento</p>
            <div className="grid gap-4 sm:grid-cols-[150px_1fr]">
              {studio.source_video_url && (
                <FramingPreview
                  videoUrl={studio.source_video_url}
                  time={form.start + Math.min(1, length / 2)}
                  framing={form}
                  frameUrl={studio.frame_url}
                  caption={form.captions && captionStyle.enabled ? captionStyle : null}
                />
              )}
              <FramingControls
                value={form}
                onChange={(f) => set(f)}
                onAuto={studio.source_video_url ? autoFrame : null}
                autoBusy={autoBusy}
                autoMessage={autoMessage}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.captions}
                onChange={(e) => set({ captions: e.target.checked })}
                className="accent-pink-500"
              />
              Legenda queimada neste corte
              {!captionStyle.enabled && (
                <span className="text-xs text-zinc-500">
                  (desligada para todos na aba Moldura)
                </span>
              )}
            </label>
          </div>

          <div>
            <p className="mb-1 text-sm text-zinc-400">
              Transcrição: clique no tempo para ir até ele; passe o mouse para marcar início/fim.
            </p>
            <TranscriptPicker
              segments={studio.transcript}
              start={form.start}
              end={form.end}
              onSeek={(t) => seek(t)}
              onStart={(t) => set({ start: t })}
              onEnd={(t) => set({ end: t })}
            />
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <p className="mb-1 text-xs text-zinc-400">
              Versão atual ({formatTime(clip.start_s)}–{formatTime(clip.end_s)})
            </p>
            {clip.video_url && (
              <video
                key={clip.video_url}
                src={clip.video_url}
                controls
                preload="metadata"
                className="aspect-[9/16] w-full rounded bg-black object-contain"
              />
            )}
            {studio.render_job && (
              <div className="mt-2 text-xs text-zinc-300">
                Renderizando nova versão… {studio.render_job.message}
                <div className="mt-1 h-1 overflow-hidden rounded bg-white/10">
                  <div
                    className="h-full bg-gradient-to-r from-orange-400 to-pink-500 transition-all"
                    style={{ width: `${Math.max(3, studio.render_job.progress * 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          <label className="block text-sm">
            <span className="flex justify-between text-zinc-400">
              Título <span className={form.title.length > 70 ? 'text-orange-400' : ''}>{form.title.length}/70</span>
            </span>
            <input
              value={form.title}
              onChange={(e) => set({ title: e.target.value })}
              className={INPUT}
            />
          </label>
          <label className="block text-sm">
            <span className="text-zinc-400">Descrição</span>
            <textarea
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
              rows={4}
              className={INPUT}
            />
          </label>
          <label className="block text-sm">
            <span className="text-zinc-400">Hashtags (separadas por espaço)</span>
            <input
              value={form.hashtags}
              onChange={(e) => set({ hashtags: e.target.value })}
              className={INPUT}
            />
          </label>

          {error && <p className="text-sm text-orange-400">{error}</p>}
          {notice && <p className="text-sm text-emerald-400">{notice}</p>}
          <button
            disabled={saving || (needsRender && ((timesChanged && !!timeError) || rendering))}
            className="w-full rounded bg-pink-500 py-2 font-semibold text-white hover:bg-pink-400 disabled:opacity-50"
          >
            {saving ? 'Salvando…' : needsRender ? 'Salvar e renderizar de novo' : 'Salvar texto'}
          </button>
          {needsRender && !(timesChanged && timeError) && (
            <p className="text-xs text-zinc-500">
              A versão atual continua valendo até a nova ficar pronta.
            </p>
          )}
        </div>
      </form>
    </Shell>
  )
}
