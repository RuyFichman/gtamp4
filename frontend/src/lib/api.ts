import type { Clip, ClipSort, ClipStatus, Health, Job, Source } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  health: () => request<Health>('/health'),
  addVideo: (url: string) => post<Job>('/videos', { url }),
  refreshViews: (videoId: number) => post<Source>(`/videos/${videoId}/refresh-views`),
  jobs: () => request<Job[]>('/jobs'),
  retryJob: (id: number) => post<Job>(`/jobs/${id}/retry`),
  dismissJob: (id: number) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  clips: (status: ClipStatus, sort: ClipSort) =>
    request<Clip[]>(`/clips?status=${status}&sort=${sort}`),
  setClipStatus: (id: number, status: ClipStatus) => post<Clip>(`/clips/${id}/status`, { status }),
  clipDownloadUrl: (id: number) => `/api/clips/${id}/download`,
}
