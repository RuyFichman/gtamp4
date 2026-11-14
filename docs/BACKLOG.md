# Backlog

Funcionalidades adiadas. Ao começar uma, mova para o roadmap do `AGENTS.md` e apague daqui quando concluída.

## Legenda queimada no vídeo (estilo TikTok)

- Legenda grande, centralizada, com a **palavra falada no momento destacada** (cor/escala diferente).
- Fonte: timestamps por palavra (faster-whisper `word_timestamps=True`; legendas do YouTube só dão por frase, então pode exigir Whisper).
- Gerar arquivo `.ass` (Advanced SubStation Alpha) com estilos/karaoke e queimar com o filtro `ass` do ffmpeg.
- Sempre no idioma original do vídeo.
- Configurável na aba **Moldura** (fonte, cor, cor do destaque, posição, tamanho) e liga/desliga por corte no **Estúdio**.

## Estúdio: detectar bordas desfocadas

- O "Automático" do enquadramento usa `cropdetect`, que só acha barras **pretas**. Vídeos verticais com laterais desfocadas ainda exigem zoom manual.
- Ideia: medir a nitidez (variância do Laplaciano / bordas) por coluna com numpy para achar a faixa nítida.
