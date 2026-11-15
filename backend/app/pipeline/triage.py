"""Radar triage: decide which found videos are worth processing. Haiku when a key is set."""

import re

import anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline.radar import Found
from app.pipeline.ranking import ChannelHistory, is_bad_channel

GTA6 = re.compile(r"gta\s*(6|vi)\b|grand\s+theft\s+auto\s*(6|vi)\b", re.IGNORECASE)


class Decision(BaseModel):
    youtube_id: str
    keep: bool
    reason: str


class TriageResult(BaseModel):
    decisions: list[Decision]


SYSTEM_PROMPT = """Você faz a triagem de vídeos do YouTube para um editor de cortes de GTA 6
(TikTok/Reels). Os cortes só funcionam se o vídeo tiver FALA interessante sobre GTA 6.

keep=true para: notícias, vazamentos, análises, teorias, reações, podcasts, entrevistas,
gameplay comentado, opiniões fortes sobre GTA 6. Qualquer idioma.

keep=false para:
- não é sobre GTA 6 (GTA 5/Online, outros jogos, título usa GTA 6 só como isca);
- provavelmente sem fala: música, trilha sonora, trailer puro, compilação sem comentário;
- notícia repetida: mesmo assunto de um título em "Já enviados recentemente";
- golpe, download pirata, "GTA 6 mobile/APK", mod falso.

"editor: X de Y cortes aprovados" é o histórico do canal: dos cortes que o editor já avaliou
de vídeos desse canal, quantos ele aprovou. Canal com quase tudo recusado (ex.: 1 de 8) é
keep=false, a não ser que o título seja claramente forte; histórico bom reforça keep=true.
Sem histórico é neutro.

reason: uma frase curta em português do Brasil.
Devolva exatamente uma decisão por vídeo recebido, com o mesmo youtube_id."""


def _describe(v: Found, history: ChannelHistory) -> str:
    minutes = f"{v.duration_s / 60:.0f} min" if v.duration_s else "?"
    channel = v.channel
    record = history.of(v.channel)
    if record and record.decided:
        channel += f" (editor: {record.approved} de {record.decided} cortes aprovados)"
    return f"- {v.youtube_id} | {v.title} | canal: {channel} | {minutes} | views: {v.views}"


def triage_with_claude(
    videos: list[Found], recent_titles: list[str], model: str, history: ChannelHistory
) -> dict[str, Decision]:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    recent = "\n".join(f"- {t}" for t in recent_titles) or "(nenhum)"
    user = f"Já enviados recentemente:\n{recent}\n\nVídeos para avaliar:\n" + "\n".join(
        _describe(v, history) for v in videos
    )
    response = client.beta.messages.parse(
        model=model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_format=TriageResult,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"Triagem da IA falhou (stop_reason={response.stop_reason})")
    wanted = {v.youtube_id for v in videos}
    return {d.youtube_id: d for d in response.parsed_output.decisions if d.youtube_id in wanted}


def _heuristic_one(v: Found, history: ChannelHistory) -> Decision:
    record = history.of(v.channel)
    if not GTA6.search(v.title):
        keep, reason = False, "Título não fala de GTA 6 (sem IA)"
    elif record is not None and is_bad_channel(record):
        keep = False
        reason = (
            f"Canal com poucos cortes aprovados: {record.approved} de {record.decided} (sem IA)"
        )
    else:
        keep, reason = True, "Título fala de GTA 6 (sem IA)"
    return Decision(youtube_id=v.youtube_id, keep=keep, reason=reason)


def triage_heuristic(
    videos: list[Found], history: ChannelHistory | None = None
) -> dict[str, Decision]:
    """No API key: keep anything whose title mentions GTA 6 / GTA VI, unless the editor keeps
    rejecting that channel's clips."""
    history = history or ChannelHistory()
    return {v.youtube_id: _heuristic_one(v, history) for v in videos}


def triage(
    videos: list[Found],
    recent_titles: list[str],
    model: str,
    history: ChannelHistory | None = None,
) -> dict[str, Decision]:
    if not videos:
        return {}
    history = history or ChannelHistory()
    if get_settings().anthropic_api_key:
        return triage_with_claude(videos, recent_titles, model, history)
    return triage_heuristic(videos, history)
