import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { Health } from '../lib/types'

function Pill({ on, label }: { on: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs">
      <span className={`size-2 rounded-full ${on ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
      {label}
    </span>
  )
}

export function StatusBar() {
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    const check = () =>
      api
        .health()
        .then((h) => {
          setHealth(h)
          setOffline(false)
        })
        .catch(() => setOffline(true))
    check()
    const id = setInterval(check, 5000)
    return () => clearInterval(id)
  }, [])

  if (offline) {
    return (
      <p className="text-sm text-orange-400">
        Sem conexão com o app. Confira se o terminal do backend está aberto.
      </p>
    )
  }
  if (!health) return null
  return (
    <div className="flex flex-wrap gap-2">
      <Pill on={health.ai} label={health.ai ? 'IA ligada' : 'IA sem chave'} />
      <Pill on={health.ffmpeg} label={`ffmpeg · ${health.encoder}`} />
    </div>
  )
}
