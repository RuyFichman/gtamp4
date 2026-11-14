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
export type ClipSort = 'potential' | 'recent' | 'views'

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
  source: Source
}
