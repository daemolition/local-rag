# AGENTS.md

High-signal guidance for OpenCode sessions in this repo.

## Project in one line

German Flask RAG app with SSE chat, SQLAlchemy multi-user management, Qdrant hybrid search (dense + sparse/BM25), Pandas analytics tools, and Ollama/OpenAI-compatible LLMs.

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
- Linux/Docker default URL: `http://0.0.0.0:5000`.
- Default admin login: `admin` / `secret123` (or `ADMIN_PASSWORD` from `.env`).
- Both `run_windows.py` and `run_linux.py` run `alembic upgrade head` automatically before starting the server.

## Important: Alembic baseline and existing app.db

- The initial migration (`alembic/versions/0001_initial_schema_and_admin_seed.py`) creates all tables from `app/models.py` and seeds an admin user (`admin` / `admin`).
- `app.db` may already exist, created by `DatabaseService` calling `Base.metadata.create_all()` in `app/__init__.py` (not by Alembic). On an existing `app.db`, `alembic upgrade head` fails with "table already exists" — run `alembic stamp head` to mark it as migrated without executing DDL, or delete `app.db` to start fresh.
- `run_windows.py` / `run_linux.py` run `alembic upgrade head` automatically before starting the server; on a fresh DB this creates the schema + admin seed.
- For schema changes to `app/models.py`: `alembic revision --autogenerate -m "description"`; autogenerate sees the full schema (`env.py` sets `target_metadata = Base.metadata`).

## Lint / format

```bash
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .
```

- Ruff is a project dependency but has **no `[tool.ruff]` config** in `pyproject.toml`; it runs with built-in defaults.
- There is currently no test suite (`tests/` does not exist) and no type checker configured.

## Key architecture facts

- App factory: `app/__init__.py:create_app()`.
- Routes: `app/routes.py` (chat + SSE), `app/admin_routes.py`, `app/user_routes.py`.
- Database service singleton: `app/database_service.py:init_db_service()` / `get_db_service()`. Always close sessions you open.
- Models: `app/models.py`. Settings model is the source of truth for runtime config.
- Settings resolution order: `settings_service.py` reads DB first, then `.env`/environment, then default.
- Qdrant client factory: `app/utils/qdrant_client.py`. Connects to a running Qdrant server at `QDRANT_HOST:QDRANT_PORT` (default `localhost:6333`). No embedded/local file mode.
- Vector collection name is hardcoded to `"local_rag"` and uses hybrid retrieval (`langchain_qdrant` dense + FastEmbedSparse BM25).
- Default embedding dimension is `384`; must match the chosen `EMBEDDING_MODEL`.

## Document ingestion

Dokumente werden **über das Web-Interface** eingelesen. Es ist kein separates CLI-Skript mehr nötig.

- Admin-Panel: **Upload** → Dateien hochladen → **Ingestion starten** (synchron, ruft `app.vector.DocumentIngestion` direkt auf).
- User-Bereich: **Meine Dokumente** → Dateien hochladen → **Ingestion starten**.
- Ingestion erfolgt aus `app/admin_routes.py` und `app/user_routes.py` heraus über `app.vector.DocumentIngestion`.
- Unter Windows wird Qdrant als `qdrant.exe` von `run_windows.py` gestartet (Server-Modus auf `127.0.0.1:6333`), sodass Flask und Ingestion gleichzeitig laufen können.

## File locations

| Type | Location |
|------|----------|
| SQLite app DB | `./app/data/app.db` |
| Legacy chat DB | `./app/data/chat_history.db` (migration target only) |
| Session storage | `./flask_session/` |
| Uploads | `./files/` |
| Analytics data | `./data/` |
| Summaries | `./summaries/` |

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
|--------|-------|
| DB schema / models | `app/models.py` + create Alembic migration |
| DB queries / CRUD | `app/database_service.py` |
| Config/settings | `app/settings_service.py` (also check `env.example`) |
| Admin features | `app/admin_routes.py` + `app/templates/admin/` |
| User features | `app/user_routes.py` + `app/templates/user/` |
| Qdrant wiring | `app/utils/qdrant_client.py`, `app/__init__.py` |
| File operations | `app/utils/file_manager.py` |
| Vector ingestion | `app/vector/ingestion.py`, `app/vector/retriever.py` |
| Agent/system prompt | `app/agent/document_agent.py` |
| LLM wrapper | `app/llm/local_llm.py` |

## Common gotchas

- **SQLite locked:** enable WAL mode or reduce concurrent writers.
- **Settings drift:** Admin panel edits live in the `settings` table. Use `SettingsService(db_session)` to read current values, not stale `.env` defaults.
- **Legacy `app/database.py`:** still called inside `create_app()` for compatibility; new code should use `app/database_service.py`.
- **Embedding dimension mismatch** causes Qdrant collection creation to fail. Keep `EMBEDDING_DIMENSION` in sync with `EMBEDDING_MODEL`.
- **Tesseract/Poppler paths on Windows** should be set via `.env` (`TESSERACT_CMD`, `POPPLER_PATH`) or configured in the PDF loader.
- **Env var name mismatch:** `.env`/`env.example` use `EMBEDDING_DIMENSIONS` (plural), but the code reads `EMBEDDING_DIMENSION` (singular). The plural env value is silently ignored; dimension falls back to the DB setting or default `384`. Keep the singular name when setting it.
- **Qdrant must be running** before starting the app (server mode only; no embedded file fallback). On Windows, `run_windows.py` auto-starts `qdrant.exe`; on Linux, use Docker Compose or run Qdrant separately.
- **Qdrant server migration:** `scripts/manage_qdrant.py` (`uv run python scripts/manage_qdrant.py status|migrate|info`) can move a collection between two Qdrant server instances.

