import { useEffect, useRef, useState } from 'react'
import type { CaptionStyle, Framing } from '../lib/types'
import { CaptionSample } from './CaptionSample'

type Props = {
  videoUrl: string
  time: number
  framing: Framing
  frameUrl: string | null
  caption: CaptionStyle | null
}

const BOX_RATIO = 16 / 9 // box height / width (9:16 output)

/**
 * Same geometry as the ffmpeg render (pipeline/cut.py): blurred fill, middle video scaled to
 * zoom x box width, cropped to the box and positioned by pan (-1..1), frame on top.
 */
export function FramingPreview({ videoUrl, time, framing, frameUrl, caption }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const bg = useRef<HTMLVideoElement>(null)
  const fg = useRef<HTMLVideoElement>(null)
  const [width, setWidth] = useState(0)
  const [aspect, setAspect] = useState(16 / 9) // source width / height

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    for (const v of [bg.current, fg.current]) if (v && v.readyState > 0) v.currentTime = time
  }, [time])

  const height = width * BOX_RATIO
  const fgW = width * framing.zoom
  const fgH = fgW / aspect
  const viewW = Math.min(fgW, width)
  const viewH = Math.min(fgH, height)
  const offX = ((fgW - viewW) / 2) * (1 + framing.pan_x)
  const offY = ((fgH - viewH) / 2) * (1 + framing.pan_y)

  const onMeta = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const v = e.currentTarget
    if (v.videoWidth) setAspect(v.videoWidth / v.videoHeight)
    v.currentTime = time
  }

  return (
    <div
      ref={box}
      className="relative aspect-[9/16] w-full overflow-hidden rounded bg-black"
      aria-label="Prévia do enquadramento"
    >
      <video
        ref={bg}
        src={videoUrl}
        muted
        preload="auto"
        onLoadedMetadata={onMeta}
        className="absolute inset-0 size-full scale-110 object-cover blur-md"
      />
      <div
        className="absolute overflow-hidden"
        style={{ left: (width - viewW) / 2, top: (height - viewH) / 2, width: viewW, height: viewH }}
      >
        <video
          ref={fg}
          src={videoUrl}
          muted
          preload="auto"
          onLoadedMetadata={onMeta}
          className="absolute max-w-none"
          style={{ left: -offX, top: -offY, width: fgW, height: fgH }}
        />
      </div>
      {frameUrl && (
        <img src={frameUrl} alt="" className="pointer-events-none absolute inset-0 size-full" />
      )}
      {caption && <CaptionSample style={caption} />}
    </div>
  )
}
