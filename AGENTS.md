# AGENTS.md

High-signal guidance for OpenCode sessions in this repo.

## Project in one line

German Flask RAG app with SSE chat, single-user app-password login (no accounts), SQLAlchemy settings/chat/document tracking, Qdrant hybrid search (dense + sparse/BM25), Pandas analytics tools, and Ollama/OpenAI-compatible LLMs.

## Entry points and run commands

```bash
# Install dependencies (uses uv)
uv sync

# Windows (no admin required; auto-downloads qdrant.exe)
start.bat
# Or directly
python run_windows.py              # with local Qdrant
python run_windows.py --no-qdrant  # if you run Qdrant separately

# Linux / Docker
alembic upgrade head
python run_linux.py
docker-compose up --build
```

- Windows default URL: `http://127.0.0.1:5000` (localhost only; no firewall prompt).
- Linux/Docker host port: `docker-compose up` maps `8083:5000` (host:container) — the app is on `http://localhost:8083`, not 5000. The README's "http://localhost:5000" Docker note is stale.
- Linux manual (`python run_linux.py`, no Docker) binds `0.0.0.0:5000`.
- Default app login: single app-password (no username). Default password `admin`, overridable via `ADMIN_PASSWORD` env on a fresh DB; afterwards managed via *Einstellungen → Passwort ändern*. Auth sets `session['authenticated']` (see `app/auth.py`); the hash lives in the `APP_PASSWORD_HASH` setting row.
- Both `run_windows.py` and `run_linux.py` run `alembic upgrade head` automatically before starting the server.

## Important: Alembic baseline and existing app.db

- The initial migration (`alembic/versions/0001_initial_schema_and_admin_seed.py`) creates all tables and seeds an admin user (`admin` / `admin`).
- Migration `0002_single_user_conversion.py` drops the `users` table, moves the admin password hash into the `APP_PASSWORD_HASH` setting row, and removes all `user_id` FKs (single-user). `0003_embedding_model_prefix.py` rewrites `EMBEDDING_MODEL` to the HF-org-prefixed form fastembed needs.
- `app.db` may already exist, created by `DatabaseService` calling `Base.metadata.create_all()` in `app/__init__.py` (not by Alembic). On an existing `app.db`, `alembic upgrade head` fails with "table already exists" — run `alembic stamp head` to mark it as migrated without executing DDL, or delete `app.db` to start fresh.
- `run_windows.py` / `run_linux.py` run `alembic upgrade head` automatically before starting the server; on a fresh DB this creates the schema + admin seed.

## Lint / format

```bash
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .
```

- Ruff is a project dependency but has **no `[tool.ruff]` config** in `pyproject.toml`; it runs with built-in defaults.
- There is currently no test suite (`tests/` does not exist) and no type checker configured.

## Key architecture facts

- App factory: `app/__init__.py:create_app()`. Qdrant client + collection creation run synchronously (needed immediately by document routes); loading the embedding model and building the vectorstore/retriever/agent happens in a background thread (`init_resources` → `_load_resources`) so container startup doesn't block on a model download. Code needing `app.extensions["agent"]`/`"dense_embeddings"` must gate on `wait_for_resources(timeout=...)` first (see `user_routes.py:trigger_ingestion`).
- Routes: `app/routes.py` (chat + SSE, no prefix), `app/user_routes.py` (`/user`). The former `/admin` blueprint was removed; dashboard, vector DB, settings, summaries, and uploads now live under `/user`.
- Database service singleton: `app/database_service.py:init_db_service()` / `get_db_service()`. Every method opens its own session and closes it in `finally` before returning — see the DetachedInstanceError gotcha below.
- Models: `app/models.py`. Settings model is the source of truth for runtime config.
- Settings resolution order: `settings_service.py` reads DB first, then `.env`/environment, then default. A stale DB row silently wins over a correct env var indefinitely — check the `settings` table first when an env var "doesn't take effect".
- Qdrant client factory: `app/utils/qdrant_client.py`. Connects to a running Qdrant server at `QDRANT_HOST:QDRANT_PORT` (default `localhost:6333`). No embedded/local file mode.
- Vector collection name is hardcoded to `"local_rag"` and uses hybrid retrieval (`langchain_qdrant` dense + FastEmbedSparse BM25). One Qdrant point per chunk; all chunks of one ingested file share a `file_group_id` payload value, which file-level list/delete operations filter on (a file is never one point).
- Default embedding dimension is `384`; must match the chosen `EMBEDDING_MODEL`.
- Shared knowledge base, not per-user silos: any document uploaded by anyone is retrievable by everyone in chat (intentional). `UserDocument`/`UserSummaryFile` rows are ownership bookkeeping for the "my documents"/"my analyses" management UI, not an access-control boundary — retrieval is never filtered by uploader.
- `app/tools/custom_tools.py:CustomTools` is instantiated **once** at app startup and shared across every request — it has no per-request state. Summary tracking (`_track_summary_for_current_user`) calls `get_db_service()` directly (single-user, no Flask session inspection needed).
- Linux/Docker runs `gunicorn -w 1 --threads 4 -k gthread` (`run_linux.py`). Worker count must stay at 1 — several module-level globals are process-wide, not per-worker-safe (`app/__init__.py`'s `_qdrant_client`/`_db_service`, `app/user_routes.py`'s shared ingestion status). Threads exist so a long-lived SSE chat stream doesn't block every other request app-wide.
- Tailwind CSS is precompiled at Docker build time (standalone CLI against `app/templates/**`/`app/static/js/**` → `app/static/css/tailwind.css`, binary then deleted). No live watch/dev-server — new utility classes in templates only take effect after an image rebuild. Dark mode is **not** configured — `darkMode: 'class'` was removed from `tailwind.config.js`; do not add `dark:` variants to templates.
- The embedding model is baked into the Docker image at build time (`ARG EMBEDDING_MODEL`, downloaded into the fastembed ONNX cache during build). Default `EMBEDDING_SOURCE=local` uses `FastEmbedEmbeddings` (ONNX) from `langchain_community` — no PyTorch overhead. Setting `EMBEDDING_SOURCE=endpoint` switches to `OpenAIEmbeddings` (langchain_openai) pointed at `EMBEDDING_ENDPOINT` with `API_KEY`. Changing the `EMBEDDING_MODEL` setting at runtime without rebuilding with a matching `--build-arg` means the new model downloads on demand instead of using the prebuilt cache. fastembed requires the HF-org-prefixed model name (e.g. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, not the bare `paraphrase-multilingual-MiniLM-L12-v2`).
- Image extraction with VisionLLM is not limited to PDF. DOCX/DOC/ODT use `CustomDOCXLoader` → `PreprocessDOCX` which opens the file as a ZIP, extracts images from `word/media/`, and processes them in paragraph order via `python-docx` so `[BILD-BESCHREIBUNG: ...]` markers land at the correct text-flow position. PDF uses `CustomPDFLoader` → `PreprocessPDF` with `partition_pdf(extract_images_in_pdf=True)`. Both inherit from `PreprocessBase` (`app/components/preprocess_base.py`) which holds the shared dedup/encode/VisionLLM/chunk-building logic. Markdown (`.md`) uses `UnstructuredMarkdownLoader` — images are links, not embedded binaries, so no VisionLLM processing.
- `langchain-huggingface` is **not** a dependency. Local embedding is ONNX-based via `FastEmbedEmbeddings` + `FastEmbedSparse`; `EMBEDDING_SOURCE=endpoint` uses `OpenAIEmbeddings` (langchain_openai). The `retriever.py` standalone class still reads from env (not DB) — it's not in the active app path but kept for scripts.

## Document ingestion

Dokumente werden **über das Web-Interface** eingelesen. Es ist kein separates CLI-Skript mehr nötig.

- Dokumente-Bereich (`/user/documents`) und Vektordatenbank-Bereich (`/user/vectordb`): Dateien hochladen → **Ingestion starten**. Ingestion läuft synchron (`app.vector.DocumentIngestion.ingest_documents()`, aufgerufen aus `app/user_routes.py`) — der Request blockiert bis Ingestion fertig ist, kein Hintergrund-Job/Queue.
- Uploads landen zunächst flach in `data/files/<filename>`. Nach erfolgreicher Ingestion wandern PDF/DOCX nach `data/processed_files/<filename>`, CSV/XLSX nach `DATA_DIR` (Kollisionsschutz per Timestamp-Suffix).
- Unter Windows wird Qdrant als `qdrant.exe` von `run_windows.py` gestartet (Server-Modus auf `127.0.0.1:6333`), sodass Flask und Ingestion gleichzeitig laufen können.

## File locations

| Type | Location |
| ---- | -------- |
| SQLite app DB | `data/app.db` (not `app/data/app.db`) |
| Session storage | Flask cookie sessions (client-side, signed via `SECRET_KEY`) |
| Pending uploads | `data/files/` |
| Ingested PDF/DOCX archive | `data/processed_files/` |
| Ingested CSV/XLSX (`DATA_DIR` setting) | `data/` |
| Markdown analyses (`SUMMARIES_DIR` setting) | `data/summaries/` |

## Code conventions

- German UI, tool descriptions, system prompt, and user-facing errors.
- Imports grouped: stdlib → third party → local, separated by blank lines.
- Use `SettingsService` for config access; fall back to `os.getenv` only where the DB session is unavailable.
- Use `get_db_service()` for DB access; close sessions explicitly.
- Pydantic input models for LangChain tools, with German `description` fields.
- Path validation: resolve with `Path` and assert the result stays under `DATA_DIR`/`SUMMARIES_DIR`.

## Security guardrails to preserve

- `run_pandas` tool blocks `os.`, `sys.`, `subprocess`, `__import__`, `open(`, `eval(`, `exec(`, and write methods like `to_csv`/`to_sql`/`to_json`.
- Do not relax these blocks without explicit user approval.

## What to touch when changing...

| Change | Files |
| ------ | ----- |
| DB schema / models | `app/models.py` + create Alembic migration |
| DB queries / CRUD | `app/database_service.py` |
| Config/settings | `app/settings_service.py` (also check `env.example`) |
| User features (documents, vector DB, settings, summaries, dashboard) | `app/user_routes.py` + `app/templates/user/` |
| Qdrant wiring | `app/utils/qdrant_client.py`, `app/__init__.py` |
| File operations | `app/utils/file_manager.py` |
| Vector ingestion | `app/vector/ingestion.py`, `app/vector/retriever.py` |
| Document preprocessing / image extraction | `app/components/preprocess_base.py`, `preprocess_pdf.py`, `preprocess_docx.py`, `custom_pdf_loader.py`, `custom_docx_loader.py` |
| Agent/system prompt | `app/agent/document_agent.py` |
| LLM wrapper | `app/llm/local_llm.py` |

## Common gotchas

- **SQLite locked:** enable WAL mode or reduce concurrent writers.
- **Settings drift:** Admin panel edits live in the `settings` table and win over `.env`/environment variables silently and indefinitely — a stale DB row can override a correct env var forever. Check the `settings` table before trusting `.env` when something "doesn't take effect" (bit us with `QDRANT_HOST` stuck at `localhost` from an old run). `env.example` contains only Qdrant infra vars and OCR paths — all app config (LLM, embedding, retriever, storage, API keys, STT) lives in the `settings` table.
- **API_KEY no longer needs `.env`:** `API_KEY` is read from the settings DB (like all other config), with `os.getenv` only as standalone fallback. The `docker-compose.yml` no longer passes `API_KEY` as an environment variable. The settings DB row is seeded with default `'ollama'` on first migration.
- **Embedding dimension mismatch** causes Qdrant collection creation to fail. Keep `EMBEDDING_DIMENSION` in sync with `EMBEDDING_MODEL`. Embedding/LLM/retriever config lives entirely in the `settings` table now — `env.example` only has Qdrant infra vars and OCR paths, not model/dimension config.
- **Embedding backend change requires re-ingestion:** switching from Torch (`HuggingFaceEmbeddings`) to ONNX (`FastEmbedEmbeddings`) changes vector values for the "same" model — old and new vectors coexist in the collection with slightly different geometries. Re-ingest all documents after swapping backends.
- **Tesseract/Poppler paths on Windows** should be set via `.env` (`TESSERACT_CMD`, `POPPLER_PATH`) or configured in the PDF loader.
- **Qdrant must be running** before starting the app (server mode only; no embedded file fallback). On Windows, `run_windows.py` auto-starts `qdrant.exe`; on Linux, use Docker Compose or run Qdrant separately.
- **Qdrant server migration:** `scripts/manage_qdrant.py` (`uv run python scripts/manage_qdrant.py status|migrate|info`) can move a collection between two Qdrant server instances.
- **DetachedInstanceError risk:** `DatabaseService` methods close their session before returning ORM objects. Any relationship on a returned object (e.g. `ChatSession.messages`, `Message.session`) not eager-loaded (`joinedload`) raises `DetachedInstanceError` the moment it's accessed later — already happened once with `get_summary_by_filename` (a relationship access). Plain columns are always safe; relationships are not unless eager-loaded.
- **"Tracking" DB writes are easy to forget to wire up:** `add_document()`/`create_summary_file()` existed with zero callers for a while — files were written/ingested correctly but silently never appeared in the "my documents"/"my analyses" UI because nothing called the DB-row-creating method. When adding a "create X and track it" flow, grep for actual callers, don't assume it's wired in just because the method exists.
- **Gunicorn worker count:** stay at `-w 1` (see architecture facts above) — multiple worker processes would each get their own copy of the module-level globals several routes depend on.
- **fastembed mean-pooling change:** fastembed ≥0.6 switched `paraphrase-multilingual-MiniLM-L12-v2` from CLS-token to mean pooling. Vectors embedded with fastembed ≤0.5.1 (CLS) are NOT compatible with new embeddings — re-ingest all documents after upgrading fastembed. The `UserWarning` about this is intentionally suppressed in `app/__init__.py` (the new behaviour is correct); don't remove that filter without a reason.
- **SearXNG JSON API needs explicit opt-in:** `docker-compose.yml`'s `searxng` service is configured via the checked-in `searxng/settings.yml`. By default SearXNG only serves HTML and its bot-protection limiter blocks non-browser requests — both `search.formats: [html, json]` and `server.limiter: false` are required there, otherwise `web_search_tool.py`'s `format=json` requests come back empty/403. `server.secret_key` must NOT be left as `ultrasecretkey` — newer SearXNG images hard-refuse to start with that literal value instead of auto-generating a replacement (older versions did); the checked-in file has a pre-generated random hex value, regenerate your own with `openssl rand -hex 32` for real deployments. `SEARCH_SEARXNG_URL` defaults to `http://searxng:8080` on a fresh DB (migration `0004`).
- **entityguard PII-filter service:** `docker-compose.yml`'s `entityguard` service (`registry.nutsolution.de/entityguard:latest`, port `9500`, no host port mapped) is the PII-filter backend for `app/utils/pii_filter_client.py`. Its `/api/v1/sanitize` endpoint returns `mapping` as a **flat dict** `{"[NAME_1]": "Max Mustermann", ...}`, not a list of `{"placeholder":..., "original":...}` objects — `PIIFilterClient.demask()` handles both shapes (dict branch added after finding the mismatch would otherwise `AttributeError` on the first real call). `PII_FILTER_URL` defaults to `http://entityguard:9500/api/v1/sanitize` on a fresh DB (migration `0004`).
- **parakeet STT service needs a GPU (or explicit CPU build):** `docker-compose.yml`'s `parakeet` service (built from `parakeet/Dockerfile`, multi-stage `ARG DEVICE=gpu|cpu` selecting `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` vs `python:3.12-slim`) requires the NVIDIA Container Toolkit on the host for the GPU build — the `deploy.resources.reservations.devices` GPU reservation block works with plain `docker compose up` (no Swarm needed) as of Compose v2, but the container won't start without a real GPU + toolkit unless built with `--build-arg DEVICE=cpu`. The Dockerfile has a benign internal quirk: `ARG DEVICE=gpu` (before the first `FROM`, used to pick the base image) and a *separately re-declared* `ARG DEVICE=cpu` (inside the final stage, used only for an otherwise-unused `ENV DEVICE=${DEVICE}`) have different defaults — harmless as long as `docker-compose.yml` always passes `args: {DEVICE: gpu}` explicitly (which it does), since a single `--build-arg`/`args:` value overrides every `ARG` declaration of that name throughout the build. Models are preloaded at build time (Parakeet ASR into the default HF cache, Silero VAD into a flat `/app/models/silero-vad` dir — `onnxruntime` rejects the HF cache's symlink-into-`blobs/` layout for the raw VAD session driven directly in `streaming.py`). `STT_BASEURL`/`STT_MODEL` default to `http://parakeet:5001/v1`/`nemo-parakeet-tdt-0.6b-v3` on a fresh DB. **The actual seed source is `alembic/versions/0002_single_user_conversion.py`** (`ON CONFLICT(key) DO NOTHING` insert), not `app/database_service.py:_init_settings()` — that Python dict has its own STT entries too, but they're dead code for a fresh install: migration 0002 always runs first (`run_linux.py`/`run_windows.py` both run `alembic upgrade head` before starting the server) and already inserts the row, so `_init_settings()`'s "insert if not exists" check finds it present and skips it. Keep both in sync if changing STT defaults again — easy to edit only one and have it silently not take effect (this bit us once: editing `database_service.py` alone left fresh installs still pointing at the old `whisper` URL). The batch `/api/stt` route (`app/routes.py`) still works against this same URL and is kept as a server-side fallback, but the chat UI's mic button no longer calls it.
- **Live STT streaming needs `flask-sock` + a background relay thread:** `app/stt_stream.py` exposes `/ws/stt-stream`, a WebSocket endpoint (via `flask-sock`/`simple-websocket`, WSGI-socket-hijacking) that proxies raw float32 PCM from the browser to Parakeet's own `/v1/audio/stream` WebSocket (a plain synchronous `websocket-client` connection opened per browser session) and relays `partial`/`committed`/`final`/`error` JSON messages back. This only works under `gunicorn -k gthread` (the Linux/Docker path, `run_linux.py`) — **not** under `waitress` (`run_windows.py`), which has no socket-hijacking support, so live streaming STT is Docker-only; Windows users only get the batch `/api/stt` fallback. Each open recording occupies one of the app's 4 gunicorn threads for its whole duration (shares the pool with SSE chat streams) — fine for the single-user design, but don't lower `--threads` without checking this.
- **`parakeet/streaming.py`'s `ParakeetStreamEngine` must reuse `main.py`'s already-loaded ASR model, not load its own:** loading the ~0.6B-param Parakeet model a second time (one copy for the batch endpoint via `main.py`'s `get_model()`, a separate copy for the streaming engine) doubles GPU memory usage for the exact same weights — this OOM'd on a shared/modest GPU during verification (a 16MB Silero-VAD allocation failed only because the second ASR copy had already exhausted VRAM). Fixed by passing `asr_model=get_model()` into `parakeet_stream_engine.ensure_loaded()` in `main.py`'s lifespan handler; `ensure_loaded()`/`_load()` skip the redundant `onnx_asr.load_model()` call when given one. Also: the raw Silero VAD `onnxruntime.InferenceSession` in `streaming.py` is forced to `CPUExecutionProvider` regardless of the ASR provider — it's tiny (~2MB) and this avoids contending with the ASR model for GPU memory entirely.

