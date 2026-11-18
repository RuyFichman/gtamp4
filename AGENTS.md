# AGENTS.md

Guia para agentes de IA (Claude Code, Codex, Cursor etc.) que trabalham neste repositório.
Leia inteiro antes de mudar qualquer coisa.

## O que é o projeto

**gtamp4** é uma ferramenta **local e pessoal** (não comercial, um único usuário) que:

1. Encontra vídeos sobre GTA 6 no YouTube (manualmente por link ou automaticamente pelo Radar).
2. Baixa o vídeo e a transcrição.
3. Usa IA para escolher os melhores trechos e dar uma nota de **potencial (0–100)**.
4. Corta cada trecho em vídeo vertical 9:16, com a **moldura** (overlay PNG) em uso, se houver.
5. Mostra os cortes numa interface web para o usuário **aprovar / recusar / editar / baixar**.
6. Organiza a fila de postagem para TikTok e Instagram. **A postagem é sempre feita manualmente pelo usuário**; o app só prepara o arquivo e o texto.

Tudo roda na máquina do usuário. Não há deploy em nuvem, login nem multi-tenant.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, **FastAPI**, gerenciado com **uv** |
| Banco | **SQLite** via **SQLModel** (arquivo em `data/app.db`) |
| Fila de jobs | Tabela `job` no SQLite + um worker em thread (sobrevive a reinícios) |
| Agendador | **APScheduler** (só enfileira: coleta do Radar, atualização de views) |
| Download | **yt-dlp** (vídeo, metadados, legendas) |
| Transcrição | 1º legendas do YouTube via yt-dlp; fallback **faster-whisper** em CPU (`int8`, modelo escolhido em Ajustes, padrão `small`). O áudio vai para o Whisper já decodificado pelo ffmpeg (`transcribe.decode_audio`) |
| Legenda queimada | Whisper com `word_timestamps` só no trecho do corte → `.ass` (`pipeline/captions.py`) → filtro `ass` do ffmpeg (libass) |
| IA | **API do Claude** (SDK `anthropic`): uma chamada por vídeo com o modelo de cortes (padrão Sonnet) que escolhe trechos, dá a nota e escreve título/descrição; o modelo de triagem (padrão Haiku) filtra vídeos do Radar. Saída estruturada via `beta.messages.parse` + Pydantic. Sem chave, cai numa heurística por volume |
| Energia da fala | ffmpeg → PCM → **numpy** (RMS por segundo, `pipeline/energy.py`), passada à IA como "energia 0-9" por linha |
| Edição de vídeo | **ffmpeg** / **ffprobe** (CLI, via `pipeline/proc.run`) |
| Frontend | **React 19 + Vite + TypeScript + Tailwind v4**, sem biblioteca de componentes; lint com **oxlint** |
| Comunicação | REST JSON em `/api/*`; progresso de jobs por polling. Arquivos servidos em `/api/media/{clips,videos,frames}/` |

## Ambiente da máquina (importante)

- **Windows 11**, Ryzen 5 5600, 16 GB RAM, GPU **AMD Radeon RX 590** (sem CUDA).
- **Não use CUDA.** Whisper roda em CPU. Não adicione dependências que exijam NVIDIA.
- Encoder de vídeo: tente **`h264_amf`** (AMD) e faça fallback automático para **`libx264`** se falhar. A escolha fica em um único lugar (`backend/app/pipeline/encoder.py`, `pick_encoder(choice)`); o `cut.render_clip` ainda tenta de novo em CPU se o AMF falhar no meio.
- Caminhos: use sempre `pathlib.Path`; nunca concatene caminhos com `/` ou `\` em string.
- Shell padrão é PowerShell; scripts do projeto devem funcionar no Windows.

## Estrutura de pastas

```
gtamp4/
├── AGENTS.md              # este arquivo
├── CLAUDE.md              # aponta para o AGENTS.md
├── docs/
│   └── BACKLOG.md         # funcionalidades adiadas / ideias
├── backend/
│   ├── pyproject.toml
│   ├── .env.example       # variáveis aceitas (copie para .env)
│   ├── app/
│   │   ├── main.py        # cria o FastAPI, monta rotas e /api/media, inicia worker e scheduler
│   │   ├── config.py      # Settings (pydantic-settings) lidas do .env
│   │   ├── db.py          # engine SQLite, sessão, add_missing_columns()
│   │   ├── models.py      # tabelas SQLModel
│   │   ├── store.py       # config editável na UI (tabela setting): AppConfig, RadarConfig
│   │   ├── stats.py       # números do Painel
│   │   ├── feedback.py    # motivos de recusa, exemplos do editor para o prompt da IA,
│   │   │                  # histórico de aprovação por canal (Radar)
│   │   ├── warmup.py      # checklist do Aquecimento
│   │   ├── frames.py      # molduras (validação do PNG, padrão, re-render)
│   │   ├── maintenance.py # limpeza de vídeos originais
│   │   ├── scheduler.py
│   │   ├── api/           # um arquivo de rotas por aba + schemas.py (modelos de resposta)
│   │   ├── jobs/          # queue, worker, handlers (process_video, render_clip), radar_jobs
│   │   └── pipeline/      # download, transcribe, energy, score, triage, radar, ranking,
│   │                      # boundaries, captions, cut, framing, encoder, proc, types
│   │                      # (não lê o banco)
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx        # abas
│       ├── pages/         # uma página por aba
│       ├── components/    # um componente por arquivo
│       └── lib/
│           ├── api.ts     # cliente da API (único lugar que faz fetch)
│           ├── types.ts   # tipos da API
│           └── format.ts  # datas, views, durações, tempos
└── data/                  # NÃO versionado: app.db, videos/, clips/, frames/
```

## Abas da interface (glossário do domínio)

| Aba | Função |
|---|---|
| **Painel** | Estatísticas (`GET /api/stats`, `app/stats.py`): fila de aprovação/postagem, taxa de aprovação, cortes por dia (14 dias, fuso da máquina), potencial médio aprovados vs. recusados, postados por conta, Radar, jobs, disco. Gráfico em SVG próprio (sem lib), cores validadas para daltonismo |
| **Aprovar** | Colar link do YouTube, ver fila de processamento, cards de corte (aprovar, recusar, Estúdio, baixar). "Recusar" pede o motivo (botões; "Sem motivo" também vale), que ensina a IA (ver Pipeline). Fica montada o tempo todo para o polling e o contador da aba seguirem funcionando |
| **Postagem** | Cortes aprovados aguardando postagem manual: baixar vídeo, copiar título/descrição/hashtags, escolher a conta e marcar como "postado" (com link do post, opcional). Lista dos já postados |
| **Contas** | Lista das contas de TikTok / Instagram do usuário (nome, @, plataforma, notas). Só para organização: **sem tokens, sem login, sem integração** |
| **Aquecimento** | Checklist **manual** de 14 dias por conta (`app/warmup.py`: 3 fases, tarefas diárias e "uma vez", tabela `warmupcheck`, dia local da máquina). Só registra o que o usuário marcou; nunca automatizar (ver Regras) |
| **Radar** | Busca automática de vídeos novos de GTA 6 por termos/canais, com intervalo e limite diário configuráveis (ver seção Radar). A lista mostra inscritos, views por hora, o histórico do canal ("Canal: X de Y cortes aprovados por você") e a posição na fila de espera |
| **Moldura** | PNGs 9:16 com transparência (`app/frames.py`: valida assinatura, proporção, largura mínima e alfa só com stdlib; arquivos em `data/frames/`). Uma moldura "em uso" (ou nenhuma) vale para renders novos; "Re-renderizar cortes" enfileira `render_clip` para os pendentes/aprovados. Prévia em CSS por cima de um corte real. Também o estilo da **legenda queimada** (`CaptionStyle`, tabela `setting`, chave `caption_style`): liga/desliga global, fonte, tamanho, contorno, cores, altura, palavras por vez, maiúsculas |
| **Ajustes** | `AppConfig` (`store.py`, tabela `setting`): duração mín/máx e nº de cortes, encoder, modelo do Whisper, modelos do Claude (padrões vêm do `.env`). Os jobs leem a config e passam explicitamente ao pipeline (o pipeline não lê o banco). A chave da API **não** é editável aqui (só mostra se está configurada). Também: limpeza dos vídeos originais cujos cortes já foram todos postados/recusados (bloqueada com jobs na fila) |

O **Estúdio** não é aba: é um painel (`StudioModal`) aberto pelos cards (ver seção Estúdio).

Cada card de corte mostra: player, título, **views do vídeo original**, **data da consulta**, link "Ver fonte no YouTube", botão "Atualizar views", **Potencial x/100** com o motivo, e a descrição gerada.

## Modelo de dados (resumo)

- `SourceVideo`: youtube_id, url, título, canal, idioma, duração, views, views_checked_at, transcrição, heatmap (gráfico "mais repetidos" do YouTube) e chapters (capítulos), file_path (some quando a limpeza apaga o original).
- `Clip`: source_video_id, start_s, end_s, ai_start_s/ai_end_s (início/fim que o app entregou; o Estúdio não mexe), título, descrição, hashtags, potential (0–100), potential_reason, file_path, status, reject_reason (chave de `feedback.REJECT_REASONS`, só quando recusado), zoom/pan_x/pan_y (enquadramento), captions (legenda liga/desliga) + caption_words/caption_range (cache das palavras do Whisper e a janela que cobrem), account_id, post_url, posted_at.
- `Job`: kind, payload (JSON), status, progresso, mensagem, erro, tentativas, timestamps.
- `Account` (+ `warmup_started_on`), `WarmupCheck`, `FrameTemplate` (name, overlay_path, is_default), `RadarQuery`, `RadarCandidate` (+ channel_id, published_at aproximado, subscribers, views_per_hour medido quando achado), `RadarChannel` (cache de inscritos por canal, 7 dias), `Setting` (chave/valor JSON).

**Status de `Clip`:** `pending_review` → `approved` | `rejected` → `posted` (marcado manualmente pelo usuário).
**Status de `Job`:** `queued` → `running` → `done` | `failed`. Ao iniciar o app, jobs `running` voltam para `queued` ("Retomando após reinício").

## Pipeline de um vídeo

1. `download`: yt-dlp baixa vídeo (máx. 1080p), metadados e legendas (manual > automática, **no idioma original**), mais o gráfico "mais repetidos" (`heatmap`) e os capítulos, quando o YouTube tem (muitos vídeos não têm: sem views suficientes, não há gráfico).
2. `transcribe`: usa a legenda; se não houver, faster-whisper em CPU. Resultado: segmentos com timestamps.
3. `energy` + `score`: mede o volume por segundo; Claude recebe a transcrição anotada (`energia=0-9` e, se houver, `replay=0-9` do "mais repetidos"; linhas `=== Capítulo ... ===`), os metadados e as **decisões do editor** (`feedback.editor_examples`: até 4 aprovados/postados e 4 recusados recentes de outros vídeos, com motivo, nota que a IA deu e o começo/fim do trecho, mais a contagem dos motivos). Aprovado cujo início/fim o editor mexeu no Estúdio (comparando com `ai_start_s`/`ai_end_s`, tolerância 0,5 s) vem primeiro, marcado "APÓS AJUSTE DO EDITOR", com o texto que saiu ou entrou em cada ponta, e há uma linha de tendência ("encurtou o fim em N") a partir de 3 aprovados com esse registro. Vale ajustar antes ou depois de aprovar: a comparação é feita quando o próximo vídeo é processado. Devolve trechos (start, end, potential, reason, title, description, hashtags). `sanitize()` aplica os `ClipLimits` dos Ajustes (padrão 12–75 s, até 5 cortes). Sem chave, a heurística usa metade volume, metade replay.
3b. `boundaries`: para cada corte, o Whisper transcreve o trecho com 3 s de folga de cada lado (uma vez só; as palavras ficam no cache `caption_words` e a legenda reaproveita). Início e fim vão para a melhor quebra a até 2 s: fim de frase (`.` `!` `?`) vale mais que vírgula, pausa longa mais que curta, e se afastar custa. Nunca corta entre pedaços de uma palavra que o Whisper separou (`GT` + `-A6`). Se a mudança quebra os limites de duração, mantém o tempo da IA naquele lado.
4. `cut`: ffmpeg corta, reenquadra para 1080x1920 (fundo desfocado + vídeo centralizado, com o enquadramento do corte), aplica a moldura em uso se houver, queima a legenda por cima de tudo (se ligada no estilo e no corte), normaliza áudio (`loudnorm`). Arquivo: `data/clips/{youtube_id}_{start}-{end}.mp4`.
5. Cria `Clip` com status `pending_review` só depois do arquivo renderizado (reprocessar o mesmo vídeo não duplica cortes).

Tudo isso roda no job `process_video` (`backend/app/jobs/handlers.py`).

## Estúdio

- Abre num painel (`StudioModal`) pelo botão "Estúdio" dos cards (Aprovar e Postagem).
- `GET /api/clips/{id}/studio`: corte, vídeo original (`/api/media/videos/`, com Range, então dá para pular no player), transcrição, job de render pendente e a moldura em uso (`frame_url`).
- `PATCH /api/clips/{id}`: o texto é salvo na hora. Início/fim novos (3 a 180 s) ou enquadramento novo viram um job `render_clip`; o `Clip` só muda depois do render dar certo. O arquivo novo se chama `{youtube_id}_{clip_id}_{start}-{end}.mp4` (com `_v{job_id}` se o nome repetir, ex.: só trocou a moldura ou o zoom); o antigo é apagado se nenhum outro corte usa. Um render por corte de cada vez (409).
- **Enquadramento:** `Clip.zoom` (1–3) e `pan_x`/`pan_y` (-1..1) mudam só o vídeo do meio (`cut.Framing`, `foreground_filter`: escala para 1080·zoom e recorta na tela 1080x1920). Prévia em CSS com a mesma geometria (`FramingPreview`). "Automático" (`GET /api/clips/{id}/autoframe`, `pipeline/framing.py`) usa `cropdetect` e só acha barras pretas. Jobs `render_clip` sem as chaves de enquadramento (ex.: re-render da Moldura) mantêm o do corte.
- **Legenda:** caixa "Legenda queimada neste corte" (`Clip.captions`); mudar só ela também vira `render_clip` (`captions` no payload; sem a chave, vale a do corte). O render reaproveita `caption_words` se a janela salva cobre o novo início/fim; senão roda o Whisper de novo no trecho. Texto sempre no idioma original.
- Se o vídeo original foi apagado do disco, o job baixa de novo.

## Radar

- `scheduler.py`: um tick do APScheduler a cada 1 min lê a config do banco (`store.py`, tabela `setting`) e só **enfileira** jobs: `radar_scan` no intervalo escolhido (se ligado) e `refresh_views` a cada 3 h. O worker executa. Nunca publica nada.
- `radar_scan` (`jobs/radar_jobs.py`):
  1. roda cada `RadarQuery` ativa (`pipeline/radar.py`, yt-dlp com `extract_flat`, sem baixar);
  2. ignora vídeos já vistos (`RadarCandidate`) ou já processados (`SourceVideo`);
  3. aplica o pré-filtro (duração 90 s a 3 h, sem live);
  4. busca os inscritos dos canais que passaram (`radar.channel_subscribers`, uma consulta rápida por canal; cache `RadarChannel` de 7 dias; busca por canal já traz o número). Falha não para o scan: fica sem inscritos e tenta no próximo;
  5. faz a triagem por título com o modelo de triagem (`pipeline/triage.py`), que recebe o histórico do canal ("editor: X de Y cortes aprovados", de `feedback.channel_history`). Sem chave: regex "GTA 6/VI" e descarta canal com 6+ cortes avaliados e até 15% aprovados;
  6. envia os da espera para `process_video` na ordem de `radar_jobs.waiting_queue`, até o **limite diário** (envios que falharam não contam);
  7. quem fica "na espera" por mais de 3 dias é descartado.

**Ordem da fila** (`pipeline/ranking.py`): `views por hora ÷ √inscritos × peso do canal`.
- **Views por hora:** views ÷ horas desde a publicação, medidas quando o Radar achou o vídeo. A idade é aproximada ("há 9 horas", via `approximate_date` do yt-dlp), com mínimo de 1 h; sem data, conta como 48 h.
- **Inscritos:** abaixo de 10 mil, contam como 10 mil; se o canal esconde o número, contam como 100 mil. A raiz fica entre "velocidade pura" (canal grande sempre ganha) e "views por inscrito" (qualquer canal minúsculo ganharia).
- **Peso do canal:** aprovados (inclui postados) ÷ decididos daquele canal, suavizado com 5 decisões "médias" e comparado à taxa geral, ao quadrado, limitado a 0,25×–3×. Canal sem histórico vale 1×. Recusa por "Cortou no meio" não conta contra o canal (o erro foi do corte). O canal é casado pelo nome (`ranking.channel_key`: sem diferença de maiúsculas/espaços), porque `SourceVideo` não guarda o id do canal.
- `RadarCandidate.status`: `rejected` | `waiting` | `sent`. "Cortar mesmo assim" na UI ignora triagem e limite.

Cada etapa é idempotente: se o arquivo de saída já existe e é válido, pula.

## API (resumo)

| Prefixo | Rotas |
|---|---|
| `/api/health`, `/api/stats` | status do sistema; números do Painel |
| `/api/videos` | `POST` (link → job `process_video`), `POST /{id}/refresh-views` |
| `/api/jobs` | lista, `POST /{id}/retry`, `DELETE /{id}` |
| `/api/clips` | lista por status/ordem, `GET /reject-reasons`, `POST /{id}/status` (com `reject_reason` ao recusar), `GET /{id}/download`, `GET /{id}/studio`, `PATCH /{id}`, `GET /{id}/autoframe` |
| `/api/accounts` | CRUD |
| `/api/warmup` | lista, `POST /{account_id}/start` / `stop` / `check` |
| `/api/radar` | estado, `PUT /config`, `POST /scan`, `queries` (CRUD), `candidates` (com `queue_position` e `channel_record`), `POST /candidates/{id}/send` |
| `/api/frames` | lista, `POST` (multipart: name + file), `PUT /default`, `DELETE /{id}`, `POST /rerender` |
| `/api/captions` | estilo da legenda queimada (`GET`/`PUT`, com padrões e fontes) |
| `/api/settings`, `/api/maintenance/originals` | Ajustes (`GET`/`PUT`); prévia e `POST /delete` da limpeza |

## Regras

- **Idioma:** títulos, descrições e hashtags são gerados **sempre no idioma original do vídeo**. Não traduzir.
- **UI em português (pt-BR).** Código, nomes de variáveis, funções, tabelas e commits em **inglês**.
- **Segredos** só no `.env` (raiz do repo ou `backend/.env`, que tem prioridade). Nunca commitar `.env`, nunca logar nem mostrar chaves (a API e a UI só dizem se a chave existe). Manter `backend/.env.example` atualizado.
- **`data/` nunca é versionado.**
- **Sem automação de aquecimento de contas** (curtir/rolar feed com bot). Viola os termos do TikTok/Instagram e causa ban. A aba Aquecimento é só checklist manual.
- **Postagem é 100% manual (decisão do usuário).** Não implementar postagem automática de nenhum tipo: nem APIs oficiais, nem automação de navegador, nem agendamento que publique sozinho. O app apenas prepara o vídeo e o texto e registra o que o usuário marcou como postado.
- Chamadas ao Claude: só em `backend/app/pipeline/score.py` (cortes) e `pipeline/triage.py` (Radar), com model ID vindo do `AppConfig` (Ajustes), passado pelo job. Validar resposta com Pydantic; em JSON inválido, tentar de novo uma vez e então marcar o job como `failed` com mensagem clara.
- Chamadas ao ffmpeg/ffprobe/yt-dlp: sempre via helper que captura stderr e grava as últimas linhas no `Job.error` (`proc.run`). Nunca engolir erros (ex.: "ffmpeg saiu com código ..." precisa vir com o motivo).
- Mensagens de erro mostradas na UI devem ser em português e acionáveis. Erros de validação (422) viram texto legível no `api.ts`.
- Ações destrutivas na UI (apagar originais, apagar moldura, parar aquecimento, re-renderizar em lote) pedem confirmação inline, sem `window.confirm`.
- Não adicionar dependências pesadas sem necessidade; preferir a stdlib.
- Funcionalidades adiadas vão para `docs/BACKLOG.md`, não para o código como TODO solto.

## Comandos

> Pré-requisitos: `uv`, Node 24, `ffmpeg` no PATH (`winget install Gyan.FFmpeg`).

```powershell
# Backend
cd backend
uv sync                                      # instala dependências
uv run fastapi dev app/main.py --port 8000   # dev server (recarrega sozinho)
uv run pytest                                # testes
uv run ruff check . ; uv run ruff format .   # lint + format

# Frontend
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxy /api -> :8000)
npm run build
npm run lint         # oxlint
npx tsc -b --noEmit  # typecheck (o tsconfig raiz só tem references; sem -b não checa nada)
```

## Armadilhas conhecidas

- SQLModel exige datetimes **com fuso** (`utcnow()` de `app.models`); comparar com datetime "naive" dá erro 500. O SQLite perde o fuso ao gravar: o que volta "naive" é UTC (ver `schemas._UtcModel` e `stats.py`).
- yt-dlp precisa de runtime JS para o YouTube: usamos Node (`js_runtimes: {"node": {}}` em `pipeline/download.py`) e o pacote `yt-dlp[default]`.
- Um terminal aberto antes de instalar o ffmpeg não o enxerga no PATH: abra um terminal novo.
- No Windows, `python` solto pode ser o atalho da Microsoft Store: rode scripts com `uv run python`.
- yt-dlp desta versão não tem o atalho `ytsearchdate`: o Radar usa a URL `youtube.com/results?search_query=...&sp=CAI%3D` (ordenado por data).
- `create_all` não altera tabelas existentes. `db.add_missing_columns()` adiciona colunas novas no startup (com default escalar ou NULL). Para renomear ou apagar coluna, escreva a migração à mão.
- O YouTube às vezes responde "confirm you're not a bot" ou "video unavailable". `proc.explain_error()` põe uma dica em pt-BR acima do erro cru.
- O prompt da IA é em português; sem o idioma explícito, a IA escrevia títulos de vídeos em inglês em português. Por isso `plan_with_claude` recebe `language` e o `ClipPlan` tem `video_language` preenchido antes dos cortes. Só `reason` é em pt-BR. Não remova isso.
- `get_settings()` tem `lru_cache`: teste que muda `DATA_DIR` precisa chamar `get_settings.cache_clear()`.
- faster-whisper 1.2 abre arquivos com PyAV usando `metadata_errors`, que o `av` 19 não aceita: nunca passe caminho ao Whisper, passe o array de `transcribe.decode_audio`.
- O filtro `ass` do ffmpeg não lida bem com `C:\` no caminho: `cut.render_clip` escreve `captions.ass` numa pasta temporária e roda o ffmpeg com `cwd` nela (por isso os outros caminhos viram absolutos).
- O Whisper roda em todo corte novo (para ajustar início/fim), mesmo com a legenda desligada; com ela ligada, é a mesma passada.
- Vídeo com restrição de idade só baixa logado: `YTDLP_COOKIES_FROM_BROWSER=firefox` (ou `firefox:Perfil`) no `.env` faz o `download.login_opts()` passar os cookies do Firefox ao yt-dlp (vale para download, metadados e views; a busca do Radar continua anônima). Chrome 127+ não serve (cookies com criptografia "app-bound" que o yt-dlp não lê). OAuth e os truques de "cliente embed/TV" para burlar a idade foram fechados pelo YouTube.
- O "mais repetidos" vem da página do vídeo (`heatmap` do yt-dlp) e falta na maioria dos vídeos pequenos/novos; o prompt diz à IA que a coluna `replay` pode não existir.
- A busca "plana" do yt-dlp não traz data de publicação nem inscritos: a data vem do texto "há 9 horas" só com `extractor_args: {"youtubetab": {"approximate_date": [""]}}` (`radar.LIST_OPTS`), e os inscritos vêm da página do canal. Candidatos achados antes disso não têm `views_per_hour` (o ranking estima com 48 h).
- As fontes da legenda precisam existir no Windows (lista fixa em `captions.FONTS`); o libass troca por outra se não achar.
- **Só um backend por vez.** O `queue.claim_next` não é atômico: dois servidores no mesmo `data/app.db` (ex.: um uvicorn órfão que sobrou depois de fechar o terminal) pegam o mesmo job e o rodam duas vezes. O órfão sem stdout ainda quebra yt-dlp/ffmpeg (`[Errno 22] Invalid argument`, ffmpeg código 3221225794). Antes de subir o dev server, confira se a porta 8000 está livre (`netstat -ano | findstr :8000`) e mate a árvore do processo antigo (`taskkill /T /F /PID ...`).
- `api.ts` só põe `Content-Type: application/json` quando o corpo é string; upload com `FormData` define o próprio boundary.
- Re-render com o mesmo início/fim gera nome com `_v{job_id}` para não sobrescrever o arquivo que pode estar tocando no navegador.

## Testes

- Backend: `pytest`. Testar a lógica pura (parsing de legendas, montagem de comandos ffmpeg, validação do JSON da IA e do PNG, transições de status, contas do Painel/Aquecimento) sem rede.
- Não chamar YouTube nem a API do Claude em testes. Não rodar ffmpeg de verdade: o render é substituído por um fake (`monkeypatch`). Arquivos de teste (PNG, "vídeos") são gerados em `tmp_path`; não há pasta de fixtures.
- Antes de dizer que algo está pronto: rodar testes, lint e typecheck, e verificar o fluxo no navegador quando mexer na UI. Para conferir ffmpeg de verdade, renderize num diretório temporário, não em `data/`.

## Convenções de código

- Python: type hints em tudo, `ruff` (line-length 100), funções pequenas, sem lógica de negócio nas rotas (rotas chamam serviços em `app/*.py`).
- TypeScript: `strict`, componentes funcionais, um componente por arquivo, tipos da API em `src/lib/types.ts`.
- Commits: Conventional Commits em inglês (`feat:`, `fix:`, `chore:` ...).

## Roadmap

1. ~~Colar link → baixar → transcrever → IA escolhe trechos → corte 9:16~~ feito.
2. ~~Aba Aprovar com cards~~ feito.
3. ~~Radar com coleta automática + atualização de views~~ feito.
4. ~~Aba Postagem: fila manual (baixar, copiar texto, marcar como postado)~~ feito, junto com a aba Contas (lista simples).
5. ~~Estúdio (com zoom/enquadramento)~~, ~~Painel~~, ~~Ajustes~~, ~~Aquecimento~~ e ~~Moldura~~ feitos.
6. ~~Legenda queimada estilo TikTok~~ feita.
7. ~~Escolha melhor dos momentos: "mais repetidos" + capítulos, início/fim nas quebras da fala, motivos de recusa e exemplos do editor no prompt~~ feita.
8. ~~Radar escolhe melhor os vídeos: velocidade (views/h para o tamanho do canal) e histórico de aprovação do canal na fila e na triagem~~ feito.

Próximos candidatos: ver `docs/BACKLOG.md` (detecção de bordas desfocadas).
