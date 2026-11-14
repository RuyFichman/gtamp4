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
