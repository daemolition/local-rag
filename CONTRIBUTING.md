# Contributing to Local Document RAG

Vielen Dank für dein Interesse, zu diesem Projekt beizutragen!

## Entwicklungsumgebung einrichten

```bash
git clone https://github.com/daemolition/local-document-rag.git
cd local-document-rag
uv sync
cp env.example .env
alembic upgrade head
python run_linux.py   # oder run_windows.py
```

## Code Style

- **Linting/Formatting:** [Ruff](https://docs.astral.sh/ruff/) (keine eigene Konfiguration, Defaults)
  ```bash
  uv run ruff check .
  uv run ruff format .
  ```
- **Imports:** stdlib → third party → local, getrennt durch Leerzeilen.
- **Sprache:** UI, Tool-Beschreibungen, System-Prompt und user-facing Errors sind auf Deutsch.
- **Kommentare:** Englisch oder Deutsch, aber sparsam — nur wo nötig.

## Commits & Pull Requests

1. Erstelle einen Branch: `feat/...`, `fix/...`, `docs/...`
2. Schreibe klare Commit-Messages (im Präsens, imperativ).
3. Beschreibe im PR **was** geändert wurde und **warum**.
4. Bei Schema-Änderungen: erstelle eine Alembic-Migration:
   ```bash
   alembic revision --autogenerate -m "description"
   ```
5. Führe `uv run ruff check .` aus, bevor du den PR öffnest.

## Sicherheitsrelevante Änderungen

- Die `run_pandas`-Tool-Guardrails dürfen **nicht** gelockert werden (blockt `os.`, `sys.`, `subprocess`, `__import__`, `open(`, `eval(`, `exec(`, write-Methoden). Nur mit expliziter Zustimmung.
- Keine Secrets, API-Keys oder privaten IPs in Code committen.
- Default-Passwörter nur als Fallback, nie hartkodiert für Production.

## Lizenz

Durch das Einreichen eines Beitrags stimmst du zu, dass dieser unter der [AGPL-3.0-or-later](./LICENSE) Lizenz steht.