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
