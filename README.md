# Local Document RAG

Ein lokales RAG-System (Retrieval-Augmented Generation) mit Flask-Webinterface, SSE-Streaming, Pandas-Datenanalyse und Multi-User-Verwaltung.

## Features

- **Flask Webinterface** mit Login-Authentifizierung und Session-Management
- **Multi-User Support** mit Admin-Panel und Berechtigungen
- **SSE Streaming** für Echtzeit-Antworten
- **Hybride Vektorsuche** (Dense + Sparse/BM25) mit Qdrant
- **Multi-Format Dokumenten-Ingestion** (PDF, CSV, Excel, DOCX)
- **Pandas Analytics Tools** für Datenanalyse
- **Lokales LLM** via Ollama/OpenAI-kompatibler API
- **Admin Panel** für Settings, User Management und Summaries
- **Alembic Datenbank-Migrationen** für SQLAlchemy

---

## Schnellstart

### Windows (Keine Admin-Rechte nötig!)

```batch
# Einfach doppelklicken:
start.bat

# Oder manuell:
python run_windows.py
```

→ Öffnet http://127.0.0.1:5000 (nur lokal, keine Firewall-Abfrage!)

### Linux / Docker

```bash
# Mit Docker Compose
docker-compose up --build

# Oder manuell:
alembic upgrade head
python run_linux.py
```

→ Öffnet http://localhost:5000

### Default Login

| Benutzer | Passwort | Rolle |
|---------|----------|-------|
| admin | secret123 | Admin (alle Berechtigungen) |

---

## Installation

### Voraussetzungen

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) Package Manager
- [Ollama](https://ollama.ai/) oder kompatibler LLM-Server

### Setup

1. **Repository klonen:**
   ```bash
   git clone <repository-url>
   cd local-document-rag
   ```

2. **Dependencies installieren:**
   ```bash
   uv sync
   ```

3. **Datenbank initialisieren:**
   ```bash
   alembic upgrade head
   ```
   → Erstellt `app.db` mit allen Tabellen + Admin-User

4. **Umgebungsvariablen (`.env`):**
   ```bash
   # LLM
   CHAT_MODEL=qwen3:8b
   CHAT_BASEURL=http://localhost:11434/v1
   CHAT_TEMPERATURE=0.1
   CHAT_TOP_P=0.2
   
   VISION_MODEL=qwen3-vl:8b
   VISION_BASEURL=http://localhost:11434/v1
   
   # Legacy Fallback
   MODEL=qwen3-vl:8b
   BASEURL=http://localhost:11434/v1
   TEMPERATURE=0.1
   TOP_P=0.2
   API_KEY=loc-123
   
   # Embedding
   EMBEDDING_SOURCE=local
   EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
   EMBEDDING_DIMENSION=384
   
   # Qdrant
   QDRANT_LOCAL=true
   # QDRANT_HOST=localhost
   # QDRANT_PORT=6333
   
   # Storage
   DATA_DIR=./data
   SUMMARIES_DIR=./summaries
   ```

---

## Projektstruktur

```
local-document-rag/
├── app/                          # Flask Application
│   ├── __init__.py               # App Factory & SQLAlchemy Init
│   ├── routes.py                 # Main Routes (Chat, SSE)
│   ├── admin_routes.py           # Admin Panel (Settings, Users)
│   ├── user_routes.py            # User Routes (Documents, Summaries)
│   ├── database_service.py       # SQLAlchemy CRUD Operations
│   ├── settings_service.py       # Settings Management
│   ├── models.py                 # SQLAlchemy Models
│   └── templates/
│       ├── index.html            # Chat-Interface
│       ├── login.html            # Login-Seite
│       ├── admin/                # Admin Templates
│       │   ├── index.html
│       │   ├── documents.html
│       │   ├── settings.html
│       │   ├── users.html
│       │   ├── summaries.html
│       │   └── edit_summary.html
│       └── user/                 # User Templates
│           ├── documents.html
│           ├── summaries.html
│           └── edit_summary.html
│
├── src/
│   ├── llm/
│   │   └── local_llm.py          # VisionLLM Wrapper
│   ├── vector/
│   │   ├── retriever.py          # Document Retriever
│   │   └── ingestion.py          # Document Ingestion Pipeline
│   ├── agent/
│   │   └── document_agent.py     # LangChain Agent mit Tools
│   ├── tools/
│   │   └── custom_tools.py       # Pandas & Document Tools
│   └── utils/
│       ├── qdrant_client.py      # Qdrant Client Factory
│       ├── file_manager.py        # File Management Utilities
│       └── phase_logger.py       # Phase Logging
│
├── alembic/                      # Alembic Migrationen
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
│
├── scripts/
│   ├── manage_qdrant.py          # Qdrant Migration (local ↔ remote)
│   └── migrate_sessions.py       # Legacy Sessions Migration
│
├── files/                        # Upload-Ordner für Dokumente
├── data/                         # Excel/CSV-Dateien für Analyse
├── summaries/                    # Markdown Summary-Dateien
├── app.db                        # SQLite Hauptdatenbank (SQLAlchemy)
├── chat_history.db               # Legacy DB (optional für Migration)
│
├── run_windows.py                # Windows Entry Point
├── run_linux.py                  # Linux Entry Point
├── start.bat                     # Windows Starter
├── Dockerfile                    # Docker Image
├── docker-compose.yml            # Docker Compose
├── entrypoint.sh                 # Docker Entrypoint
├── ingest_documents.py           # Dokumente in Vektordatenbank laden
└── pyproject.toml                # Dependencies
```

---

## Multi-Platform Deployment

### Windows (Ohne Admin-Rechte)

```batch
# Einfach starten
start.bat

# Oder mit vorhandener Qdrant-Installation
python run_windows.py --no-qdrant
```

**Features:**
- Auto-Download von `qdrant.exe` (wenn nicht vorhanden)
- Flask auf `127.0.0.1:5000` (nur lokal, keine Firewall-Abfrage!)
- Qdrant auf `127.0.0.1:6333` (nur lokal)
- Waitress WSGI Server

### Linux / Docker

```bash
# Mit Docker (empfohlen)
docker-compose up --build

# Oder manuell
alembic upgrade head
python run_linux.py
```

**Features:**
- Gunicorn WSGI Server (4 Worker)
- Qdrant als Docker Container
- Netzwerk-weit erreichbar (`0.0.0.0:5000`)

---

## Datenbank-Migrationen (Alembic)

### Erste Installation

```bash
# Erstellt app.db mit allen Tabellen
alembic upgrade head
```

### Migrationen verwalten

```bash
# Neue Migration erstellen (nach Model-Änderungen)
alembic revision --autogenerate -m "description"

# Migration anwenden
alembic upgrade head

# Migration zurücksetzen
alembic downgrade -1

# Status prüfen
alembic current
```

### Legacy-Daten migrieren

```bash
# Alte chat_history.db → Neue app.db
python scripts/migrate_sessions.py
```

---

## Admin Panel

### Zugriff

- URL: http://localhost:5000/admin/
- Login: admin / secret123

### Features

| Bereich | Funktion |
|---------|----------|
| **Dashboard** | Qdrant-Statistiken, Collection-Info |
| **Dokumente** | Alle Qdrant-Dokumente anzeigen/löschen |
| **Upload** | Dateien für Ingestion hochladen |
| **Settings** | Alle .env-Variablen im UI bearbeiten |
| **Users** | User anlegen/löschen/Passwort zurücksetzen |
| **Summaries** | Alle Markdown-Dateien bearbeiten/löschen |

---

## User Features

### Meine Dokumente

- Eigene Dokumente hochladen
- Eigene Dokumente löschen
- Bei Löschung: Automatische Löschung der zugehörigen Datei im DATA_DIR

### Meine Summaries

- Eigene Markdown-Dateien bearbeiten (Inline-Editor mit Preview)
- Eigene Markdown-Dateien löschen
- Erstellt automatisch beim Speichern von Analysen

---

## Qdrant Verwaltung

### Qdrant Migration (Local ↔ Remote)

```bash
# Status prüfen
python scripts/manage_qdrant.py status

# Lokal → Remote (Dry-Run)
python scripts/manage_qdrant.py migrate --from local --to-remote --dry-run

# Lokal → Remote (Ausführen)
python scripts/manage_qdrant.py migrate --from local --to-remote

# Remote → Lokal
python scripts/manage_qdrant.py migrate --from-remote --to local
```

---

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/` | GET | Chat-Interface |
| `/login` | GET/POST | Login |
| `/logout` | GET | Logout |
| `/chat` | POST (SSE) | Streaming Chat |
| `/api/sessions` | GET/POST | Session Management |
| `/admin/*` | - | Admin Panel |
| `/user/*` | - | User Routes |

---

## Entwicklung

### Code Style

```bash
# Linting
uv run ruff check .
uv run ruff check --fix .

# Formatting
uv run ruff format .
```

### Neue Dependencies

```bash
uv add <package>
```

---

## Troubleshooting

### "database is locked" (SQLite)

- Mehrere gleichzeitige Schreibzugriffe
- **Lösung:** WAL Mode aktivieren oder auf PostgreSQL migrieren

### Qdrant Verbindungsfehler

```bash
# Prüfen ob Qdrant läuft
curl http://localhost:6333/health

# Windows: qdrant.exe starten
# Linux: docker-compose ps
```

### Alembic Migration fehlgeschlagen

```bash
# Von vorne beginnen (Achtung: Daten gehen verloren!)
rm app.db
alembic upgrade head
```

### Session-Probleme

```bash
# Session-Verzeichnis löschen
rm -rf flask_session/
```

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask App                                │
├─────────────────────────────────────────────────────────────────┤
│  SQLAlchemy DB (Users, Sessions, Messages, Documents, ...) │
│  Auth: Session-based (admin/user roles)                         │
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
┌──────────────────────────────────────────────────────────────────┐
│                      DocumentAgent                                │
│  (LangChain ReAct Agent mit deutschem System Prompt)            │
├──────────────────────────────────────────────────────────────────┤
│  Tools:                                                           │
│  1. document_search_tool → Qdrant Vector Search                  │
│  2. list_files           → Verfügbare Dateien auflisten           │
│  3. preview_data          → Spalten/Vorschau anzeigen            │
│  4. run_pandas            → Pandas-Code ausführen                │
└─────────────────────────────────────┬────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                         LLM                                      │
│  (Ollama / OpenAI-kompatibele API)                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## License

MIT

---

## Autor

Christopher Abanilla
