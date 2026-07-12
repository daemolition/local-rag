# Local Document RAG

Ein lokales RAG-System (Retrieval-Augmented Generation) mit Flask-Webinterface, SSE-Streaming, Pandas-Datenanalyse und hybrider Vektorsuche. Singleuser: ein einzelnes App-Passwort schützt den Zugriff, keine Accounts oder Rollen.

> **Lizenz:** Dieses Projekt ist unter der **GNU Affero General Public License v3 oder später (AGPL-3.0-or-later)** veröffentlicht. Siehe [`LICENSE`](./LICENSE).

## Features

- **Flask Webinterface** mit einfachem Passwortschutz und Session-Management
- **SSE Streaming** für Echtzeit-Antworten
- **Hybride Vektorsuche** (Dense + Sparse/BM25) mit Qdrant
- **Multi-Format Dokumenten-Ingestion** (PDF, CSV, Excel, DOCX)
- **Pandas Analytics Tools** für Datenanalyse
- **Lokales LLM** via Ollama/OpenAI-kompatibler API
- **Verwaltungsbereich** für Vektordatenbank-Einsicht und Settings
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

### Default-Passwort

Beim ersten Start wird ein einzelnes App-Passwort gesetzt: **`admin`** (überschreibbar über `ADMIN_PASSWORD` in `.env` bei frischer DB). Es gibt keine Benutzernamen/Accounts mehr — nur das eine Passwort schützt die App.

> **Wichtig:** Ändere das Passwort nach dem ersten Login über **Einstellungen → Passwort ändern**.

---

## Qdrant

Dieses Projekt benötigt einen **laufenden Qdrant-Server** (Server-Modus). Die App verbindet sich zu `QDRANT_HOST:QDRANT_PORT` (Default: `localhost:6333`).

### Windows

`run_windows.py` startet automatisch einen lokalen Qdrant-Server (`qdrant.exe` auf `127.0.0.1:6333`) — ohne Administratorrechte und ohne Firewall-Abfrage:

- `qdrant.exe` wird automatisch heruntergeladen, falls nicht vorhanden.
- Qdrant läuft auf `127.0.0.1:6333` (nur localhost erreichbar).
- Der Flask-Server läuft auf `127.0.0.1:5000` (ebenfalls nur localhost).
- Beim Beenden wird der Qdrant-Prozess aufgeräumt.

Wenn du Qdrant bereits separat betreibst (z. B. per Docker oder manuell):

```batch
python run_windows.py --no-qdrant
```

### Linux / Docker

Docker Compose startet Qdrant als separaten Container (`qdrant/qdrant:latest`). Die App verbindet sich über das `local-rag-network` zum `qdrant`-Service.

Manuell: Starte Qdrant separat (Docker, Binary, etc.) und konfiguriere `QDRANT_HOST`/`QDRANT_PORT` in `.env`.

---

## Installation

### Voraussetzungen

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) Package Manager
- [Ollama](https://ollama.ai/) oder kompatibler LLM-Server
- Ein laufender Qdrant-Server (siehe oben)
- Für PDF-OCR:
  - **Windows:** Tesseract-OCR + Poppler (Pfade können über `.env` gesetzt werden)
  - **Linux:** `tesseract-ocr`, `tesseract-ocr-deu`, `poppler-utils`

### Setup

1. **Repository klonen:**
   ```bash
   git clone https://github.com/daemolition/local-document-rag.git
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
   → Erstellt `data/app.db` mit allen Tabellen + Default-Passwort (`admin`).

4. **Umgebungsvariablen (`.env`):**
   ```bash
   cp env.example .env
   # .env anpassen (Qdrant-Host, OCR-Pfade)
   ```

   Siehe [`env.example`](./env.example) für alle verfügbaren Variablen. App-Konfiguration (LLM, Embedding, API-Keys etc.) wird über das Einstellungen-Panel in der UI gepflegt, nicht über `.env`.

---

## Projektstruktur

```
local-document-rag/
├── app/                          # Flask Application & RAG Pipeline
│   ├── __init__.py               # App Factory & SQLAlchemy Init
│   ├── routes.py                 # Main Routes (Chat, SSE, Login, STT)
│   ├── user_routes.py            # Dokumente, Analysen, Vektordatenbank, Settings, Dashboard
│   ├── database_service.py       # SQLAlchemy CRUD Operations
│   ├── settings_service.py       # Settings Management (inkl. App-Passwort)
│   ├── models.py                 # SQLAlchemy Models
│   ├── templates/                # Flask Templates
│   ├── llm/local_llm.py          # VisionLLM Wrapper
│   ├── vector/                   # Document Ingestion & Retrieval
│   ├── agent/document_agent.py   # LangChain Agent mit Tools
│   ├── tools/custom_tools.py     # Pandas & Document Tools
│   ├── utils/                    # Qdrant Client, File Manager, Phase Logger
│   └── components/               # PDF Loader & Preprocessing
│
├── alembic/                      # Alembic Migrationen
├── scripts/                      # Qdrant Server-Migration
├── data/                         # App-Daten (app.db, files/, processed_files/, summaries/)
│
├── run_windows.py                # Windows Entry Point
├── run_linux.py                  # Linux Entry Point
├── start.bat                     # Windows Starter
├── Dockerfile                    # Docker Image
├── docker-compose.yml            # Docker Compose
├── entrypoint.sh                 # Docker Entrypoint
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
- Qdrant auf `127.0.0.1:6333` (nur lokal, im Benutzerkontext)
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
- Gunicorn WSGI Server (1 Worker + mehrere Threads via `gthread`) — ein Worker-Prozess, damit In-Memory-State (Qdrant-Client etc.) konsistent bleibt, mehrere Threads, damit ein langer SSE-Chat-Stream nicht jede andere Anfrage blockiert
- Qdrant als Docker Container
- Netzwerk-weit erreichbar (`0.0.0.0:5000`)

---

## Dokumente einlesen (Ingestion)

Dokumente werden **über das Web-Interface** eingelesen. Es ist kein separates CLI-Skript mehr nötig.

1. Einloggen.
2. Unter **Dokumente** PDF-, DOCX-, XLSX-, XLS- oder CSV-Dateien hochladen.
3. **Ingestion starten** klicken.
4. Einzelne Dokumente oder ganze Dateigruppen lassen sich sowohl unter **Dokumente** (einfache Karten-Ansicht) als auch unter **Vektordatenbank** im Verwaltungsbereich (technische Chunk-Ansicht mit Filter/Pagination/Batch-Löschen) löschen.

### Was passiert im Hintergrund?

Die Ingestion nutzt `app.vector.DocumentIngestion`:

- PDFs werden mit OCR und einem Vision-LLM für Bilder/Diagramme verarbeitet.
- DOCX-Dateien werden strukturiert eingelesen.
- CSV/XLSX-Dateien erzeugen eine tabellarische Übersicht plus eine LLM-generierte Inhaltsbeschreibung.
- Alle Inhalte werden gechunkt, mit Kontext angereichert und als dichte + sparse (BM25) Vektoren in die Qdrant-Collection `"local_rag"` geschrieben.
- Verarbeitete PDFs/DOCXs landen in `./processed_files/`, CSV/XLSX-Dateien in `./data/`.

---

## Datenbank-Migrationen (Alembic)

### Erste Installation

```bash
# Erstellt data/app.db mit allen Tabellen + Default-Passwort
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

### Bestehende app.db

Wenn `app.db` bereits existiert (z. B. durch `DatabaseService` erstellt, nicht durch Alembic), schlägt `alembic upgrade head` mit "table already exists" fehl. Lösung:

```bash
# Markiere DB als migriert, ohne DDL auszuführen
alembic stamp head
```

---

## Verwaltungsbereich

### Zugriff

- URL: http://localhost:5000/admin/
- Login: einzelnes App-Passwort (Default `admin`, siehe [Default-Passwort](#default-passwort))

### Features

| Bereich | Funktion |
|---------|----------|
| **Dashboard** | Qdrant-Statistiken, Collection-Info |
| **Vektordatenbank** | Alle Qdrant-Dokumente (Chunk-Ebene) anzeigen/löschen, Filter & Pagination |
| **Settings** | Alle Konfiguration im UI bearbeiten (LLM, Embedding, Retriever, API-Keys, Storage), inkl. **Passwort ändern** |

---

## Dokumente & Analysen

### Dokumente

- Dateien hochladen (Datei-Karten-Ansicht, eine Karte pro Datei)
- Dokumente löschen
- Bei Löschung: Automatische Löschung der zugehörigen Datei

### Analysen (Summaries)

- Markdown-Dateien bearbeiten (Inline-Editor mit Live-Preview inkl. Tabellen)
- Markdown-Dateien löschen
- Werden automatisch beim Speichern von Analysen im Chat erstellt

---

## Qdrant Verwaltung

### Qdrant Server-Migration

Migration zwischen zwei Qdrant-Server-Instanzen (z. B. beim Wechsel des Hosts):

```bash
# Status einer Qdrant-Instanz prüfen
uv run python scripts/manage_qdrant.py status --host localhost --port 6333

# Migration Server A → Server B (Dry-Run)
uv run python scripts/manage_qdrant.py migrate \
    --source-host localhost --source-port 6333 \
    --target-host 192.168.1.100 --target-port 6333 --dry-run

# Migration durchführen
uv run python scripts/manage_qdrant.py migrate \
    --source-host localhost --source-port 6333 \
    --target-host 192.168.1.100 --target-port 6333

# Collection-Info anzeigen
uv run python scripts/manage_qdrant.py info --host localhost --port 6333
```

---

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/` | GET | Chat-Interface |
| `/login` | GET/POST | Login (einzelnes App-Passwort) |
| `/logout` | GET | Logout |
| `/chat` | POST (SSE) | Streaming Chat |
| `/api/sessions` | GET/POST | Session Management |
| `/admin/*` | - | Verwaltung (Vektordatenbank, Settings) |
| `/user/*` | - | Dokumente & Analysen |
| `/health` | GET | Health Check |

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask App                                │
├─────────────────────────────────────────────────────────────────┤
│  SQLAlchemy DB (Sessions, Messages, Documents, Settings, ...)   │
│  Auth: Session-based (einzelnes App-Passwort, keine Accounts)    │
└────────────────────────────────────┬────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌──────────┐    ┌──────────┐     ┌──────────┐
              │Verwaltung│    │Dokumente/│     │  Chat    │
              │(Vektor-DB│    │ Analysen │     │  (SSE)   │
              │/Settings)│    │          │     │          │
              └──────────┘    └──────────┘     └────┬─────┘
                                                       │
                                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DocumentAgent                                │
│  (LangChain ReAct Agent mit deutschem System Prompt)             │
├──────────────────────────────────────────────────────────────────┤
│  Tools:                                                           │
│  1. document_search_tool → Qdrant Vector Search                   │
│  2. list_files           → Verfügbare Dateien auflisten           │
│  3. preview_data          → Spalten/Vorschau anzeigen             │
│  4. run_pandas            → Pandas-Code ausführen                 │
└─────────────────────────────────────┬────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                         LLM                                       │
│  (Ollama / OpenAI-kompatible API)                                 │
└──────────────────────────────────────────────────────────────────┘
```

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

# Windows: qdrant.exe starten oder python run_windows.py
# Linux: docker-compose ps
```

### Alembic Migration fehlgeschlagen

```bash
# Bestehende DB als migriert markieren (ohne DDL auszuführen)
alembic stamp head

# Oder von vorne beginnen (Achtung: Daten gehen verloren!)
rm data/app.db
alembic upgrade head
```

### Session-Probleme

Sessions werden als signierte Cookies clientseitig gespeichert. Bei merkwürdigem Verhalten `SECRET_KEY` in den Einstellungen zurücksetzen (neuer Schlüssel wird beim nächsten Start generiert).

---

## Lizenz

Dieses Projekt steht unter der [GNU Affero General Public License v3 oder später](https://www.gnu.org/licenses/agpl-3.0.html).

Jede Interaktion mit der Anwendung über ein Netzwerk erfordert laut AGPLv3, dass den Nutzern der Quellcode der laufenden Version zur Verfügung gestellt wird. Betreibst du eine öffentlich erreichbare Instanz, stelle sicher, dass ein Link zum Quellcode angeboten wird — z. B. in der App-UI oder im Footer.

---

## Autor

Christopher Abanilla — [GitHub](https://github.com/daemolition)