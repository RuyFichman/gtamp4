import { useState } from 'react'

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle')

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setState('ok')
    } catch {
      setState('fail')
    }
    setTimeout(() => setState('idle'), 1500)
  }

  return (
    <button
      type="button"
      onClick={copy}
      disabled={!text}
      className="rounded border border-white/20 px-2 py-1 hover:bg-white/10 disabled:opacity-40"
    >
      {state === 'ok' ? 'Copiado!' : state === 'fail' ? 'Não deu pra copiar' : label}
    </button>
  )
}
