import type {
  Account,
  AutoFrame,
  AppConfig,
  AppSettings,
  CleanupPreview,
  AccountInput,
  Clip,
  ClipEdit,
  ClipSort,
  ClipStatus,
  Frames,
  Health,
  Job,
  RadarCandidate,
  RadarConfig,
  RadarQuery,
  RadarQueryKind,
  RadarStatus,
  Source,
  Stats,
  Studio,
  Warmup,
} from './types'

/** FastAPI sends a string, or a list of validation errors (422). */
function errorText(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, ''))
      .filter(Boolean)
      .join(' ')
  }
  return undefined
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    // FormData sets its own multipart boundary
    headers: typeof init?.body === 'string' ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(errorText(body?.detail) ?? `${res.status} ${res.statusText}`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  health: () => request<Health>('/health'),
  stats: () => request<Stats>('/stats'),
  autoframe: (clipId: number, start: number, end: number) =>
    request<AutoFrame>(`/clips/${clipId}/autoframe?start_s=${start}&end_s=${end}`),
  frames: () => request<Frames>('/frames'),
  uploadFrame: (name: string, file: File) => {
    const body = new FormData()
    body.append('name', name)
    body.append('file', file)
    return request<Frames>('/frames', { method: 'POST', body })
  },
  setDefaultFrame: (frameId: number | null) =>
    request<Frames>('/frames/default', { method: 'PUT', body: JSON.stringify({ frame_id: frameId }) }),
  deleteFrame: (id: number) => request<Frames>(`/frames/${id}`, { method: 'DELETE' }),
  rerenderWithFrame: () => post<{ queued: number }>('/frames/rerender'),
  warmup: () => request<Warmup[]>('/warmup'),
  startWarmup: (accountId: number) => post<Warmup>(`/warmup/${accountId}/start`),
  stopWarmup: (accountId: number) => post<Warmup>(`/warmup/${accountId}/stop`),
  checkWarmup: (accountId: number, taskKey: string, done: boolean) =>
    post<Warmup>(`/warmup/${accountId}/check`, { task_key: taskKey, done }),
  settings: () => request<AppSettings>('/settings'),
  saveSettings: (config: AppConfig) =>
    request<AppSettings>('/settings', { method: 'PUT', body: JSON.stringify(config) }),
  cleanupPreview: () => request<CleanupPreview>('/maintenance/originals'),
  cleanupOriginals: () => post<CleanupPreview>('/maintenance/originals/delete'),
  addVideo: (url: string) => post<Job>('/videos', { url }),
  refreshViews: (videoId: number) => post<Source>(`/videos/${videoId}/refresh-views`),
  jobs: () => request<Job[]>('/jobs'),
  retryJob: (id: number) => post<Job>(`/jobs/${id}/retry`),
  dismissJob: (id: number) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  clips: (status: ClipStatus, sort: ClipSort) =>
    request<Clip[]>(`/clips?status=${status}&sort=${sort}`),
  setClipStatus: (id: number, status: ClipStatus) => post<Clip>(`/clips/${id}/status`, { status }),
  markPosted: (id: number, accountId: number | null, postUrl: string) =>
    post<Clip>(`/clips/${id}/status`, {
      status: 'posted',
      account_id: accountId,
      post_url: postUrl,
    }),
  clipDownloadUrl: (id: number) => `/api/clips/${id}/download`,
  studio: (id: number) => request<Studio>(`/clips/${id}/studio`),
  editClip: (id: number, data: ClipEdit) =>
    request<Studio>(`/clips/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  accounts: () => request<Account[]>('/accounts'),
  createAccount: (data: AccountInput) => post<Account>('/accounts', data),
  updateAccount: (id: number, data: AccountInput) =>
    request<Account>(`/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAccount: (id: number) => request<void>(`/accounts/${id}`, { method: 'DELETE' }),
  radar: () => request<RadarStatus>('/radar'),
  setRadarConfig: (config: RadarConfig) =>
    request<RadarStatus>('/radar/config', { method: 'PUT', body: JSON.stringify(config) }),
  radarScan: () => post<Job>('/radar/scan'),
  radarQueries: () => request<RadarQuery[]>('/radar/queries'),
  addRadarQuery: (kind: RadarQueryKind, query: string) =>
    post<RadarQuery>('/radar/queries', { kind, query }),
  toggleRadarQuery: (id: number, enabled: boolean) =>
    request<RadarQuery>(`/radar/queries/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),
  deleteRadarQuery: (id: number) => request<void>(`/radar/queries/${id}`, { method: 'DELETE' }),
  radarCandidates: () => request<RadarCandidate[]>('/radar/candidates'),
  sendCandidate: (id: number) => post<RadarCandidate>(`/radar/candidates/${id}/send`),
}
