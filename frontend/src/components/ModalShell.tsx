import type { ReactNode } from 'react'

export function ModalShell({
  title,
  onClose,
  children,
}: {
  title?: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-2 sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="mx-auto max-w-6xl rounded-xl border border-white/15 bg-indigo-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <h2 className="text-lg font-bold">{title ?? 'Estúdio'}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-zinc-400 hover:bg-white/10 hover:text-white"
            aria-label="Fechar"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
