import { formatDateTime, PLATFORM_LABEL } from '../lib/format'
import type { Account, Clip } from '../lib/types'

type Props = { clips: Clip[]; accounts: Account[]; onUndo: (id: number) => void }

export function PostedList({ clips, accounts, onUndo }: Props) {
  if (clips.length === 0) return <p className="mt-3 text-sm text-zinc-500">Nada postado ainda.</p>
  const byId = new Map(accounts.map((a) => [a.id, a]))

  return (
    <ul className="mt-3 divide-y divide-white/10 rounded-lg border border-white/10 bg-white/5 text-sm">
      {clips.map((clip) => {
        const account = clip.account_id ? byId.get(clip.account_id) : undefined
        return (
          <li key={clip.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5">
            <span className="min-w-0 flex-1 truncate font-medium">{clip.title}</span>
            <span className="text-zinc-400">
              {account
                ? `@${account.handle} · ${PLATFORM_LABEL[account.platform] ?? account.platform}`
                : 'sem conta'}
            </span>
            <span className="text-zinc-400">{formatDateTime(clip.posted_at)}</span>
            {clip.post_url && (
              <a
                href={clip.post_url}
                target="_blank"
                rel="noreferrer"
                className="text-cyan-300 underline"
              >
                ver post
              </a>
            )}
            <button
              onClick={() => onUndo(clip.id)}
              title="Volta para a fila de postagem"
              className="rounded border border-white/20 px-2 py-0.5 text-xs hover:bg-white/10"
            >
              Desfazer
            </button>
          </li>
        )
      })}
    </ul>
  )
}
