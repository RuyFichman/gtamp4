type Props = {
  label: string
  value: string | number
  hint?: string
  onClick?: () => void
}

export function StatTile({ label, value, hint, onClick }: Props) {
  const body = (
    <>
      <p className="text-sm text-zinc-400">{label}</p>
      <p className="mt-1 text-3xl font-bold tabular-nums text-zinc-50">{value}</p>
      {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
    </>
  )
  const box = 'rounded-lg border border-white/10 bg-white/5 p-4 text-left'
  return onClick ? (
    <button type="button" onClick={onClick} className={`${box} transition hover:bg-white/10`}>
      {body}
    </button>
  ) : (
    <div className={box}>{body}</div>
  )
}
