# Backlog

Funcionalidades adiadas. Ao começar uma, mova para o roadmap do `AGENTS.md` e apague daqui quando concluída.

## Legenda queimada no vídeo (estilo TikTok)

- Legenda grande, centralizada, com a **palavra falada no momento destacada** (cor/escala diferente).
- Fonte: timestamps por palavra (faster-whisper `word_timestamps=True`; legendas do YouTube só dão por frase, então pode exigir Whisper).
- Gerar arquivo `.ass` (Advanced SubStation Alpha) com estilos/karaoke e queimar com o filtro `ass` do ffmpeg.
- Sempre no idioma original do vídeo.
- Configurável na aba **Moldura** (fonte, cor, cor do destaque, posição, tamanho) e liga/desliga por corte no **Estúdio**.

## Estúdio: zoom / reenquadramento

- Problema visto: vídeos que já são verticais (gravação de celular) dentro de um quadro 16:9 viram um corte 9:16 com o conteúdo pequeno e borda desfocada dupla.
- Ideia: no Estúdio, um controle de zoom e posição (crop) do vídeo do meio, com prévia; ou detecção automática das barras laterais (`cropdetect` do ffmpeg) para ampliar sozinho.
- Guardar o crop no `Clip` e usar no `build_cut_command`.
