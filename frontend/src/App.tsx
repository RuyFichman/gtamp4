import { useState } from 'react'
import { StatusBar } from './components/StatusBar'
import { AccountsPage } from './pages/AccountsPage'
import { ApprovePage } from './pages/ApprovePage'
import { PostPage } from './pages/PostPage'

const TABS = [
  'Painel',
  'Aprovar',
  'Postagem',
  'Contas',
  'Aquecimento',
  'Radar',
  'Moldura',
  'Ajustes',
] as const
type Tab = (typeof TABS)[number]
const READY: Tab[] = ['Aprovar', 'Postagem', 'Contas']

export default function App() {
  const [tab, setTab] = useState<Tab>('Aprovar')
  const [pending, setPending] = useState(0)

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="bg-gradient-to-r from-orange-400 to-pink-500 bg-clip-text text-3xl font-bold text-transparent">
            gtamp4
          </h1>
          <p className="text-sm text-zinc-400">Cortes de GTA 6 para TikTok e Instagram</p>
        </div>
        <StatusBar />
      </header>

      <nav className="mt-6 flex gap-1 overflow-x-auto border-b border-white/10 [scrollbar-width:none]">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-1.5 whitespace-nowrap px-4 py-2 text-sm font-medium transition ${
              tab === t
                ? 'border-b-2 border-pink-500 text-pink-400'
                : 'text-zinc-400 hover:text-zinc-100'
            }`}
          >
            {t}
            {t === 'Aprovar' && pending > 0 && (
              <span className="rounded-full bg-pink-500 px-1.5 text-xs text-white">{pending}</span>
            )}
          </button>
        ))}
      </nav>

      <main className="mt-6">
        {/* kept mounted so polling and the pending badge keep working on other tabs */}
        <div hidden={tab !== 'Aprovar'}>
          <ApprovePage active={tab === 'Aprovar'} onCountChange={setPending} />
        </div>
        {/* mounted on open so they always show fresh data */}
        {tab === 'Postagem' && <PostPage />}
        {tab === 'Contas' && <AccountsPage />}
        {!READY.includes(tab) && <p className="text-zinc-400">Aba “{tab}” em construção.</p>}
      </main>
    </div>
  )
}
