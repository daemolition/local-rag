# AGENTS.md

Guidelines for agentic coding agents working in this repository.

## Project Overview

Local Document RAG - A German-language RAG (Retrieval-Augmented Generation) system with Flask web interface, SSE streaming, Pandas analytics, and multi-user management with SQLAlchemy.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask Application                        │
├─────────────────────────────────────────────────────────────────┤
│  Database: SQLAlchemy (SQLite) with Alembic Migrations        │
│  Auth: Session-based (admin/user roles via SQLAlchemy)          │
│  ORM Models: User, ChatSession, Message, UserDocument, etc.    │
└────────────────────────────────────┬────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌─────────┐      ┌──────────┐     ┌──────────┐
              │  Admin   │      │  User    │     │  Chat    │
              │  Panel   │      │  Routes  │     │  (SSE)   │
              └─────────┘      └──────────┘     └────┬─────┘
                                                       │
                                                       ▼
                                              DocumentAgent
                                                       │
                                                       ▼
                                              LLM (Ollama)
```

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Models** | `app/models.py` | SQLAlchemy ORM (User, ChatSession, Message, UserDocument, UserSummaryFile, Setting) |
| **Database Service** | `app/database_service.py` | CRUD operations, DB singleton |
| **Settings Service** | `app/settings_service.py` | Environment/DB settings with fallback |
| **Admin Routes** | `app/admin_routes.py` | Admin panel (settings, users, summaries) |
| **User Routes** | `app/user_routes.py` | User routes (documents, summaries) |
| **File Manager** | `app/utils/file_manager.py` | File operations with Qdrant metadata |
| **Qdrant Client** | `src/utils/qdrant_client.py` | Qdrant factory (local/remote) |
| **Qdrant Manager** | `scripts/manage_qdrant.py` | Migration between local/remote Qdrant |
| **Session Migrator** | `scripts/migrate_sessions.py` | Legacy chat_history.db migration |

## Build/Lint/Test Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Windows (no admin required)
start.bat
# OR
python run_windows.py

# Linux
alembic upgrade head
python run_linux.py

# Docker
docker-compose up --build

# Ingest documents
uv run python ingest_documents.py

# Qdrant migration (local ↔ remote)
python scripts/manage_qdrant.py status
python scripts/manage_qdrant.py migrate --from local --to-remote --dry-run

# Alembic migrations
alembic upgrade head                    # Apply all migrations
alembic revision --autogenerate -m "desc"  # Create new migration
alembic downgrade -1                   # Rollback one

# Linting
uv run ruff check .
uv run ruff check --fix .              # Auto-fix issues
uv run ruff format .

# Run single test file (if tests exist)
uv run pytest tests/test_file.py -v
uv run pytest tests/test_file.py::test_function -v
```

## Code Style Guidelines

### Imports

Order imports in three sections separated by blank lines:
1. Standard library (e.g., `import os`, `from pathlib import Path`)
2. Third-party packages (e.g., `import pandas as pd`, `from langchain_core...`)
3. Local modules (e.g., `from src.llm.local_llm import VisionLLM`)

```python
# Standard library
import os
import io
from logging import getLogger

# Third party
import pandas as pd
from pydantic import BaseModel, Field
from langchain_core.tools import create_retriever_tool
from sqlalchemy.orm import Session

# Local imports
from src.utils.phase_logger import phase_logger, Phase
from app.database_service import get_db_service
from app.settings_service import SettingsService
```

### Formatting

- Line length: 120 characters maximum
- Use double quotes for strings by convention
- Run `uv run ruff format .` before committing

### Naming Conventions

- **Functions/variables**: `snake_case` (e.g., `list_files`, `get_dataframe`)
- **Classes**: `PascalCase` (e.g., `DocumentAgent`, `CustomTools`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DATA_DIR`, `SYSTEM_PROMPT`)
- **Private methods**: prefix with underscore (e.g., `_get_dataframe`, `_detect_encoding`)

### Type Hints

Use Pydantic models for tool inputs with descriptive docstrings:

```python
class PreviewDataInput(BaseModel):
    """Input model for preview_data tool."""
    filename: str = Field(
        description="Name der Datei aus der Dateiliste (z. B. 'sales_2024.xlsx')"
    )
    rows: int = Field(
        default=5,
        description="Anzahl der Zeilen für die Vorschau (Standard: 5)"
    )
```

### SQLAlchemy Patterns

**Database Access:**
```python
# Get database service
db = get_db_service()

# CRUD operations
user = db.create_user("username", "password", is_admin=False)
sessions = db.list_sessions(user.id)
messages = db.get_messages(session_id)
```

**Session Handling:**
```python
# Always close sessions!
db = get_db_service()
try:
    user = db.get_user_by_username(username)
    # ... operations ...
finally:
    db.close()
```

### Error Handling

Catch specific exceptions and return user-friendly error messages in German:

```python
try:
    df = self._get_dataframe(filename)
except Exception as e:
    logger.error(f"Fehler beim Laden von {filename}: {e}")
    return f"FEHLER beim Laden von '{filename}': {type(e).__name__}: {e}"
```

### Comments and Docstrings

- Use triple quotes for module/class/method docstrings
- Comments should be in German (matching the application language)
- Keep docstrings concise but descriptive

```python
def list_files(self) -> list[str]:
    """Listet alle xlsx/csv Dateien im Datenverzeichnis auf."""
```

### Logging

Use the phase_logger for tool execution tracking and standard logging for errors:

```python
from src.utils.phase_logger import phase_logger, Phase

phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool: {tool_name}")
logger = getLogger(__name__)
logger.error(f"Fehler: {e}")
```

### Environment Variables

Access configuration via SettingsService with fallback:

```python
# Good
settings = SettingsService(db.get_session())
data_dir = settings.get('DATA_DIR', './data')

# Legacy fallback still supported
import os
data_dir = os.getenv("DATA_DIR", "./data")
```

### Security Considerations

**When executing dynamic code (like `run_pandas`):**

```python
forbidden_keywords = [
    "os.", "sys.", "subprocess", "__import__", "open(",
    "to_csv", "to_sql", "to_json", "eval(", "exec("
]
```

**File Path Security:**

```python
from pathlib import Path

# Always validate paths
file_path = Path(data_dir) / filename
if not str(file_path).startswith(str(data_dir)):
    raise ValueError("Ungültiger Pfad")
```

## Database Schema (SQLAlchemy)

### Core Models

```python
class User(Base):
    id: int
    username: str (unique)
    password_hash: str
    is_admin: bool
    created_at: datetime
    
class ChatSession(Base):
    id: str (UUID)
    user_id: int (FK → User)
    title: str
    created_at: datetime
    updated_at: datetime
    
class Message(Base):
    id: int
    session_id: str (FK → ChatSession)
    role: str ('user' | 'assistant')
    content: str
    created_at: datetime
    
class UserDocument(Base):
    id: int
    user_id: int (FK → User)
    document_id: str (Qdrant ID)
    filename: str
    uploaded_at: datetime
    
class UserSummaryFile(Base):
    id: int
    user_id: int (FK → User)
    filename: str
    created_at: datetime
    
class Setting(Base):
    key: str (primary)
    value: str
    default_value: str
    category: str
    is_sensitive: bool
    description: str
```

## Deployment Patterns

### Windows (No Admin)

```python
# run_windows.py
from waitress import serve
serve(app, host="127.0.0.1", port=5000, threads=4)
```

- Localhost only (no firewall prompt)
- Auto-downloads qdrant.exe if missing
- Runs Qdrant on localhost:6333

### Linux/Docker

```python
# run_linux.py
os.system("gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'")
```

- Network accessible
- Qdrant as Docker container
- Entrypoint runs Alembic migrations

## File Locations

| Type | Location |
|------|----------|
| Database | `./app.db` (SQLite via SQLAlchemy) |
| Legacy DB | `./chat_history.db` (old, for migration only) |
| Session files | `./flask_session/` |
| Uploads | `./files/` |
| Data (CSV/XLSX) | `./data/` |
| Summaries (MD) | `./summaries/` |
| Qdrant (local) | `./local_qdrant.db/` |

## German Language Requirements

- System prompts must be in German
- Tool descriptions should be in German
- User-facing error messages must be in German
- Variable names can be in German for domain-specific terms
- Admin panel is in German

## Multi-User Permission Model

| Action | Admin | User |
|--------|-------|------|
| See all documents | ✅ | ❌ |
| See own documents | ✅ | ✅ |
| Delete all documents | ✅ | ❌ |
| Delete own documents | ✅ | ✅ |
| Edit all summaries | ✅ | ❌ |
| Edit own summaries | ✅ | ✅ |
| Manage users | ✅ | ❌ |
| Change settings | ✅ | ❌ |
| Access admin panel | ✅ | ❌ |
| Use chat | ✅ | ✅ |

## Key Files for Agents

When making changes, check these files:

1. **Models changed?** → Update `app/models.py` + create Alembic migration
2. **Database access?** → Update `app/database_service.py`
3. **Settings changed?** → Update `app/settings_service.py`
4. **Admin features?** → Update `app/admin_routes.py` + templates
5. **User features?** → Update `app/user_routes.py` + templates
6. **Qdrant changes?** → Check `src/utils/qdrant_client.py`
7. **File operations?** → Use `app/utils/file_manager.py`

## Troubleshooting Common Issues

### "database is locked" (SQLite)

- Multiple simultaneous writes
- **Solution:** Use WAL mode or migrate to PostgreSQL

### Alembic Migration Failed

```bash
# Check current version
alembic current

# Manual SQL fix
sqlite3 app.db "DELETE FROM alembic_version;"
alembic stamp head
```

### Qdrant Connection

```python
# Test connection
from src.utils.qdrant_client import test_connection
client = get_qdrant_client()
success, msg = test_connection(client)
```

### Settings Not Loading

- Check DB: `SELECT * FROM settings;`
- Check ENV: SettingsService falls back to os.getenv
- Re-seed: `alembic downgrade 001 && alembic upgrade head`
