import { api } from '../lib/api'
import type { Job } from '../lib/types'

const LABEL: Record<Job['status'], string> = {
  queued: 'Na fila',
  running: 'Processando',
  done: 'Pronto',
  failed: 'Falhou',
}

export function JobList({ jobs, onChange }: { jobs: Job[]; onChange: () => void }) {
  if (jobs.length === 0) return null
  return (
    <ul className="divide-y divide-white/10 rounded-lg border border-white/10 bg-white/5">
      {jobs.map((job) => (
        <li key={job.id} className="px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{job.title ?? job.url}</p>
              <p
                className={`text-xs ${job.status === 'failed' ? 'text-orange-400' : 'text-zinc-400'}`}
              >
                {LABEL[job.status]}
                {job.message && job.message !== LABEL[job.status] && `: ${job.message}`}
              </p>
              {job.error && (
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-orange-300/80">
                  {job.error}
                </pre>
              )}
            </div>
            {job.status === 'failed' && (
              <div className="flex shrink-0 gap-2 text-xs">
                <button
                  onClick={() => api.retryJob(job.id).then(onChange)}
                  className="rounded border border-white/20 px-2 py-1 hover:bg-white/10"
                >
                  Tentar de novo
                </button>
                <button
                  onClick={() => api.dismissJob(job.id).then(onChange)}
                  className="rounded border border-white/20 px-2 py-1 hover:bg-white/10"
                >
                  Remover
                </button>
              </div>
            )}
          </div>
          {(job.status === 'running' || job.status === 'queued') && (
            <div className="mt-2 h-1 overflow-hidden rounded bg-white/10">
              <div
                className="h-full bg-gradient-to-r from-orange-400 to-pink-500 transition-all"
                style={{ width: `${Math.max(3, job.progress * 100)}%` }}
              />
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
