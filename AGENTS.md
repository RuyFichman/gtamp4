# AGENTS.md

Guia para agentes de IA (Claude Code, Codex, Cursor etc.) que trabalham neste repositório.
Leia inteiro antes de mudar qualquer coisa.

## O que é o projeto

**gtamp4** é uma ferramenta **local e pessoal** (não comercial, um único usuário) que:

1. Encontra vídeos sobre GTA 6 no YouTube (manualmente por link ou automaticamente pelo Radar).
2. Baixa o vídeo e a transcrição.
3. Usa IA para escolher os melhores trechos e dar uma nota de **potencial (0–100)**.
4. Corta cada trecho em vídeo vertical 9:16 com uma **moldura** (overlay) aplicada.
5. Mostra os cortes numa interface web para o usuário **aprovar / recusar / editar / baixar**.
6. Organiza a fila de postagem para TikTok e Instagram. **A postagem é sempre feita manualmente pelo usuário**; o app só prepara o arquivo e o texto.

Tudo roda na máquina do usuário. Não há deploy em nuvem, login nem multi-tenant.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, **FastAPI**, gerenciado com **uv** |
| Banco | **SQLite** via **SQLModel** (arquivo em `data/app.db`) |
| Fila de jobs | Tabela `job` no SQLite + worker em thread (sobrevive a reinícios) |
| Agendador | **APScheduler** (coleta do Radar, atualização de views) |
| Download | **yt-dlp** (vídeo, metadados, legendas) |
| Transcrição | 1º legendas do YouTube via yt-dlp; fallback **faster-whisper** em CPU (`small`, `int8`) |
| IA | **API do Claude** (SDK `anthropic`): uma chamada por vídeo com `MODEL_WRITER` (Sonnet) que escolhe trechos, dá a nota e escreve título/descrição; `MODEL_TRIAGE` (Haiku) fica para filtrar vídeos do Radar. Saída estruturada via `messages.parse` + Pydantic. Sem chave, cai numa heurística por volume |
| Energia da fala | ffmpeg → PCM → **numpy** (RMS por segundo, `pipeline/energy.py`), passada à IA como "energia 0-9" por linha |
| Edição de vídeo | **ffmpeg** (CLI, chamado via `subprocess`) |
| Frontend | **React + Vite + TypeScript + Tailwind** + shadcn/ui |
| Comunicação | REST JSON em `/api/*`; progresso de jobs via polling (ou SSE em `/api/events`) |

## Ambiente da máquina (importante)

- **Windows 11**, Ryzen 5 5600, 16 GB RAM, GPU **AMD Radeon RX 590** (sem CUDA).
- **Não use CUDA.** Whisper roda em CPU. Não adicione dependências que exijam NVIDIA.
- Encoder de vídeo: tente **`h264_amf`** (AMD) e faça fallback automático para **`libx264`** se falhar. A lógica de escolha fica em um único lugar (`backend/app/pipeline/encoder.py`).
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
│   ├── app/
│   │   ├── main.py        # cria o FastAPI, monta rotas, inicia worker e scheduler
│   │   ├── config.py      # Settings (pydantic-settings) lidas do .env
│   │   ├── db.py          # engine SQLite + sessão
│   │   ├── models.py      # tabelas SQLModel
│   │   ├── api/           # um arquivo de rotas por aba (clips.py, radar.py, ...)
│   │   ├── jobs/          # fila, worker, tipos de job
│   │   ├── pipeline/      # download, transcribe, score, cut, frame, encoder
│   │   └── scheduler.py
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── pages/         # uma página por aba
│       ├── components/
│       └── lib/api.ts     # cliente da API (único lugar que faz fetch)
└── data/                  # NÃO versionado: app.db, videos/, clips/, frames/, cache/
```

## Abas da interface (glossário do domínio)

| Aba | Função |
|---|---|
| **Painel** | Estatísticas (`GET /api/stats`, calculadas em `app/stats.py`): fila de aprovação/postagem, taxa de aprovação, cortes por dia (14 dias, fuso da máquina), potencial médio aprovados vs. recusados, postados por conta, Radar, jobs, disco. Gráfico em SVG próprio (sem lib), cores validadas para daltonismo |
| **Aprovar** | Colar link do YouTube, ver fila de processamento, cards de corte (aprovar, recusar, estúdio, baixar) |
| **Postagem** | Cortes aprovados aguardando postagem manual: baixar vídeo, copiar título/descrição/hashtags, escolher a conta e marcar como "postado" (com link do post, opcional) |
| **Contas** | Lista das contas de TikTok / Instagram do usuário (nome, @, plataforma, notas). Só para organização: **sem tokens, sem login, sem integração** |
| **Aquecimento** | Checklist **manual** de 14 dias por conta (`app/warmup.py`: 3 fases, tarefas diárias e "uma vez", tabela `warmupcheck`, dia local da máquina). Só registra o que o usuário marcou; nunca automatizar (ver Regras) |
| **Radar** | Busca automática de vídeos novos de GTA 6 por termos/canais, com intervalo configurável |
| **Moldura** | PNGs 9:16 com transparência (`app/frames.py`: valida assinatura, proporção e alfa só com stdlib; arquivos em `data/frames/`). Uma moldura "em uso" (ou nenhuma) vale para renders novos; "Re-renderizar cortes" enfileira `render_clip` para os pendentes/aprovados. Prévia no navegador com CSS por cima de um corte |
| **Estúdio** | Ajuste fino de um corte: início/fim, título, descrição; re-renderiza |
| **Ajustes** | `AppConfig` (`store.py`, tabela `setting`): duração mín/máx e nº de cortes, encoder, modelo do Whisper, modelos do Claude. Os jobs leem a config e passam explicitamente ao pipeline (o pipeline não lê o banco). A chave da API **não** é editável aqui (fica no `.env`). Também: limpeza dos vídeos originais cujos cortes já foram todos postados/recusados |

Cada card de corte mostra: player, título, **views do vídeo original**, **data da consulta**, link "Ver fonte no YouTube", botão "Atualizar views", **Potencial x/100** com o motivo, e a descrição gerada.

## Modelo de dados (resumo)

- `SourceVideo`: youtube_id, url, título, canal, idioma, duração, views, views_checked_at, transcrição.
- `Clip`: source_video_id, start, end, título, descrição, hashtags, potential (0–100), potential_reason, file_path, status.
- `Job`: tipo, payload (JSON), status, progresso, mensagem, erro, tentativas, timestamps.
- `Account`, `FrameTemplate`, `RadarQuery`, `Setting`.

**Status de `Clip`:** `pending_review` → `approved` | `rejected` → `posted` (marcado manualmente pelo usuário).
**Status de `Job`:** `queued` → `running` → `done` | `failed`. Ao iniciar o app, jobs `running` voltam para `queued` ("Retomando após reinício").

## Pipeline de um vídeo

1. `download`: yt-dlp baixa vídeo (máx. 1080p), metadados e legendas (manual > automática, **no idioma original**).
2. `transcribe`: usa a legenda; se não houver, faster-whisper em CPU. Resultado: segmentos com timestamps.
3. `energy` + `score`: mede o volume por segundo; Claude recebe transcrição anotada com energia + metadados e devolve trechos (start, end, potential, reason, title, description, hashtags). `sanitize()` limita duração (12–75 s) e quantidade (≤5).
4. `cut`: ffmpeg corta, reenquadra para 1080x1920 (fundo desfocado + vídeo centralizado), aplica a moldura em uso se houver, normaliza áudio (`loudnorm`). Arquivo: `data/clips/{youtube_id}_{start}-{end}.mp4`.
5. Cria `Clip` com status `pending_review` só depois do arquivo renderizado.

Tudo isso roda no job `process_video` (`backend/app/jobs/handlers.py`).

## Estúdio

- Abre num painel (`StudioModal`) pelo botão "Estúdio" dos cards (Aprovar e Postagem). Não é uma aba.
- `GET /api/clips/{id}/studio`: corte, vídeo original (`/api/media/videos/`, com Range, então dá para pular no player), transcrição e o job de render pendente.
- `PATCH /api/clips/{id}`: o texto é salvo na hora. Início/fim novos (3 a 180 s) viram um job `render_clip`; o `Clip` só muda depois do render dar certo. O arquivo novo se chama `{youtube_id}_{clip_id}_{start}-{end}.mp4` (com `_v{job_id}` se o nome repetir, ex.: só trocou a moldura); o antigo é apagado se nenhum outro corte usa. Um render por corte de cada vez (409).
- **Enquadramento:** `Clip.zoom` (1–3) e `pan_x`/`pan_y` (-1..1) mudam só o vídeo do meio (`cut.Framing`, `foreground_filter`: escala para 1080·zoom e recorta na tela 1080x1920). Prévia em CSS com a mesma geometria (`FramingPreview`). "Automático" (`GET /api/clips/{id}/autoframe`, `pipeline/framing.py`) usa `cropdetect` e só acha barras pretas. Mudar só o enquadramento também gera `render_clip`; jobs sem as chaves de enquadramento mantêm o do corte.
- Se o vídeo original foi apagado do disco, o job baixa de novo.

## Radar

- `scheduler.py`: um tick do APScheduler a cada 1 min lê a config do banco (`store.py`, tabela `setting`) e só **enfileira** jobs: `radar_scan` no intervalo escolhido (se ligado) e `refresh_views` a cada 3 h. O worker executa. Nunca publica nada.
- `radar_scan` (`jobs/radar_jobs.py`):
  1. roda cada `RadarQuery` ativa (`pipeline/radar.py`, yt-dlp com `extract_flat`, sem baixar);
  2. ignora vídeos já vistos (`RadarCandidate`) ou já processados (`SourceVideo`);
  3. aplica o pré-filtro (duração 90 s a 3 h, sem live);
  4. faz a triagem por título com Haiku (`pipeline/triage.py`; sem chave, regex "GTA 6/VI");
  5. envia os aprovados para `process_video`, os mais vistos primeiro, até o **limite diário** (envios que falharam não contam);
  6. quem fica "na espera" por mais de 3 dias é descartado.
- `RadarCandidate.status`: `rejected` | `waiting` | `sent`. "Cortar mesmo assim" na UI ignora triagem e limite.

Cada etapa é idempotente: se o arquivo de saída já existe e é válido, pula.

## Regras

- **Idioma:** títulos, descrições e hashtags são gerados **sempre no idioma original do vídeo**. Não traduzir.
- **UI em português (pt-BR).** Código, nomes de variáveis, funções, tabelas e commits em **inglês**.
- **Segredos** só no `.env` (raiz do repo ou `backend/.env`, que tem prioridade). Nunca commitar `.env`, nunca logar chaves. Manter `.env.example` atualizado.
- **`data/` nunca é versionado.**
- **Sem automação de aquecimento de contas** (curtir/rolar feed com bot). Viola os termos do TikTok/Instagram e causa ban. A aba Aquecimento é só checklist manual.
- **Postagem é 100% manual (decisão do usuário).** Não implementar postagem automática de nenhum tipo: nem APIs oficiais, nem automação de navegador, nem agendamento que publique sozinho. O app apenas prepara o vídeo e o texto e registra o que o usuário marcou como postado.
- Chamadas ao Claude: só em `backend/app/pipeline/score.py` (cortes, Sonnet) e `pipeline/triage.py` (Radar, Haiku), com model ID vindo de config. Validar resposta com Pydantic; em JSON inválido, tentar de novo uma vez e então marcar o job como `failed` com mensagem clara.
- Chamadas ao ffmpeg/yt-dlp: sempre via helper que captura stderr e grava as últimas linhas no `Job.error`. Nunca engolir erros (ex.: "ffmpeg exited with code ..." precisa vir com o motivo).
- Mensagens de erro mostradas na UI devem ser em português e acionáveis.
- Não adicionar dependências pesadas sem necessidade; preferir a stdlib.
- Funcionalidades adiadas vão para `docs/BACKLOG.md`, não para o código como TODO solto.

## Comandos

> Pré-requisitos: `uv`, Node 24, `ffmpeg` no PATH (`winget install Gyan.FFmpeg`).

```powershell
# Backend
cd backend
uv sync                                   # instala dependências
uv run fastapi dev app/main.py --port 8000   # dev server
uv run pytest                             # testes
uv run ruff check . ; uv run ruff format .   # lint + format

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxy /api -> :8000)
npm run build
npm run lint
npx tsc --noEmit   # typecheck
```

## Armadilhas conhecidas

- SQLModel exige datetimes **com fuso** (`utcnow()` de `app.models`); comparar com datetime "naive" dá erro 500.
- yt-dlp precisa de runtime JS para o YouTube: usamos Node (`js_runtimes: {"node": {}}` em `pipeline/download.py`) e o pacote `yt-dlp[default]`.
- Um terminal aberto antes de instalar o ffmpeg não o enxerga no PATH: abra um terminal novo.
- yt-dlp desta versão não tem o atalho `ytsearchdate`: o Radar usa a URL `youtube.com/results?search_query=...&sp=CAI%3D` (ordenado por data).
- `create_all` não altera tabelas existentes. `db.add_missing_columns()` adiciona colunas novas no startup (com default escalar ou NULL). Para renomear ou apagar coluna, escreva a migração à mão.
- O YouTube às vezes responde "confirm you're not a bot" ou "video unavailable". `proc.explain_error()` põe uma dica em pt-BR acima do erro cru.
- O prompt da IA é em português; sem o idioma explícito, a IA escrevia títulos de vídeos em inglês em português. Por isso `plan_with_claude` recebe `language` e o `ClipPlan` tem `video_language` preenchido antes dos cortes. Só `reason` é em pt-BR. Não remova isso.

## Testes

- Backend: `pytest`. Testar a lógica pura (parsing de legendas, montagem de comandos ffmpeg, validação do JSON da IA, transições de status) sem rede.
- Não chamar YouTube nem a API do Claude em testes: usar fixtures/mocks. Um vídeo curto de fixture fica em `backend/tests/fixtures/`.
- Antes de dizer que algo está pronto: rodar testes, lint e typecheck, e verificar o fluxo no navegador quando mexer na UI.

## Convenções de código

- Python: type hints em tudo, `ruff` (line-length 100), funções pequenas, sem lógica de negócio nas rotas (rotas chamam serviços).
- TypeScript: `strict`, componentes funcionais, um componente por arquivo, tipos da API em `src/lib/types.ts`.
- Commits: Conventional Commits em inglês (`feat:`, `fix:`, `chore:` ...).

## Roadmap

1. ~~Colar link → baixar → transcrever → IA escolhe trechos → corte 9:16~~ feito (moldura vai no item 5).
2. ~~Aba Aprovar com cards~~ feito.
3. ~~Radar com coleta automática + atualização de views~~ feito.
4. ~~Aba Postagem: fila manual (baixar, copiar texto, marcar como postado)~~ feito, junto com a aba Contas (lista simples).
5. ~~Estúdio~~ (com zoom/enquadramento), ~~Painel~~, ~~Ajustes~~, ~~Aquecimento~~ e ~~Moldura~~ feitos.

Itens adiados: ver `docs/BACKLOG.md`.
