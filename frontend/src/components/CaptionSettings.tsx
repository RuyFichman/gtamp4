import { useState } from 'react'
import { api } from '../lib/api'
import type { CaptionStyle, Captions } from '../lib/types'
import { FramePreview } from './FramePreview'
import { RangeField } from './RangeField'

type Props = {
  data: Captions
  sampleVideoUrl: string | null
  frameUrl: string | null
  onSaved: (c: Captions) => void
}

const same = (a: CaptionStyle, b: CaptionStyle) => JSON.stringify(a) === JSON.stringify(b)

export function CaptionSettings({ data, sampleVideoUrl, frameUrl, onSaved }: Props) {
  const [form, setForm] = useState<CaptionStyle>(data.style)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const set = (patch: Partial<CaptionStyle>) => {
    setNotice(null)
    setForm({ ...form, ...patch })
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const out = await api.saveCaptions(form)
      setForm(out.style)
      onSaved(out)
      setNotice('Legenda salva. Vale para os próximos cortes e re-renders.')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
      <div>
        <h3 className="font-semibold">Legenda queimada</h3>
        <p className="max-w-3xl text-zinc-400">
          Texto grande gravado no vídeo, com a palavra falada destacada (estilo TikTok). Sempre no
          idioma original do vídeo. O Whisper ouve cada corte para pegar o tempo de cada palavra.
          Dá para desligar por corte no Estúdio.
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-[170px_1fr]">
        <FramePreview
          overlayUrl={frameUrl}
          sampleVideoUrl={sampleVideoUrl}
          caption={form.enabled ? form : null}
        />

        <div className="max-w-xl space-y-2.5">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => set({ enabled: e.target.checked })}
              className="accent-pink-500"
            />
            Colocar legenda nos cortes
          </label>

          <fieldset disabled={!form.enabled} className="space-y-2.5 disabled:opacity-50">
            <label className="grid grid-cols-[110px_1fr] items-center gap-2">
              <span className="text-zinc-400">Fonte</span>
              <select
                value={form.font}
                onChange={(e) => set({ font: e.target.value })}
                className="rounded border border-white/15 bg-black/30 px-2 py-1"
              >
                {data.fonts.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
            <RangeField
              label="Tamanho"
              min={40}
              max={160}
              step={2}
              value={form.size}
              shown={`${form.size}`}
              onChange={(size) => set({ size })}
            />
            <RangeField
              label="Contorno"
              min={0}
              max={16}
              step={1}
              value={form.outline}
              shown={`${form.outline}`}
              onChange={(outline) => set({ outline })}
            />
            <RangeField
              label="Altura"
              min={0.1}
              max={0.9}
              step={0.01}
              value={form.position_y}
              shown={`${Math.round(form.position_y * 100)}%`}
              onChange={(position_y) => set({ position_y })}
            />
            <RangeField
              label="Palavras"
              min={1}
              max={6}
              step={1}
              value={form.max_words}
              shown={`${form.max_words}`}
              onChange={(max_words) => set({ max_words })}
            />
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2">
                <span className="text-zinc-400">Cor</span>
                <input
                  type="color"
                  value={form.color}
                  onChange={(e) => set({ color: e.target.value.toUpperCase() })}
                  className="h-7 w-10 cursor-pointer rounded bg-transparent"
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-zinc-400">Destaque</span>
                <input
                  type="color"
                  value={form.highlight}
                  onChange={(e) => set({ highlight: e.target.value.toUpperCase() })}
                  className="h-7 w-10 cursor-pointer rounded bg-transparent"
                />
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.uppercase}
                  onChange={(e) => set({ uppercase: e.target.checked })}
                  className="accent-pink-500"
                />
                MAIÚSCULAS
              </label>
            </div>
          </fieldset>
          <p className="text-xs text-zinc-500">
            "Altura" é o centro do texto (0% = topo). A moldura costuma ocupar as faixas de cima e
            de baixo; deixe a legenda entre elas.
          </p>

          {error && <p className="text-orange-400">{error}</p>}
          {notice && <p className="text-emerald-400">{notice}</p>}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={save}
              disabled={saving || same(form, data.style)}
              className="rounded bg-pink-500 px-3 py-1 font-semibold text-white hover:bg-pink-400 disabled:opacity-50"
            >
              {saving ? 'Salvando…' : 'Salvar legenda'}
            </button>
            <button
              type="button"
              onClick={() => set(data.defaults)}
              disabled={same(form, data.defaults)}
              className="rounded border border-white/20 px-3 py-1 hover:bg-white/10 disabled:opacity-40"
            >
              Voltar ao padrão
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
