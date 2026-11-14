/** Label + range input + current value, in one row. */
export function RangeField(p: {
  label: string
  min: number
  max: number
  step: number
  value: number
  shown: string
  onChange: (v: number) => void
}) {
  return (
    <label className="grid grid-cols-[110px_1fr_48px] items-center gap-2 text-sm">
      <span className="text-zinc-400">{p.label}</span>
      <input
        type="range"
        min={p.min}
        max={p.max}
        step={p.step}
        value={p.value}
        onChange={(e) => p.onChange(Number(e.target.value))}
        className="accent-pink-500"
      />
      <span className="text-right tabular-nums text-zinc-300">{p.shown}</span>
    </label>
  )
}
