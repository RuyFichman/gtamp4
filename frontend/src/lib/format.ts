const compact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })

export function formatViews(views: number | null): string {
  if (views == null) return 'views desconhecidas'
  return `${compact.format(views)} views no original`
}

export function formatDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('pt-BR') : '—'
}

export function formatDuration(seconds: number): string {
  const s = Math.round(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** YouTube link that opens the source video at the clip's start. */
export function sourceAt(url: string, seconds: number): string {
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}t=${Math.floor(seconds)}s`
}

export const PLATFORM_LABEL: Record<string, string> = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube Shorts',
  outra: 'Outra',
}

/** Caption pasted into TikTok/Instagram: description + hashtags. */
export function captionText(description: string, hashtags: string[]): string {
  const tags = hashtags.map((h) => `#${h}`).join(' ')
  return [description.trim(), tags].filter(Boolean).join('\n\n')
}

/** 83.4 -> "1:23.4" (Studio precision) */
export function formatTime(seconds: number): string {
  const tenths = Math.round(seconds * 10)
  const m = Math.floor(tenths / 600)
  const s = (tenths % 600) / 10
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

/** Accepts "1:23.4", "83.4" or "83,4". */
export function parseTime(text: string): number | null {
  const parts = text.trim().replace(',', '.').split(':')
  if (parts.length > 2 || parts.some((p) => p === '' || Number.isNaN(Number(p)))) return null
  const value = parts.length === 2 ? Number(parts[0]) * 60 + Number(parts[1]) : Number(parts[0])
  return value >= 0 ? value : null
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB`
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

/** "2026-11-14" -> "14/11" */
export function formatDayMonth(isoDate: string): string {
  const [, m, d] = isoDate.split('-')
  return `${d}/${m}`
}
