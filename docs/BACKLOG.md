# Backlog

Funcionalidades adiadas. Ao começar uma, mova para o roadmap do `AGENTS.md` e apague daqui quando concluída.

## Estúdio: detectar bordas desfocadas

- O "Automático" do enquadramento (`pipeline/framing.py`) usa `cropdetect`, que só acha barras **pretas**. Vídeos verticais com laterais desfocadas ainda exigem zoom manual.
- Ideia: medir a nitidez (variância do Laplaciano / bordas) por coluna com numpy para achar a faixa nítida, e reaproveitar `framing.suggest()`.

## Fila: pegar job de forma atômica

- `jobs/queue.claim_next` faz `SELECT` e depois `UPDATE`; com dois processos no mesmo banco, os dois pegam o mesmo job (aconteceu com um backend órfão: um `radar_scan` rodou duas vezes e mandou vídeos além do limite diário).
- Ideia: `UPDATE job SET status='running' ... WHERE id = (SELECT ...) AND status='queued'` e conferir `rowcount`, ou um lock de arquivo em `data/` que impeça subir um segundo backend.

## Aprovar: feedback livre por corte

- Hoje a IA aprende com o motivo da recusa e com o ajuste de início/fim no Estúdio (`feedback.adjustment_lines`). Falta um jeito de explicar o "porquê" em texto livre (ex.: "o gancho é bom porque revela algo antes de todo mundo").
- Ideia: campo opcional `Clip.editor_note` (botão "Feedback" no card e no Estúdio) que entra na linha do exemplo em `feedback._line`. Cuidado com o tamanho do prompt: cortar notas longas.
