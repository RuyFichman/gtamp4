import { useCallback, useEffect, useRef, useState } from 'react'
import { AddVideoForm } from '../components/AddVideoForm'
import { ClipCard } from '../components/ClipCard'
import { JobList } from '../components/JobList'
import { api } from '../lib/api'
import type { Clip, ClipSort, ClipStatus, Job, Source } from '../lib/types'

export function ApprovePage({ onCountChange }: { onCountChange: (n: number) => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [sort, setSort] = useState<ClipSort>('potential')
  const doneIds = useRef(new Set<number>())

  const loadClips = useCallback(() => {
    api.clips('pending_review', sort).then(setClips).catch(() => {})
  }, [sort])

  const loadJobs = useCallback(() => {
    api
      .jobs()
      .then((list) => {
        setJobs(list)
        // a job just finished: new clips may exist
        const finished = list.filter((j) => j.status === 'done' && !doneIds.current.has(j.id))
        finished.forEach((j) => doneIds.current.add(j.id))
        if (finished.length) loadClips()
      })
      .catch(() => {})
  }, [loadClips])

  useEffect(loadClips, [loadClips])
  useEffect(() => {
    loadJobs()
    const id = setInterval(loadJobs, 2000)
    return () => clearInterval(id)
  }, [loadJobs])
  useEffect(() => onCountChange(clips.length), [clips.length, onCountChange])

  function changeStatus(id: number, status: ClipStatus) {
    setClips((list) => list.filter((c) => c.id !== id))
    api.setClipStatus(id, status).catch(loadClips)
  }

  function updateSource(source: Source) {
    setClips((list) => list.map((c) => (c.source.id === source.id ? { ...c, source } : c)))
  }

  return (
    <div className="space-y-6">
      <AddVideoForm onAdded={loadJobs} />
      <JobList jobs={jobs.filter((j) => j.status !== 'done')} onChange={loadJobs} />

      <section>
        <h2 className="text-xl font-bold">Cortes esperando você</h2>
        <p className="text-sm text-zinc-400">
          Aprovado vai para a fila de postagem. Recusado some daqui.
        </p>
        <div className="mt-3 flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2 text-zinc-400">
            Ordenar
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as ClipSort)}
              className="rounded border border-white/15 bg-indigo-950 px-2 py-1 text-zinc-100"
            >
              <option value="potential">Maior potencial</option>
              <option value="recent">Mais recentes</option>
              <option value="views">Mais views no original</option>
            </select>
          </label>
          <span className="text-zinc-400">{clips.length} corte(s)</span>
        </div>

        {clips.length === 0 ? (
          <p className="mt-8 text-center text-zinc-500">
            Nenhum corte esperando. Cole um link acima para começar.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {clips.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                onStatus={changeStatus}
                onSource={updateSource}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
