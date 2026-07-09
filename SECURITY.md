# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | yes       |
| older   | no        |

## Reporting a Vulnerability

Wenn du eine Sicherheitslücke findest, **öffne kein öffentliches Issue**.

Bitte melde sie privat an: erstelle ein [GitHub Security Advisory](https://github.com/daemolition/local-document-rag/security/advisories/new) (Draft) oder kontaktiere den Maintainer direkt.

Du erhältst innerhalb von 72 Stunden eine Bestätigung. Nach der Bestätigung arbeiten wir an einem Fix und veröffentlichen ihn mit einem entsprechenden Advisory.

## Security Measures

- **`run_pandas` Guardrails:** Das Pandas-Tool blockt gefährliche Operationen (`os.`, `sys.`, `subprocess`, `__import__`, `open(`, `eval(`, `exec(`, write-Methoden wie `to_csv`/`to_sql`/`to_json`). Diese dürfen nicht gelockert werden.
- **Path Validation:** Dateioperationen validieren, dass Pfade unter `DATA_DIR`/`SUMMARIES_DIR` bleiben.
- **Session-based Auth:** Admin- und User-Rollen mit Flask-Session.
- **Default Passwords:** `admin`/`admin` — **müssen nach Installation geändert werden** (via `.env` `ADMIN_PASSWORD` oder Admin-Panel).

## Known Limitations

- SQLite ist nicht für hoch-concurrent Workloads ausgelegt (WAL-Mode empfohlen).
- Die App läuft standardmäßig auf `localhost` — für Network-Deployment eigene Sicherheitsmaßnahmen treffen (Reverse Proxy, TLS, etc.).