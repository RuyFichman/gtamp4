"""Choose the best clip windows of a video. Claude when a key is set, a loudness heuristic otherwise.

Only commented gameplay becomes clips: the AI says first whether a real person talks over the
game (`has_commentary`), and a "no" means zero clips whatever else it returned."""

import math
from dataclasses import dataclass

import anthropic
import numpy as np
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline import speech
from app.pipeline.energy import mean_between
from app.pipeline.types import Chapter, HeatPoint, Segment


@dataclass(frozen=True)
class ClipLimits:
    """From the Ajustes tab (AppConfig); defaults match its defaults."""

    min_s: float = 12.0
    max_s: float = 75.0
    max_clips: int = 5


class ClipIdea(BaseModel):
    start_s: float
    end_s: float
    potential: int
    reason: str
    title: str
    description: str
    hashtags: list[str]


class ClipPlan(BaseModel):
    # field order matters: the model fills them in order, so it commits to the output language
    # and to "is anyone commenting?" before it picks a single clip
    video_language: str
    has_commentary: bool
    clips: list[ClipIdea]


_PROMPT = """Você é editor de cortes virais de GTA 6 para TikTok e Instagram Reels.
Recebe a transcrição com timestamps de um vídeo do YouTube (gameplay comentado de GTA 6, reação,
análise ou podcast) e escolhe os melhores trechos para virar cortes verticais curtos.
Só vira corte trecho com uma pessoa real (youtuber/streamer) falando por cima do jogo.
Gameplay puro, sem ninguém comentando, nunca vira corte.

A transcrição mistura, sem rótulo, a voz de quem comenta com as falas do próprio jogo
(cutscenes, NPCs, rádio, ligações). Como separar:
- quem comenta fala do jogo como jogador: primeira pessoa ("eu vou", "deixa eu testar"), fala
  com o público ("galera", "vocês", "olha isso"), reage (grito, risada, palavrão, susto) e
  comenta o jogo em si (gráficos, física, missões, a Rockstar);
- a fala do jogo é roteiro: diálogo entre personagens, nomes de personagens (Lucia, Jason...),
  tom de filme ou de série, frases que não reagem a nada, locutor de rádio, propaganda.

has_commentary: preencha depois de video_language e antes dos cortes. true só se uma pessoa real
comenta ou reage por cima do gameplay (vídeo só de conversa, como análise, notícia ou podcast,
também conta). Falas de personagens do jogo (cutscenes, NPCs, rádio, ligações) não contam.
Se for false, devolva clips vazio.

Sinais na transcrição:
- "energia" (0-9): volume geral do áudio, voz E sons do jogo (tiros, explosões, motores, música).
  Energia alta só é bom sinal quando quem comenta também reage naquela linha (grito, risada,
  susto). Energia alta numa linha calma ou sem fala é provavelmente só barulho do jogo.
- "replay" (0-9), quando aparece: vem do gráfico "mais repetidos" do YouTube e mostra onde o
  público real volta para rever. É o sinal mais forte que você tem: trechos com replay alto
  merecem prioridade, desde que façam sentido sozinhos. Sem a coluna, o vídeo não tem esse dado.
- Linhas "=== Capítulo ..." marcam os capítulos do vídeo; evite cortes que atravessem capítulos.
- Linhas "[... N s sem fala ...]" marcam trechos em que ninguém fala: só o jogo, música ou
  silêncio. Um corte não pode ter mais de {max_silence:.0f} s seguidos sem fala, e uma pausa só vale
  quando leva direto a uma reação.
- "Decisões do editor", quando aparecem, são cortes que o editor humano aprovou ou recusou (com o
  motivo). Use para entender o gosto dele e calibrar a nota; não copie os assuntos.
  "Ajuste do editor" mostra onde você errou o começo ou o fim de um corte que ele aprovou e o
  texto que ele tirou ou incluiu: corrija esse padrão nos cortes novos.

Regras para cada corte:
- Entre {min_s:.0f} e {max_s:.0f} segundos; comece e termine em frases completas.
- Precisa fazer sentido sozinho, sem o resto do vídeo, e prender a atenção nos 2 primeiros segundos.
  Quem assiste vê a tela, então "olha isso" serve SE a coisa acontece dentro do corte. Mas você
  não vê a imagem: prefira momentos em que a própria narração deixa claro o que está acontecendo.
- Comece direto na frase que prende: sem cumprimentos, "então", "bom", "é...", "como eu disse".
  Termine logo depois da conclusão ou da piada, não no começo do assunto seguinte.
- Prefira: reações genuínas de quem comenta ao que acontece na tela, descobertas e segredos
  explicados, testes ("será que dá pra..."), comparações narradas (ex.: GTA 5 vs GTA 6), bugs e
  física absurda COM comentário, dicas úteis narradas, opiniões fortes, polêmica e humor.
- Evite: trechos em que só o jogo fala, silêncio de quem comenta, menus e telas de carregamento,
  enrolação de deslocamento ("deixa eu ir ali", "peraí"), pedido de like e inscrição, leitura do
  chat sem contexto.
- potential: nota de 0 a 100 do potencial de viralizar. Seja exigente; reserve 90+ para trechos excepcionais.
- reason: uma frase curta explicando a nota, em português do Brasil (só o editor lê).
- title, description e hashtags SEMPRE no idioma falado no vídeo, mesmo que estas instruções
  estejam em português: vídeo em inglês → texto em inglês; em espanhol → espanhol. Nunca traduza.
- video_language: preencha antes dos cortes com o código do idioma falado (ex.: "en", "pt").
- title: curto e chamativo (até 70 caracteres), sem clickbait mentiroso.
- description: 1-2 frases + chamada para seguir. hashtags: 3 a 6, sem o símbolo #.

Devolva de 0 a {max_clips} cortes, do melhor para o pior. Se nada no vídeo for bom, devolva lista vazia."""


def system_prompt(limits: ClipLimits) -> str:
    return _PROMPT.format(
        min_s=limits.min_s,
        max_s=limits.max_s,
        max_clips=limits.max_clips,
        max_silence=speech.CLIP_MAX_SILENCE_S,
    )


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def replay_per_second(heatmap: list[HeatPoint], seconds: int) -> np.ndarray:
    """YouTube's "most replayed" graph as one 0..1 value per second (empty if there is none)."""
    if not heatmap or seconds <= 0:
        return np.zeros(0)
    out = np.zeros(seconds)
    for point in heatmap:
        lo = max(0, int(point["start"]))
        hi = max(lo + 1, math.ceil(point["end"]))
        out[lo:hi] = np.maximum(out[lo:hi], point["value"])
    top = float(out.max())
    return out / top if top > 0 else np.zeros(0)


def _level(signal: np.ndarray, start: float, end: float) -> int:
    return round(mean_between(signal, start, end) * 9)


def silence_line(seconds: float) -> str:
    return f"[... {seconds:.0f} s sem fala ...]"


def format_transcript(
    segments: list[Segment],
    energy: np.ndarray,
    replay: np.ndarray | None = None,
    chapters: list[Chapter] | None = None,
    duration: float | None = None,
) -> str:
    """One line per segment with its signals, plus chapter lines and a marker on every stretch
    of at least `speech.SILENCE_MARK_S` without speech (pure gameplay, music, silence)."""
    replay = replay if replay is not None else np.zeros(0)
    pending = sorted(chapters or [], key=lambda c: c["start"])
    lines = []
    spoken_until = 0.0
    for seg in segments:
        if seg["start"] - spoken_until >= speech.SILENCE_MARK_S:
            lines.append(silence_line(seg["start"] - spoken_until))
        spoken_until = max(spoken_until, seg["end"])
        while pending and pending[0]["start"] <= seg["start"] + 0.5:
            chapter = pending.pop(0)
            lines.append(f"=== Capítulo ({_fmt_time(chapter['start'])}): {chapter['title']} ===")
        cols = f"energia={_level(energy, seg['start'], seg['end']) if energy.size else 0}"
        if replay.size:
            cols += f" replay={_level(replay, seg['start'], seg['end'])}"
        lines.append(
            f"[{seg['start']:.1f}-{seg['end']:.1f}] ({_fmt_time(seg['start'])}) {cols} | {seg['text']}"
        )
    if duration and segments and duration - spoken_until >= speech.SILENCE_MARK_S:
        lines.append(silence_line(duration - spoken_until))
    return "\n".join(lines)


def sanitize(
    ideas: list[ClipIdea], duration: float | None, limits: ClipLimits = ClipLimits()
) -> list[ClipIdea]:
    limit = duration or float("inf")
    result: list[ClipIdea] = []
    for idea in ideas:
        start = max(0.0, idea.start_s)
        end = min(limit, idea.end_s)
        if end - start < limits.min_s:
            continue
        end = min(end, start + limits.max_s)
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
    return result[: limits.max_clips]


def finalize(plan: ClipPlan, duration: float | None, limits: ClipLimits) -> ClipPlan:
    """Sanitized clips; none at all when the AI found nobody commenting, whatever it returned."""
    clips = sanitize(plan.clips, duration, limits) if plan.has_commentary else []
    return plan.model_copy(update={"clips": clips})


def user_message(
    *,
    title: str,
    channel: str,
    language: str | None,
    description: str,
    views: int | None,
    transcript: str,
    examples: str = "",
) -> str:
    lang_line = (
        f"Idioma falado no vídeo (YouTube): {language}. "
        f"Escreva title, description e hashtags nesse idioma ({language}).\n"
        if language
        else "Idioma falado: descubra pela transcrição e escreva title/description nele.\n"
    )
    parts = [
        f"{lang_line}Título: {title}\nCanal: {channel}\nViews: {views}\n"
        f"Descrição do vídeo:\n{description[:1500]}"
    ]
    if examples:
        parts.append(examples)
    parts.append(f"Transcrição ([início-fim] em segundos):\n{transcript}")
    return "\n\n".join(parts)


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
    limits: ClipLimits,
    model: str,
    replay: np.ndarray | None = None,
    chapters: list[Chapter] | None = None,
    examples: str = "",
) -> ClipPlan:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user = user_message(
        title=title,
        channel=channel,
        language=language,
        description=description,
        views=views,
        transcript=format_transcript(segments, energy, replay, chapters, duration),
        examples=examples,
    )
    last_error: Exception | None = None
    for _ in range(2):  # one retry on bad output
        response = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=system_prompt(limits),
            messages=[{"role": "user", "content": user}],
            output_format=ClipPlan,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("A IA recusou analisar este vídeo.")
        if response.parsed_output is not None:
            return finalize(response.parsed_output, duration, limits)
        last_error = RuntimeError(f"Resposta da IA inválida (stop_reason={response.stop_reason})")
    raise last_error or RuntimeError("Resposta da IA inválida")


def plan_heuristic(
    title: str,
    segments: list[Segment],
    energy: np.ndarray,
    duration: float | None,
    limits: ClipLimits = ClipLimits(),
    replay: np.ndarray | None = None,
) -> list[ClipIdea]:
    """No API key: pick the loudest non-overlapping ~40s windows among those with enough
    narration (`speech.clip_speech`), half loudness, half "most replayed" when the video has
    that graph. No narrated window, no clip: loudness alone would pick gunfire and music."""
    replay = replay if replay is not None else np.zeros(0)
    has_replay = replay.size > 0

    def level(start: int) -> float:
        e = mean_between(energy, start, start + window)
        return 0.5 * e + 0.5 * mean_between(replay, start, start + window) if has_replay else e

    total = int(duration or (segments[-1]["end"] if segments else 0))
    window = int(min(max(40, limits.min_s), limits.max_s))
    if total < limits.min_s or energy.size == 0:
        return []
    window = min(window, total)
    talking = np.zeros(total + 1)
    for seg in segments:
        talking[int(seg["start"]) : int(seg["end"]) + 1] = 1
    timed = speech.spans(segments)
    scores = []
    for start in range(0, max(1, total - window + 1), 5):
        if not speech.clip_speech(timed, start, start + window).narrated:
            continue
        s = float(talking[start : start + window].mean())
        scores.append((level(start) * (0.5 + 0.5 * s), start))
    scores.sort(reverse=True)
    picked: list[int] = []
    for _, start in scores:
        if all(abs(start - p) >= window for p in picked):
            picked.append(start)
        if len(picked) == min(3, limits.max_clips):
            break
    ideas = []
    for i, start in enumerate(picked, 1):
        score = level(start)
        ideas.append(
            ClipIdea(
                start_s=float(start),
                end_s=float(start + window),
                potential=int(score * 70),
                reason="Escolhido pelo áudio mais agitado com narração"
                + (" e pelo trecho mais repetido" if has_replay else "")
                + " (heurística, IA desligada)",
                title=f"{title} (parte {i})"[:90],
                description="",
                hashtags=[],
            )
        )
    return sanitize(ideas, duration, limits)
