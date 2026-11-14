import subprocess
from collections.abc import Sequence


class CommandError(RuntimeError):
    """External command failed; message carries the tail of stderr."""


def run(cmd: Sequence[str], tail_lines: int = 15) -> subprocess.CompletedProcess[str]:
    """Run an external tool (ffmpeg, ffprobe...) and raise CommandError with stderr on failure."""
    result = subprocess.run(
        list(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-tail_lines:])
        raise CommandError(f"{cmd[0]} saiu com código {result.returncode}:\n{tail}")
    return result


# Known yt-dlp/YouTube messages -> what the user should do (shown above the raw error).
_HINTS = [
    (
        "confirm you're not a bot",
        "O YouTube pediu verificação anti-robô. Espere alguns minutos e clique em Tentar de novo.",
    ),
    ("video is unavailable", "Vídeo indisponível: foi removido, bloqueado ou ficou privado."),
    ("private video", "Vídeo privado: não dá para baixar."),
    ("sign in to confirm your age", "Vídeo com restrição de idade: o YouTube exige login."),
    ("members-only", "Vídeo só para membros do canal: não dá para baixar."),
    ("premieres in", "Vídeo ainda não estreou. Tente depois da estreia."),
]


def explain_error(message: str) -> str:
    """Prefix a raw error with a pt-BR, actionable hint when we recognise it."""
    lower = message.lower().replace("’", "'")  # YouTube uses a curly apostrophe
    for needle, hint in _HINTS:
        if needle in lower:
            return f"{hint}\n\n{message}"
    return message
