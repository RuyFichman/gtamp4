"""Radar triage: decide which found videos are worth processing. Haiku when a key is set."""

import re

import anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline.radar import Found

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

reason: uma frase curta em português do Brasil.
Devolva exatamente uma decisão por vídeo recebido, com o mesmo youtube_id."""


def _describe(v: Found) -> str:
    minutes = f"{v.duration_s / 60:.0f} min" if v.duration_s else "?"
    return f"- {v.youtube_id} | {v.title} | canal: {v.channel} | {minutes} | views: {v.views}"


def triage_with_claude(
    videos: list[Found], recent_titles: list[str], model: str
) -> dict[str, Decision]:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    recent = "\n".join(f"- {t}" for t in recent_titles) or "(nenhum)"
    user = f"Já enviados recentemente:\n{recent}\n\nVídeos para avaliar:\n" + "\n".join(
        _describe(v) for v in videos
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


def triage_heuristic(videos: list[Found]) -> dict[str, Decision]:
    """No API key: keep anything whose title mentions GTA 6 / GTA VI."""
    return {
        v.youtube_id: Decision(
            youtube_id=v.youtube_id,
            keep=bool(GTA6.search(v.title)),
            reason="Título fala de GTA 6 (sem IA)"
            if GTA6.search(v.title)
            else "Título não fala de GTA 6 (sem IA)",
        )
        for v in videos
    }


def triage(videos: list[Found], recent_titles: list[str], model: str) -> dict[str, Decision]:
    if not videos:
        return {}
    if get_settings().anthropic_api_key:
        return triage_with_claude(videos, recent_titles, model)
    return triage_heuristic(videos)
