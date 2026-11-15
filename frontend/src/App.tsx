import { useState } from 'react'
import { StatusBar } from './components/StatusBar'
import { AccountsPage } from './pages/AccountsPage'
import { DashboardPage } from './pages/DashboardPage'
import { FramePage } from './pages/FramePage'
import { ApprovePage } from './pages/ApprovePage'
import { PostPage } from './pages/PostPage'
import { RadarPage } from './pages/RadarPage'
import { SettingsPage } from './pages/SettingsPage'
import { WarmupPage } from './pages/WarmupPage'

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

export default function App() {
  const [tab, setTab] = useState<Tab>('Aprovar')
  const [pending, setPending] = useState(0)

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="bg-gradient-to-r from-orange-400 to-pink-500 bg-clip-text text-3xl font-extrabold tracking-tight text-transparent">
            gtamp4
          </h1>
          <p className="mt-0.5 text-sm text-zinc-400">Cortes de GTA 6 para TikTok e Instagram</p>
        </div>
        <StatusBar />
      </header>

      <nav className="sticky top-0 z-40 mt-4 flex gap-1 overflow-x-auto border-b border-white/10 bg-zinc-950/50 pt-2 backdrop-blur-md [scrollbar-width:none]">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px flex items-center gap-1.5 whitespace-nowrap rounded-t-md border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t
                ? 'border-pink-500 text-white'
                : 'border-transparent text-zinc-400 hover:bg-white/5 hover:text-zinc-100'
            }`}
          >
            {t}
            {t === 'Aprovar' && pending > 0 && (
              <span className="min-w-5 rounded-full bg-pink-500 px-1.5 text-center text-xs font-semibold leading-5 tabular-nums text-white">
                {pending}
              </span>
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
        {tab === 'Painel' && <DashboardPage onNavigate={setTab} />}
        {tab === 'Postagem' && <PostPage />}
        {tab === 'Contas' && <AccountsPage />}
        {tab === 'Aquecimento' && <WarmupPage onOpenAccounts={() => setTab('Contas')} />}
        {tab === 'Radar' && <RadarPage />}
        {tab === 'Moldura' && <FramePage />}
        {tab === 'Ajustes' && <SettingsPage onOpenRadar={() => setTab('Radar')} />}
      </main>
    </div>
  )
}
