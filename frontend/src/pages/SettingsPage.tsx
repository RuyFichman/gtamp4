import { type FormEvent, useEffect, useState } from 'react'
import { CleanupCard } from '../components/CleanupCard'
import { Field } from '../components/Field'
import { api } from '../lib/api'
import type { AppConfig, AppSettings } from '../lib/types'

const INPUT = 'rounded border border-white/15 bg-black/30 px-2 py-1.5 text-zinc-100'
const SELECT = 'rounded border border-white/15 bg-black/30 px-2 py-1.5 text-zinc-100'
const MODELS = ['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5', 'claude-fable-5-2']

export function SettingsPage({ onOpenRadar }: { onOpenRadar: () => void }) {
  const [data, setData] = useState<AppSettings | null>(null)
  const [form, setForm] = useState<AppConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api
      .settings()
      .then((d) => {
        setData(d)
        setForm(d.config)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  if (!data || !form) return <p className="text-zinc-400">{error ?? 'Carregando…'}</p>

  const set = (patch: Partial<AppConfig>) => {
    setSaved(false)
    setForm({ ...form, ...patch })
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setError(null)
    try {
      const d = await api.saveSettings(form)
      setData(d)
      setForm(d.config)
      setSaved(true)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <section className="space-y-2 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
        <h3 className="font-semibold">Chave da API do Claude</h3>
        {data.ai_key_set ? (
          <p className="text-emerald-400">Configurada. A IA está ligada.</p>
        ) : (
          <p className="text-amber-300">
            Sem chave: os cortes são escolhidos pela heurística de volume e o Radar filtra só pelo
            título.
          </p>
        )}
        <p className="text-zinc-400">
          Por segurança a chave não aparece nem é editada aqui. Ela fica no arquivo{' '}
          <code className="text-zinc-200">.env</code> (linha{' '}
          <code className="text-zinc-200">ANTHROPIC_API_KEY=…</code>) e vale depois de reiniciar o
          backend.
          {data.env_files.length > 0 && <> Arquivo em uso: {data.env_files.join(', ')}.</>}
        </p>
      </section>

      <form onSubmit={save} className="space-y-6">
        <section className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
          <h3 className="font-semibold">Cortes</h3>
          <Field label="Duração mínima (s)" hint="A IA não sugere cortes mais curtos que isso.">
            <input
              type="number"
              min={5}
              max={60}
              value={form.min_clip_s}
              onChange={(e) => set({ min_clip_s: Number(e.target.value) })}
              className={`${INPUT} w-24`}
            />
          </Field>
          <Field label="Duração máxima (s)" hint="TikTok e Reels rendem melhor com até ~60–75 s.">
            <input
              type="number"
              min={15}
              max={180}
              value={form.max_clip_s}
              onChange={(e) => set({ max_clip_s: Number(e.target.value) })}
              className={`${INPUT} w-24`}
            />
          </Field>
          <Field label="Máx. de cortes por vídeo" hint="Mais cortes = mais tempo de render.">
            <input
              type="number"
              min={1}
              max={10}
              value={form.max_clips}
              onChange={(e) => set({ max_clips: Number(e.target.value) })}
              className={`${INPUT} w-24`}
            />
          </Field>
          <p className="text-xs text-zinc-500">
            Vale para vídeos processados daqui para frente. No Estúdio você ainda pode ajustar
            qualquer corte entre 3 e 180 s.
          </p>
        </section>

        <section className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
          <h3 className="font-semibold">Processamento</h3>
          <Field
            label="Encoder de vídeo"
            hint={
              data.amf_available
                ? 'Sua placa AMD (AMF) está funcionando: é bem mais rápida.'
                : 'AMF não respondeu nesta máquina: o automático usa a CPU.'
            }
          >
            <select
              value={form.video_encoder}
              onChange={(e) => set({ video_encoder: e.target.value as AppConfig['video_encoder'] })}
              className={SELECT}
            >
              <option value="auto">Automático (AMD se der, senão CPU)</option>
              <option value="h264_amf">Placa AMD (h264_amf)</option>
              <option value="libx264">CPU (libx264, mais lento)</option>
            </select>
          </Field>
          <Field
            label="Modelo do Whisper"
            hint="Só usado quando o vídeo não tem legenda no YouTube. Maior = mais preciso e mais lento (CPU)."
          >
            <select
              value={form.whisper_model}
              onChange={(e) => set({ whisper_model: e.target.value as AppConfig['whisper_model'] })}
              className={SELECT}
            >
              <option value="tiny">tiny (rápido, erra mais)</option>
              <option value="base">base</option>
              <option value="small">small (recomendado)</option>
              <option value="medium">medium (lento)</option>
            </select>
          </Field>
        </section>

        <section className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4 text-sm">
          <h3 className="font-semibold">Modelos de IA</h3>
          <datalist id="claude-models">
            {MODELS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <Field label="Escolha dos cortes" hint={`Padrão: ${data.defaults.model_writer}`}>
            <input
              list="claude-models"
              value={form.model_writer}
              onChange={(e) => set({ model_writer: e.target.value.trim() })}
              className={INPUT}
            />
          </Field>
          <Field label="Triagem do Radar" hint={`Padrão: ${data.defaults.model_triage} (barato)`}>
            <input
              list="claude-models"
              value={form.model_triage}
              onChange={(e) => set({ model_triage: e.target.value.trim() })}
              className={INPUT}
            />
          </Field>
          <p className="text-xs text-zinc-500">
            O intervalo e o limite diário do Radar ficam na{' '}
            <button type="button" onClick={onOpenRadar} className="text-cyan-300 hover:underline">
              aba Radar
            </button>
            .
          </p>
        </section>

        <div className="flex items-center gap-3">
          <button className="rounded bg-pink-500 px-5 py-2 font-semibold text-white hover:bg-pink-400">
            Salvar ajustes
          </button>
          <button
            type="button"
            onClick={() => set(data.defaults)}
            className="rounded border border-white/15 bg-white/5 px-4 py-2 text-sm hover:border-white/25 hover:bg-white/10"
          >
            Voltar ao padrão
          </button>
          {saved && <span className="text-sm text-emerald-400">Salvo.</span>}
          {error && <span className="text-sm text-orange-400">{error}</span>}
        </div>
      </form>

      <CleanupCard />

      <p className="text-xs text-zinc-500">Pasta de dados: {data.data_dir}</p>
    </div>
  )
}
