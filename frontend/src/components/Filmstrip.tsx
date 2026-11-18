import { useEffect, useRef, useState } from 'react'

type Props = { videoUrl: string; from: number; to: number; count: number; height: number }

const DEBOUNCE_MS = 250

/**
 * Thumbnails of the source between `from` and `to`, grabbed client-side from a hidden video
 * (same origin, so the canvas is not tainted). Regenerated when the window changes.
 */
export function Filmstrip({ videoUrl, from, to, count, height }: Props) {
  const [thumbs, setThumbs] = useState<string[]>([])
  const grabber = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    if (count < 1 || to <= from) return
    let cancelled = false
    const timer = setTimeout(async () => {
      const v = grabber.current ?? document.createElement('video')
      grabber.current = v
      v.muted = true
      v.preload = 'auto'
      if (v.src !== new URL(videoUrl, location.href).href) v.src = videoUrl
      if (v.readyState < 1) {
        await new Promise<void>((ok, fail) => {
          v.addEventListener('loadedmetadata', () => ok(), { once: true })
          v.addEventListener('error', () => fail(new Error('video')), { once: true })
        }).catch(() => null)
      }
      if (cancelled || !v.videoWidth) return
      const canvas = document.createElement('canvas')
      canvas.height = height * 2 // crisp on high-DPI screens
      canvas.width = Math.round((canvas.height * v.videoWidth) / v.videoHeight)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const out: string[] = []
      const step = (to - from) / count
      for (let i = 0; i < count && !cancelled; i++) {
        v.currentTime = from + step * (i + 0.5)
        await new Promise((ok) => v.addEventListener('seeked', ok, { once: true }))
        if (cancelled) return
        ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
        out.push(canvas.toDataURL('image/jpeg', 0.6))
        setThumbs([...out])
      }
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [videoUrl, from, to, count, height])

  useEffect(
    () => () => {
      grabber.current?.removeAttribute('src')
      grabber.current = null
    },
    [],
  )

  return (
    <div className="absolute inset-0 flex overflow-hidden">
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="h-full flex-1 bg-white/5 bg-cover bg-center"
          style={thumbs[i] ? { backgroundImage: `url(${thumbs[i]})` } : undefined}
        />
      ))}
    </div>
  )
}
