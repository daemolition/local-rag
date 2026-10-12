# Local Document RAG

Ein Open-Source-RAG für eigene Dokumente, gebaut auf **Qualität** und volle Kontrolle über Einlesen und Suche. Die Oberfläche ist ein Chat im Stil von ChatGPT bzw. Langdock: Fragen stellen, Antworten mit Quellen bekommen, Dateien direkt anhängen. Alles läuft lokal, Modelle und Daten bleiben bei dir.

> **Lizenz:** GNU Affero General Public License v3 oder später (AGPL-3.0-or-later), siehe [`LICENSE`](./LICENSE).

## Was es kann

- **Chat mit Quellen** (SSE-Streaming, Spracheingabe per Parakeet). Dateien lassen sich anhängen und sind nur in diesem Chat durchsuchbar.
- **Knowledge-Bereiche**: pro Bereich eine eigene Qdrant-Collection mit Upload, Dokumentliste, Vektoransicht und eigenem Retrieval-Profil.
- **Markdown-first-Einlesen**: PDF, DOCX, DOC, ODT und MD werden mit Docling zu Markdown (Überschriften, Tabellen, Bildbeschreibungen per Vision-LLM), gespeichert und an den Überschriften zerlegt. Das gespeicherte Markdown ist in der Oberfläche einsehbar und die Grundlage zum Neu-Indexieren.
- **Tabellen als CSV**: Tabellen aus Dokumenten und CSV/Excel-Dateien werden nicht in den Vektorindex gepresst, sondern vom Modell per Pandas ausgewertet (richtige Summen statt geratener Zahlen).
- **Hybride Suche**: Bedeutung (Dense, HNSW) plus Stichwort (BM25 mit IDF), Neusortierung mit einem Cross-Encoder und Nachbar-Chunks für vollständige Absätze. Das Standardprofil ist die empfohlene Strategie, Alternativen gibt es unter „Erweitert“.
- **Einstellbare Modelle**: Embedding und Reranking wählst du unter *Administration › Einlesen & Modelle*, entweder als HuggingFace-Modell (lokal, z. B. `BAAI/bge-m3`) oder über einen OpenAI-kompatiblen Endpoint. Das System lädt das Modell selbst, die Vektor-Dimension ergibt sich aus dem Modell.
- **Neu indexieren ohne Ausfall**: Nach einem Modellwechsel baut ein Hintergrundjob den Index aus dem Markdown neu auf und schaltet erst um, wenn er fertig ist.
- **Mehrbenutzer**: Rollen (`admin`, `editor`, `user`), Gruppen und Freigaben für Knowledge und Modelle. Chats sind pro Nutzer privat.
- **Beliebige LLMs**: OpenAI-kompatible Verbindungen (LiteLLM, vLLM, Ollama, OpenAI) mit Modellliste, eigenem Prompt, Parametern und angehängtem Knowledge pro Modell.
- Optional: Websuche über SearXNG, die du pro Modell zuschaltest (Standard aus, nur mit eingerichtetem PII-Filter/entityguard).

Details zu Änderungen: [`CHANGELOG.md`](./CHANGELOG.md). Architektur und Konventionen für Entwickler: [`AGENTS.md`](./AGENTS.md).

## Schnellstart

### Docker (empfohlen)

```bash
docker-compose up --build
```

Öffnet die App auf http://localhost:8083. Qdrant, SearXNG, entityguard und Parakeet starten als eigene Container (Parakeet braucht eine NVIDIA-GPU, siehe `parakeet/Dockerfile` für CPU).

### Datenbank (Postgres)

Die App speichert Benutzer, Chats, Einstellungen und Modelle in **Postgres**. `docker compose up` startet den Container `postgres` samt Volume `pgdata` und migriert beim Start automatisch. Zugangsdaten stehen in `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, siehe `env.example`); für den Betrieb ein eigenes Passwort setzen. Ohne `DATABASE_URL` nutzt die App eine lokale SQLite-Datei, das ist nur für Entwicklung und Tests gedacht.

**Bestehende SQLite-Daten übernehmen** (`data/app.db` einer älteren Version):

```bash
docker compose up -d postgres
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag alembic upgrade head   # Postgres-Port dafür kurz freigeben
python scripts/migrate_sqlite_to_postgres.py --sqlite data/app.db --database-url postgresql+psycopg://rag:rag@localhost:5432/rag
```

Das Skript arbeitet an einer Kopie der SQLite-Datei (die Originaldatei bleibt unverändert), bringt sie auf den aktuellen Stand, leert die Zieltabellen, kopiert alles, setzt die ID-Zähler und vergleicht die Zeilenzahlen. Mit `--dry-run` zählt es nur. In Docker ist der Postgres-Port nicht nach außen offen; für den Import ergänzt du vorübergehend `ports: ["127.0.0.1:5432:5432"]` beim Dienst `postgres`. Backup: `docker compose exec postgres pg_dump -U rag rag > backup.sql`.

### Ohne Docker

Voraussetzungen: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+, ein laufender Qdrant-Server und für PDF-OCR Tesseract (`tesseract-ocr-deu`) und Poppler.

```bash
uv sync
(cd frontend && npm install && npm run build)   # React-Oberfläche nach app/static/
cp env.example .env                             # Qdrant-Host, OCR-Pfade
alembic upgrade head                            # Datenbank anlegen bzw. aktualisieren
python run_linux.py                             # http://localhost:5000
```

**macOS (Apple Silicon):** Nur die App läuft nativ, alles andere bleibt in Docker, denn Docker auf dem Mac hat keinen Zugriff auf die GPU. `python run_mac.py` startet per `docker-compose.mac.yml` Qdrant, SearXNG, entityguard und Parakeet (CPU) auf localhost, migriert die Datenbank und startet die App auf http://127.0.0.1:5000. Embedding, Reranking und Docling rechnen dann über Metal (MPS), ONNX-Modelle über CoreML; mit `RAG_DEVICE=cpu` lässt sich das abschalten. Voraussetzungen: Docker Desktop, `uv sync`, Frontend-Build und `brew install tesseract tesseract-lang poppler`. Mit `--no-docker` startet nur die App. Der Mac-Pfad ist bisher nicht auf echter Hardware getestet.

Unter Windows genügt ein Doppelklick auf `start.bat` (bzw. `python run_windows.py`). Das lädt bei Bedarf `qdrant.exe` herunter und startet es lokal, ohne Administratorrechte. Mit `--no-qdrant` wird ein vorhandener Qdrant genutzt.

### Erster Start

Beim ersten Start gibt es den Benutzer **`admin`** mit Passwort **`admin`** (bei frischer Datenbank über `ADMIN_PASSWORD` in `.env` änderbar). Bitte sofort das Passwort ändern (Kontomenü unten links).

Danach in dieser Reihenfolge:

1. **Administration › Verbindungen**: LLM-Endpunkt eintragen (Base-URL und Key).
2. **Administration › Modelle**: Standardmodell wählen.
3. **Administration › Einlesen & Modelle**: Embedding- und Reranking-Modell prüfen (der Standard funktioniert ohne Eingriff, beim ersten Start werden die Modelle heruntergeladen).
4. **Knowledge**: Dokumente hochladen und einlesen, dann im Chat fragen.

## Modelle und Hardware

- **Gerät:** Die App wählt automatisch CUDA (NVIDIA), MPS (Apple Silicon) oder CPU; `RAG_DEVICE` erzwingt eines davon. Die Wahl steht auf der Seite *Einlesen & Modelle*.
- **GPU (Docker):** Das Docker-Image bringt PyTorch mit CUDA mit; `docker-compose.yml` reserviert die GPU für die App (NVIDIA-Treiber und Container Toolkit nötig). Docling, Embedding und Reranker nutzen sie automatisch. Ohne GPU: den `deploy`-Block beim Dienst `rag` entfernen und mit `docker compose build --build-arg TORCH_BACKEND=cpu` bauen. Die lokale Entwicklung (`uv sync`) installiert bewusst das CPU-Wheel; wer lokal die GPU will, installiert CUDA-torch in die venv (`uv pip install --reinstall-package torch --reinstall-package torchvision torch torchvision`).

- Das Standard-Embedding ist `paraphrase-multilingual-MiniLM-L12-v2`, der Standard-Reranker `BAAI/bge-reranker-base` (ca. 1 GB). Beides läuft auf der CPU.
- Für höhere Qualität: `BAAI/bge-m3` (Embedding, ca. 2,2 GB) und `BAAI/bge-reranker-v2-m3`. Auf der CPU ist das Einlesen damit deutlich langsamer; mit GPU (siehe oben) läuft es direkt in der App (gemessen auf einer RTX 3060: ca. 4,5 GB GPU-Speicher für beide Modelle). Alternativ betreibst du die Modelle an einem Endpoint (vLLM, TEI, Infinity) und trägst ihn als Verbindung ein.
- Ein anderes Embedding-Modell erfordert **Neu indexieren** (Knopf im Knowledge bzw. „Alle neu indexieren“ in der Admin-Seite). Bis dahin wird jedes Knowledge weiter mit seinem alten Modell durchsucht.
- Ein anderes Reranking-Modell wirkt sofort.

## Einlesen im Überblick

```
Datei ─► Docling ─► Markdown (gespeichert) ─► nach Überschriften zerlegen
      ─► [Kontext je Chunk per LLM] ─► Embedding (Dense + BM25) ─► Qdrant
```

- Das Markdown liegt unter `data/markdown/<knowledge_id>/`; das Original bleibt standardmäßig archiviert (abschaltbar).
- Chunk-Größe, Überlappung, Kontextanreicherung und das Inhaltsverzeichnis (`index.md` pro Knowledge) stellst du unter *Einlesen & Modelle* ein.
- Das Einlesen läuft Datei für Datei im Hintergrund, der Fortschritt steht in der Oberfläche.

## Entwicklung

```bash
uv run --with pytest pytest tests -q        # Tests
uv run ruff check app tests                 # Lint
cd frontend && npm run dev                  # Vite mit HMR auf :5173, Proxy auf Flask :5000
cd frontend && npm run build                # Produktions-Build nach app/static/
```

- Backend: Flask, SQLAlchemy + Alembic (Postgres), Qdrant, LangChain. Die JSON-API liegt unter `/api/*`, der Chat unter `POST /chat` (SSE).
- Frontend: React 19, TypeScript, Vite, Tailwind v4, shadcn/ui.
- Migrationen: `alembic revision --autogenerate -m "..."`, `alembic upgrade head`. Eine bestehende Datenbank ohne Migrationsstand markierst du mit `alembic stamp head`.
- Releases: `scripts/release.py` (Version, Changelog, Tag). Beiträge siehe [`CONTRIBUTING.md`](./CONTRIBUTING.md), Sicherheitsmeldungen siehe [`SECURITY.md`](./SECURITY.md).

## Betrieb

- **Qdrant**: Server-Modus, `QDRANT_HOST`/`QDRANT_PORT` (Standard `localhost:6333`). Zum Umziehen auf einen anderen Server gibt es `scripts/manage_qdrant.py`.
- **Websuche**: `searxng/settings.yml` muss das Format `json` zulassen und `server.limiter: false` setzen. Den mitgelieferten `secret_key` für den Betrieb ersetzen (`openssl rand -hex 32`). SearXNG-URL und PII-Filter stellst du unter *Administration › Tools* ein; die Websuche selbst schaltest du je Modell unter *Modelle › Konfigurieren › Werkzeuge* zu. Sie lässt sich nur aktivieren, wenn der PII-Filter eingerichtet ist.
- **PII-Filter**: `PII_FILTER_URL` leer oder `PII_FILTER_ENABLED=false` schaltet ihn ab; dann ist auch die Websuche nicht verfügbar. Das Modell für Bildbeschreibungen wählst du unter *Einlesen & Modelle*.
- **Sprache**: Der Mic-Button streamt PCM per WebSocket (`/ws/stt-stream`) an Parakeet; `STT_BASEURL` ist in Docker vorbelegt.

### Fehlersuche

| Problem | Ursache und Lösung |
|---|---|
| Datenbank nicht erreichbar | `docker compose ps`: läuft `postgres` und ist er `healthy`? `DATABASE_URL` bzw. `POSTGRES_*` in `.env` prüfen. |
| Einstellungen weg nach Neustart | Das Postgres-Volume `pgdata` darf nicht gelöscht werden (`docker compose down -v` löscht es). |
| Qdrant nicht erreichbar | `docker-compose ps` bzw. `QDRANT_HOST`/`QDRANT_PORT` prüfen. |
| Alembic scheitert an vorhandenen Tabellen | `alembic stamp head`, wenn die Datenbank schon aktuell ist. |
| Modell lädt nicht | Status und Fehlertext stehen unter *Einlesen & Modelle*; ohne Internet können HuggingFace-Modelle nicht geladen werden. |
| Reranking fehlt in der Suche | Der Reranker lädt beim Start im Hintergrund; schlägt das fehl, läuft die Suche ohne Neusortierung weiter. |

## Autor

Christopher Abanilla
