export type Health = {
  ok: boolean
  ffmpeg: boolean
  encoder: string
  ai: boolean
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed'

export type Job = {
  id: number
  kind: string
  status: JobStatus
  progress: number
  message: string
  error: string | null
  title: string | null
  url: string | null
  updated_at: string
}

export type ClipStatus = 'pending_review' | 'approved' | 'rejected' | 'posted'
export type ClipSort = 'potential' | 'recent' | 'views' | 'posted'

export type Source = {
  id: number
  url: string
  title: string
  channel: string
  views: number | null
  views_checked_at: string | null
}

export type Clip = {
  id: number
  title: string
  description: string
  hashtags: string[]
  potential: number
  potential_reason: string
  status: ClipStatus
  start_s: number
  end_s: number
  video_url: string | null
  created_at: string
  account_id: number | null
  post_url: string | null
  posted_at: string | null
  rendering: boolean
  source: Source
}

export type Segment = { start: number; end: number; text: string }

export type Studio = {
  clip: Clip
  source_video_url: string | null
  duration_s: number | null
  transcript: Segment[]
  render_job: Job | null
  min_s: number
  max_s: number
}

export type ClipEdit = {
  title: string
  description: string
  hashtags: string[]
  start_s: number
  end_s: number
}

export type Platform = 'tiktok' | 'instagram' | 'youtube' | 'outra'

export type AccountInput = {
  platform: Platform
  handle: string
  name: string
  notes: string
}

export type Account = AccountInput & {
  id: number
  posted_count: number
  created_at: string
}

export type RadarConfig = {
  enabled: boolean
  interval_minutes: number
  daily_limit: number
}

export type RadarStatus = {
  config: RadarConfig
  last_scan_at: string | null
  next_scan_at: string | null
  sent_last_24h: number
  scanning: boolean
}

export type RadarQueryKind = 'search' | 'channel'

export type RadarQuery = {
  id: number
  kind: RadarQueryKind
  query: string
  enabled: boolean
  last_run_at: string | null
  last_error: string | null
}

export type CandidateStatus = 'rejected' | 'waiting' | 'sent'

export type RadarCandidate = {
  id: number
  youtube_id: string
  url: string
  title: string
  channel: string
  duration_s: number | null
  views: number | null
  status: CandidateStatus
  reason: string
  found_at: string
  sent_at: string | null
}
