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
export type RejectReason = { key: string; label: string }

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
  reject_reason: string | null
  start_s: number
  end_s: number
  zoom: number
  pan_x: number
  pan_y: number
  captions: boolean
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
  frame_url: string | null
  caption_style: CaptionStyle
}

export type ClipEdit = {
  title: string
  description: string
  hashtags: string[]
  start_s: number
  end_s: number
  zoom: number
  pan_x: number
  pan_y: number
  captions?: boolean
}

export type Framing = { zoom: number; pan_x: number; pan_y: number }

export type AutoFrame = Framing & { found: boolean; message: string }

export type CaptionStyle = {
  enabled: boolean
  font: string
  size: number
  color: string
  highlight: string
  outline: number
  position_y: number
  max_words: number
  uppercase: boolean
}

export type Captions = { style: CaptionStyle; defaults: CaptionStyle; fonts: string[] }

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
  published_at: string | null
  subscribers: number | null
  /** views per hour since publication, measured when the Radar found it */
  views_per_hour: number | null
  status: CandidateStatus
  reason: string
  found_at: string
  sent_at: string | null
  /** 1 = next to be sent (waiting only) */
  queue_position: number | null
  /** the editor's decisions on clips from this channel */
  channel_record: { approved: number; decided: number } | null
}

export type DayStat = { date: string; generated: number; posted: number }

export type Stats = {
  clips: { pending_review: number; approved: number; rejected: number; posted: number; total: number }
  approval_rate: number | null
  avg_potential_kept: number | null
  avg_potential_rejected: number | null
  source_videos: number
  days: DayStat[]
  accounts: {
    id: number
    handle: string
    platform: string
    posted: number
    last_posted_at: string | null
  }[]
  jobs: { queued: number; running: number; failed: number; done_24h: number }
  radar: {
    enabled: boolean
    sent_24h: number
    daily_limit: number
    found_24h: number
    waiting: number
    last_scan_at: string | null
  }
  disk: { videos_bytes: number; videos_files: number; clips_bytes: number }
}

export type AppConfig = {
  min_clip_s: number
  max_clip_s: number
  max_clips: number
  video_encoder: 'auto' | 'h264_amf' | 'libx264'
  whisper_model: 'tiny' | 'base' | 'small' | 'medium'
  model_writer: string
  model_triage: string
}

export type AppSettings = {
  config: AppConfig
  defaults: AppConfig
  ai_key_set: boolean
  env_files: string[]
  amf_available: boolean
  data_dir: string
}

export type CleanupPreview = { files: number; bytes: number; blocked: string | null }

export type WarmupTask = { key: string; text: string; once: boolean; done: boolean }
export type WarmupDay = { date: string; day_number: number; done: number; total: number }

export type Warmup = {
  account_id: number
  handle: string
  platform: string
  started_on: string | null
  day_number: number | null
  finished: boolean
  phase_title: string | null
  phase_tip: string | null
  tasks: WarmupTask[]
  days: WarmupDay[]
}

export type Frame = {
  id: number
  name: string
  url: string
  is_default: boolean
  width: number | null
  height: number | null
}

export type Frames = { frames: Frame[]; live_clips: number }
