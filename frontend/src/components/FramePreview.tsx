import type { CaptionStyle } from '../lib/types'
import { CaptionSample } from './CaptionSample'

/** 9:16 mock of the final clip: sample video (or a placeholder layout) under the overlay. */
type Props = {
  overlayUrl: string | null
  sampleVideoUrl: string | null
  caption?: CaptionStyle | null
  className?: string
}

export function FramePreview({ overlayUrl, sampleVideoUrl, caption, className = '' }: Props) {
  return (
    <div
      className={`relative aspect-[9/16] overflow-hidden rounded-md bg-zinc-900 ring-1 ring-white/10 ${className}`}
    >
      {sampleVideoUrl ? (
        <video
          src={sampleVideoUrl}
          muted
          loop
          autoPlay
          playsInline
          className="absolute inset-0 size-full object-cover"
        />
      ) : (
        // same geometry as the render: 16:9 video centered on a blurred fill
        <div className="absolute inset-0 bg-gradient-to-b from-indigo-900/60 via-zinc-800 to-pink-900/50">
          <div className="absolute inset-x-0 top-1/2 grid aspect-video -translate-y-1/2 place-items-center bg-zinc-700/80 text-xs text-zinc-300">
            vídeo 16:9
          </div>
        </div>
      )}
      {overlayUrl && (
        <img src={overlayUrl} alt="" className="pointer-events-none absolute inset-0 size-full" />
      )}
      {caption && <CaptionSample style={caption} />}
    </div>
  )
}
