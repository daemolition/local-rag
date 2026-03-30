# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local Document RAG - A German-language RAG (Retrieval-Augmented Generation) system with Flask web interface, SSE streaming, and Pandas analytics capabilities. Uses local LLMs via Ollama/OpenAI-compatible API.

## Common Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run Flask development server
uv run python run.py

# Ingest documents into vector database
uv run python ingest_documents.py

# Linting and formatting
uv run ruff check .
uv run ruff format .
```

## Architecture

```
Flask App (run.py)
    └── DocumentAgent (LangChain ReAct Agent)
            ├── Tools (src/tools/custom_tools.py)
            │   ├── document_search_tool → Qdrant vector search
            │   ├── list_files / preview_data / run_pandas → Pandas analytics
            │   └── list_summaries / read/write/edit_summary → Summary management
            └── VisionLLM (src/llm/local_llm.py)
                    ├── chat_model → Agent interactions
                    └── vision_model → Image processing in PDFs
```

### Key Files

| File | Purpose |
|------|---------|
| `app/__init__.py` | App factory, Qdrant/embedding/agent initialization |
| `app/routes.py` | Flask routes: login, chat SSE, session management API |
| `src/agent/document_agent.py` | LangChain ReAct agent with system prompt |
| `src/tools/custom_tools.py` | 8 tools: document search, pandas analytics, summaries |
| `src/llm/local_llm.py` | VisionLLM wrapper (separate chat/vision models) |
| `src/vector/ingestion.py` | Document ingestion with context enrichment |
| `src/vector/retriever.py` | MMR retriever with configurable thresholds |
| `src/components/custom_pdf_loader.py` | PDF loader with OCR and image analysis |

### Data Flow

1. **Document Ingestion** (`ingest_documents.py`):
   - Load PDF/CSV/XLSX/DOCX from `./files/`
   - Split into chunks, enrich with LLM-generated context
   - Generate dense + sparse (BM25) embeddings
   - Store in Qdrant with metadata

2. **Chat Request** (`/chat` SSE endpoint):
   - Load chat history from SQLite
   - Stream agent events to frontend
   - Save user query and assistant response to database

3. **Agent Tool Workflow**:
   - Document questions → `document_search_tool`
   - Data analysis → `list_files` → `preview_data` → `run_pandas`
   - Insights → `write_summary` / `edit_summary`

## Environment Configuration

Key variables in `.env`:

| Variable | Purpose |
|----------|---------|
| `CHAT_MODEL` / `CHAT_BASEURL` | LLM for agent interactions |
| `VISION_MODEL` / `VISION_BASEURL` | LLM for image processing |
| `EMBEDDING_SOURCE` | `local` (HuggingFace) or `endpoint` |
| `EMBEDDING_MODEL` | Embedding model name |
| `EMBEDDING_DIMENSION` | Vector dimension (must match model) |
| `DATA_DIR` | Directory for Excel/CSV analytics files |
| `SUMMARIES_DIR` | Directory for stored summaries |
| `QDRANT_LOCAL` | `true` for local `.db`, `false` for remote server |

## Tool Security

`run_pandas` has security guardrails blocking: `os.`, `sys.`, `subprocess`, file operations, `eval`, `exec`.

## LLM Integration

- Uses OpenAI-compatible API (Ollama, vLLM, etc.)
- Separate models for chat (fast) and vision (multimodal)
- System prompt is German, instructs agent to respond in German
- Recursion limit: 500 for complex multi-tool queries