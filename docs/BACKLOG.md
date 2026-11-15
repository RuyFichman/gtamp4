# Backlog

Funcionalidades adiadas. Ao começar uma, mova para o roadmap do `AGENTS.md` e apague daqui quando concluída.

## Estúdio: detectar bordas desfocadas

- O "Automático" do enquadramento (`pipeline/framing.py`) usa `cropdetect`, que só acha barras **pretas**. Vídeos verticais com laterais desfocadas ainda exigem zoom manual.
- Ideia: medir a nitidez (variância do Laplaciano / bordas) por coluna com numpy para achar a faixa nítida, e reaproveitar `framing.suggest()`.
