"""Choose the best clip windows of a video. Claude when a key is set, a loudness heuristic otherwise."""

import anthropic
import numpy as np
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline.energy import mean_between
from app.pipeline.types import Segment

MIN_CLIP_S = 12.0
MAX_CLIP_S = 75.0
MAX_CLIPS = 5


class ClipIdea(BaseModel):
    start_s: float
    end_s: float
    potential: int
    reason: str
    title: str
    description: str
    hashtags: list[str]


class ClipPlan(BaseModel):
    # filled first so the model commits to the output language before writing any text
    video_language: str
    clips: list[ClipIdea]


SYSTEM_PROMPT = f"""Você é editor de cortes virais de GTA 6 para TikTok e Instagram Reels.
Recebe a transcrição com timestamps de um vídeo do YouTube e escolhe os melhores trechos
para virar cortes verticais curtos.

Regras para cada corte:
- Entre {MIN_CLIP_S:.0f} e {MAX_CLIP_S:.0f} segundos; comece e termine em frases completas.
- Precisa fazer sentido sozinho, sem o resto do vídeo, e prender a atenção nos 2 primeiros segundos.
- Prefira: revelações, notícias, opiniões fortes, polêmica, humor, reações e momentos de fala agitada.
  A coluna "energia" (0-9) indica volume da voz; energia alta costuma ser um bom sinal.
- potential: nota de 0 a 100 do potencial de viralizar. Seja exigente; reserve 90+ para trechos excepcionais.
- reason: uma frase curta explicando a nota, em português do Brasil (só o editor lê).
- title, description e hashtags SEMPRE no idioma falado no vídeo, mesmo que estas instruções
  estejam em português: vídeo em inglês → texto em inglês; em espanhol → espanhol. Nunca traduza.
- video_language: preencha antes dos cortes com o código do idioma falado (ex.: "en", "pt").
- title: curto e chamativo (até 70 caracteres), sem clickbait mentiroso.
- description: 1-2 frases + chamada para seguir. hashtags: 3 a 6, sem o símbolo #.

Devolva de 0 a {MAX_CLIPS} cortes, do melhor para o pior. Se nada no vídeo for bom, devolva lista vazia."""


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def format_transcript(segments: list[Segment], energy: np.ndarray) -> str:
    lines = []
    for seg in segments:
        level = round(mean_between(energy, seg["start"], seg["end"]) * 9) if energy.size else 0
        lines.append(f"[{seg['start']:.1f}-{seg['end']:.1f}] ({_fmt_time(seg['start'])}) "
                     f"energia={level} | {seg['text']}")  # fmt: skip
    return "\n".join(lines)


def sanitize(ideas: list[ClipIdea], duration: float | None) -> list[ClipIdea]:
    limit = duration or float("inf")
    result: list[ClipIdea] = []
    for idea in ideas:
        start = max(0.0, idea.start_s)
        end = min(limit, idea.end_s)
        if end - start < MIN_CLIP_S:
            continue
        end = min(end, start + MAX_CLIP_S)
        hashtags = [h.lstrip("#").strip() for h in idea.hashtags if h.strip("# ")]
        result.append(
            idea.model_copy(
                update={
                    "start_s": round(start, 2),
                    "end_s": round(end, 2),
                    "potential": max(0, min(100, idea.potential)),
                    "hashtags": hashtags,
                }
            )
        )
    return result[:MAX_CLIPS]


def plan_with_claude(
    *,
    title: str,
    channel: str,
    language: str | None,
    description: str,
    views: int | None,
    segments: list[Segment],
    energy: np.ndarray,
    duration: float | None,
) -> list[ClipIdea]:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    lang_line = (
        f"Idioma falado no vídeo (YouTube): {language}. "
        f"Escreva title, description e hashtags nesse idioma ({language}).\n"
        if language
        else "Idioma falado: descubra pela transcrição e escreva title/description nele.\n"
    )
    user = (
        f"{lang_line}Título: {title}\nCanal: {channel}\nViews: {views}\n"
        f"Descrição do vídeo:\n{description[:1500]}\n\n"
        f"Transcrição ([início-fim] em segundos):\n{format_transcript(segments, energy)}"
    )
    last_error: Exception | None = None
    for _ in range(2):  # one retry on bad output
        response = client.beta.messages.parse(
            model=settings.model_writer,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            output_format=ClipPlan,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("A IA recusou analisar este vídeo.")
        if response.parsed_output is not None:
            return sanitize(response.parsed_output.clips, duration)
        last_error = RuntimeError(f"Resposta da IA inválida (stop_reason={response.stop_reason})")
    raise last_error or RuntimeError("Resposta da IA inválida")


def plan_heuristic(
    title: str, segments: list[Segment], energy: np.ndarray, duration: float | None
) -> list[ClipIdea]:
    """No API key: pick the loudest non-overlapping ~40s windows that contain speech."""
    total = int(duration or (segments[-1]["end"] if segments else 0))
    window = 40
    if total < MIN_CLIP_S or energy.size == 0:
        return []
    window = min(window, total)
    speech = np.zeros(total + 1)
    for seg in segments:
        speech[int(seg["start"]) : int(seg["end"]) + 1] = 1
    scores = []
    for start in range(0, max(1, total - window + 1), 5):
        e = mean_between(energy, start, start + window)
        s = float(speech[start : start + window].mean()) if segments else 1.0
        scores.append((e * (0.5 + 0.5 * s), start))
    scores.sort(reverse=True)
    picked: list[int] = []
    for _, start in scores:
        if all(abs(start - p) >= window for p in picked):
            picked.append(start)
        if len(picked) == 3:
            break
    ideas = []
    for i, start in enumerate(picked, 1):
        score = mean_between(energy, start, start + window)
        ideas.append(
            ClipIdea(
                start_s=float(start),
                end_s=float(start + window),
                potential=int(score * 70),
                reason="Escolhido pela fala mais agitada (heurística, IA desligada)",
                title=f"{title} (parte {i})"[:90],
                description="",
                hashtags=[],
            )
        )
    return sanitize(ideas, duration)
