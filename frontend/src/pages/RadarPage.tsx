import { useCallback, useEffect, useState } from 'react'
import { CandidateList } from '../components/CandidateList'
import { RadarControls } from '../components/RadarControls'
import { RadarQueries } from '../components/RadarQueries'
import { api } from '../lib/api'
import type { RadarCandidate, RadarQuery, RadarStatus } from '../lib/types'

export function RadarPage() {
  const [status, setStatus] = useState<RadarStatus | null>(null)
  const [queries, setQueries] = useState<RadarQuery[]>([])
  const [candidates, setCandidates] = useState<RadarCandidate[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    Promise.all([api.radar(), api.radarQueries(), api.radarCandidates()])
      .then(([s, q, c]) => {
        setStatus(s)
        setQueries(q)
        setCandidates(c)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    load()
    // scans run in the background; keep the list fresh while the tab is open
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xl font-bold">Radar</h2>
        <p className="text-sm text-zinc-400">
          Busca vídeos novos de GTA 6 no YouTube, filtra com IA e manda os bons para corte. Os
          cortes aparecem na aba Aprovar.
        </p>
      </section>
      {error && <p className="text-orange-400">{error}</p>}
      {status && <RadarControls status={status} onChange={setStatus} onScan={load} />}
      <RadarQueries queries={queries} onChange={load} />
      <CandidateList candidates={candidates} onChange={load} />
    </div>
  )
}
