import type { CaptionStyle } from '../lib/types'

const SAMPLE = ['ASSIM', 'FICA', 'A', 'LEGENDA', 'DO', 'CORTE']

/**
 * Static sample of the burned-in caption over a 9:16 preview. Sizes use container units so
 * they scale like the 1080px-wide render (pipeline/captions.build_ass).
 */
export function CaptionSample({ style }: { style: CaptionStyle }) {
  const px = (v: number) => `${(v / 1080) * 100}cqw`
  const words = SAMPLE.slice(0, style.max_words).map((w) => (style.uppercase ? w : w.toLowerCase()))
  const active = Math.min(1, words.length - 1)

  return (
    <div className="pointer-events-none absolute inset-0 @container" aria-hidden>
      <p
        className="absolute inset-x-0 -translate-y-1/2 px-[5.5cqw] text-center leading-tight"
        style={{
          top: `${style.position_y * 100}%`,
          fontFamily: `"${style.font}", sans-serif`,
          fontWeight: 900,
          fontSize: px(style.size),
          color: style.color,
          WebkitTextStroke: style.outline ? `${px(style.outline * 2)} #000` : undefined,
          paintOrder: 'stroke fill',
          textShadow: `0 ${px(2)} ${px(2)} rgba(0,0,0,0.5)`,
        }}
      >
        {words.map((w, i) => (
          <span key={i}>
            {i > 0 && ' '}
            <span
              style={
                i === active
                  ? { color: style.highlight, fontSize: '1.12em', verticalAlign: 'middle' }
                  : undefined
              }
            >
              {w}
            </span>
          </span>
        ))}
      </p>
    </div>
  )
}
