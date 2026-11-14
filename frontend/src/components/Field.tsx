import type { ReactNode } from 'react'

/** Label + control + optional hint, two columns on wide screens. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1 sm:grid-cols-[220px_1fr] sm:items-center">
      <span className="text-zinc-300">{label}</span>
      <span className="flex flex-col gap-1">
        {children}
        {hint && <span className="text-xs text-zinc-500">{hint}</span>}
      </span>
    </label>
  )
}
