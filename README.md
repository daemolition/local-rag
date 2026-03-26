# Local Document RAG

Ein lokales RAG-System (Retrieval-Augmented Generation) mit Flask-Webinterface, SSE-Streaming und Pandas-Datenanalyse-Fähigkeiten.

## Features

- **Flask Webinterface** mit Login-Authentifizierung
- **SSE Streaming** für Echtzeit-Antworten
- **Hybride Vektorsuche** (Dense + Sparse/BM25) mit Qdrant
- **Multi-Format Dokumenten-Ingestion** (PDF, CSV, Excel, DOCX)
- **Pandas Analytics Tools** für Datenanalyse
- **Lokales LLM** via Ollama/OpenAI-kompatibler API

---

## Projektstruktur

```
local-document-rag/
├── app/                          # Flask Application
│   ├── __init__.py               # App Factory & Ressourcen-Initialisierung
│   ├── routes.py                 # Routes (Login, Chat, SSE-Endpoint)
│   └── templates/
│       ├── index.html            # Chat-Interface
│       └── login.html            # Login-Seite
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
│   └── components/
│       └── custom_pdf_loader.py  # PDF-Loader mit OCR/OCR
│
├── files/                        # Eingabe-Ordner für Dokumente
├── analytics/                    # Excel/CSV-Dateien für Pandas-Analyse
├── local_qdrant.db/              # Qdrant Vektordatenbank
├── flask_session/                # Serverseitige Sessions
│
├── run.py                        # Flask Entry Point
├── ingest_documents.py           # Dokumente in Vektordatenbank laden
├── .env                          # Umgebungsvariablen
└── pyproject.toml                # Dependencies
```

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask App                                │
├─────────────────────────────────────────────────────────────────┤
│  Login (hardcoded) → Session → Chat Endpoint (SSE)              │
└────────────────────────────────────┬────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DocumentAgent                               │
│  (LangChain ReAct Agent mit System Prompt)                      │
├─────────────────────────────────────────────────────────────────┤
│  Tools:                                                          │
│  1. document_search_tool → Qdrant Vector Search                  │
│  2. list_files           → Verfügbare Excel/CSV auflisten       │
│  3. preview_data          → Spalten/Vorschau anzeigen           │
│  4. run_pandas            → Pandas-Code ausführen               │
└────────────────────────────────────┬────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                         LLM                                      │
│  (Ollama / OpenAI-kompatible API)                               │
└─────────────────────────────────────────────────────────────────┘
```

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

3. **Umgebungsvariablen konfigurieren (`.env`):**
   ```bash
   # LLM
   MODEL=gemma3:4b
   BASEURL=http://192.168.1.35:11434/v1
   TEMPERATURE=0.1
   TOP_P=0.2
   API_KEY=loc-123

   # Embedding
   EMBEDDING_SOURCE=local
   EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
   EMBEDDING_DIMENSION=384

   # Data Directory für Pandas Analytics
   DATA_DIR=./analytics
   ```

4. **Dokumente ingestieren:**
   ```bash
   # PDF, CSV, Excel, DOCX in ./files/ legen
   uv run python ingest_documents.py
   ```

---

## Starten

### Entwicklung

```bash
uv run python run.py
```

Die App läuft unter: http://localhost:5000

### Default Login

| Benutzer | Passwort |
|---------|----------|
| admin | secret123 |
| user | password123 |

---

## Verwendung

### 1. Dokumenten-Suche

Stelle eine Frage und der Agent durchsucht die Vektordatenbank:

```
"Wie hoch war der Umsatz im Q1 2024?"
```

### 2. Pandas Datenanalyse

Lege Excel/CSV-Dateien in `./analytics/` ab. Der Agent kann:

1. **Dateien auflisten:** `list_files`
2. **Vorschau anzeigen:** `preview_data`
3. **Analysen durchführen:** `run_pandas`

Beispiel-Prompts:
- "Welche Excel-Dateien sind verfügbar?"
- "Zeige mir die ersten 5 Zeilen der Datei sales.xlsx"
- "Berechne die Summe der Spalte 'Umsatz' in sales.xlsx"

### 3. Workflow-Beispiel

```
User: "Was ist in der Datei sales.xlsx enthalten?"

Agent Workflow:
  1. list_files() → ["sales.xlsx"]
  2. preview_data("sales.xlsx", rows=5) → Spalten & Daten
  3. Antwort: "Die Datei enthält Spalten: Datum, Produkt, Umsatz, Menge..."
```

---

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/` | GET | Chat-Interface (Login required) |
| `/login` | GET/POST | Login-Seite |
| `/logout` | GET | Session beenden |
| `/chat` | POST (SSE) | Streaming Chat mit Agent |
| `/history` | GET | Chat-History (JSON) |

---

## Tools Details

### document_search_tool

Sucht in der Vektordatenbank nach relevanten Text-Ausschnitten.

- **Input:** Suchanfrage (String)
- **Output:** Liste von Chunks mit Metadaten

### list_files

Listet verfügbare Excel/CSV-Dateien im `DATA_DIR`.

- **Input:** Keines
- **Output:** Liste von Dateinamen

### preview_data

Zeigt Spaltennamen und erste N Zeilen einer Datei.

- **Input:** `filename`, `rows` (optional, default 5)
- **Output:** Formatierter String mit Spalten & Daten

### run_pandas

Führt Pandas-Code auf einem DataFrame aus.

- **Input:** `filename`, `code`
- **Output:** Analyseergebnis

**Beispiel-Code:**
```python
result = df['Umsatz'].sum()
result = df.groupby('Kategorie')['Wert'].mean()
result = df[df['Jahr'] == 2024]['Umsatz'].sum()
```

**Sicherheit:** Befehle wie `os.`, `sys.`, `subprocess`, `to_csv`, etc. sind blockiert.

---

## Development

### Dependencies hinzufügen

```bash
uv add <package>
```

### Ruff Linting

```bash
uv run ruff check .
uv run ruff format .
```

---

## Troubleshooting

### "Collection not found"

Starte `ingest_documents.py` um die Vektordatenbank zu initialisieren.

### Embedding-Warning

```
embeddings.position_ids | UNEXPECTED
```

Kann ignoriert werden - das Modell funktioniert dennoch korrekt.

### Session-Probleme

Lösche den `flask_session/` Ordner und starte neu.

---

## License

MIT

---

## Autor

Christopher Abanilla