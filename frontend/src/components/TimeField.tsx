import { useState } from 'react'
import { formatTime, parseTime } from '../lib/format'

const NUDGES = [-1, -0.1, 0.1, 1]
const BTN = 'rounded border border-white/15 bg-white/5 px-1.5 py-1 text-xs hover:border-white/25 hover:bg-white/10'

type Props = {
  label: string
  value: number
  onChange: (seconds: number) => void
  onUseCurrent: () => void
}

export function TimeField({ label, value, onChange, onUseCurrent }: Props) {
  // local text so a half-typed value ("1:2") isn't clobbered; resyncs when value changes
  const [draft, setDraft] = useState<{ for: number; text: string } | null>(null)
  const text = draft && draft.for === value ? draft.text : formatTime(value)

  function commit() {
    const parsed = parseTime(text)
    setDraft(null)
    if (parsed != null && parsed !== value) onChange(parsed)
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm">
      <span className="w-10 text-zinc-400">{label}</span>
      <input
        value={text}
        onChange={(e) => setDraft({ for: value, text: e.target.value })}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
        className="w-20 rounded border border-white/15 bg-black/30 px-2 py-1 font-mono"
        aria-label={`${label} (m:ss.s)`}
      />
      {NUDGES.map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(Math.max(0, Math.round((value + n) * 10) / 10))}
          className={BTN}
        >
          {n > 0 ? `+${n}` : n}s
        </button>
      ))}
      <button type="button" onClick={onUseCurrent} className={BTN} title="Usa o ponto do player">
        Ponto atual
      </button>
    </div>
  )
}
