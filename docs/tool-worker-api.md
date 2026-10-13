# Tool-Worker

Der Tool-Worker führt Code getrennt von der App aus. In dieser Version: die Pandas-Auswertungen (`run_pandas`) auf CSV- und Excel-Dateien. Die App (Rechte, Chat, Schlüssel, Datenbank) und der Worker teilen nichts außer einem Token und einem lesenden Datenordner.

## Sicherheitsmodell

Zwei Schichten, die jede für sich halten sollen:

1. **Prüfung (AST)** vor dem Start: keine Importe, keine Namen oder Attribute mit `__`, keine Zeichenketten mit `__` (verhindert `"{0.__class__}".format(...)`), kein `open`, `eval`, `exec`, `compile`, `getattr`, `type` u. a., keine `read_*`-Funktionen und keine schreibenden `to_*`-Funktionen. Erlaubt sind `df`, `pd`, `np` und `result`.
2. **Kapselung:** ein eigener Kindprozess je Aufruf mit Speicher-, CPU- und Dateigrößenlimit, Wall-Clock-Zeitlimit (Kill der Prozessgruppe), Audit-Hook (kein Lesen außerhalb des Python-Verzeichnisbaums, kein Schreiben, keine Sockets, keine Unterprozesse) und gekürzter Ausgabe. Der Container läuft nicht als root, mit `read_only`, `cap_drop: ALL`, `no-new-privileges`, Speicher-/PID-Limits, einem Netz ohne Ausgang (`internal: true`) und den Daten nur lesend.

Der Worker kennt weder die App-Datenbank noch Qdrant, LLM-Schlüssel, Sitzungen oder den PII-Filter. Er bekommt je Aufruf einen Dateinamen relativ zu seinem Datenordner, den Code und Limits.

### Grenzen (ehrlich)

- Audit-Hooks und AST-Prüfung sind keine vollständige Sandbox. Die Isolation trägt der Container, nicht die Prüfung allein.
- `internal: true` in Compose verhindert den Weg nach außen für Container in diesem Netz, ist aber keine Firewall. Strenges Filtern des Ausgangs braucht die Firewall des Hosts.
- Die Dateien im Datenvolume müssen für den Benutzer 10001 lesbar sein.
- `preview_data` liest Dateien weiterhin in der App (es führt keinen Code aus).

## Betrieb

| Variable | Wo | Bedeutung |
|---|---|---|
| `TOOL_WORKER_TOKEN` (oder `_FILE`) | App und Worker | gemeinsames Geheimnis, Pflicht (ohne startet der Worker nicht; Compose bricht ab) |
| `TOOL_WORKER_DATA_DIR` | Worker | Datenordner im Container, Standard `/data` |
| `TOOL_WORKER_MAX_TIMEOUT_S`, `TOOL_WORKER_MAX_MEMORY_MB` | Worker | Obergrenzen, die die App nicht überschreiben kann |

In der Datenbank (Administration › Tools › Tool-Worker): `TOOL_WORKER_URL` (Standard `http://tool-worker:8090`), `PANDAS_TIMEOUT_S` (30), `PANDAS_MAX_MEMORY_MB` (1024), `PANDAS_MAX_OUTPUT_CHARS` (20000).

Ist der Worker nicht erreichbar, läuft der Chat weiter; `run_pandas` meldet „Codeausführung nicht verfügbar“. Es gibt keine Ausführung in der App als Rückfall.

## Schnittstelle (JSON über HTTP, nur im internen Netz)

Alle `/v1/*`-Aufrufe brauchen `Authorization: Bearer <TOOL_WORKER_TOKEN>`.

### `GET /health`

Ohne Anmeldung. `200 {"status": "ok", "version": "0.1.0"}`

### `POST /v1/pandas`

```bash
curl -s -H "Authorization: Bearer $TOOL_WORKER_TOKEN" -H "Content-Type: application/json" \
  -d '{"file":"knowledge_2/umsatz.csv","code":"result = df[\"betrag\"].sum()",
       "limits":{"timeout_s":30,"memory_mb":1024,"max_output_chars":20000}}' \
  http://tool-worker:8090/v1/pandas
```

| Status | Bedeutung |
|---|---|
| 200 `{"ok": true, "output": "..."}` | Ausgeführt; `output` enthält Konsole und `result` |
| 200 `{"ok": false, "error": "FEHLER: ..."}` | Code blockiert, Fehler im Code, Zeit- oder Speicherlimit |
| 400 | Ungültige Anfrage |
| 401 | Token fehlt oder falsch |
| 404 | Datei nicht verfügbar (außerhalb des Datenordners, falscher Typ, nicht vorhanden) |
| 413 | Code länger als 20 000 Zeichen |
| 500 | Interner Fehler (ohne Details in der Antwort) |

`file` ist relativ zum Datenordner (`umsatz.csv`, `knowledge_2/tabelle.csv`). Die App entscheidet, welche Dateien eine Anfrage nutzen darf; der Worker lehnt jeden Pfad außerhalb seines Mounts ab. Die Limits werden vom Worker auf seine eigenen Obergrenzen gekappt.

## Rolle `sql` (SQL-Knowledge)

Dasselbe Image läuft mit `TOOL_WORKER_ROLE=sql` als zweiter Dienst `tool-worker-sql`. Er bedient nur `/v1/sql/*` (die Pandas-Rolle nur `/v1/pandas`; die jeweils andere antwortet 404). Er hängt im Netz `sql-worker-net` (mit Ausgang zu den Datenbanken), der Pandas-Worker bleibt ohne Ausgang.

| Endpunkt | Zweck | Antwort |
|---|---|---|
| `POST /v1/sql/test` | Verbindung, Version, Tabellen, Schreibrecht-Warnung | `{"ok": true, "version", "tables": [{name, columns}], "write_privilege"}` |
| `POST /v1/sql/schema` | Schema (gefiltert nach Freigaben) | `{"ok": true, "tables": [...]}` |
| `POST /v1/sql/query` | eine SELECT-Abfrage | `{"ok": true, "columns", "rows", "truncated"}` |

Körper: `{"connection": {dialect, host, port, instance, database, user, password, schema}, "allowed_tables": [..]|null, "blocked_columns": {tabelle: [spalte]}, "sql": "...", "limits": {"row_limit", "timeout_s", "max_cell_chars"}}`. Prüfungs- und Datenbankfehler kommen als `200 {"ok": false, "error": "..."}`, ohne Adresse und Zugangsdaten.

Umgebung (Rolle sql): `TOOL_WORKER_ROLE=sql`, `TOOL_WORKER_SQLITE_DIR` (Standard `/sqlite`, lesend), `TOOL_WORKER_MAX_ROWS` (1000), `TOOL_WORKER_MAX_SQL_TIMEOUT_S` (60). Einstellungen der App (DB): `SQL_WORKER_URL`, `SQL_ROW_LIMIT`, `SQL_TIMEOUT_S`, `SQL_MAX_CELL_CHARS`, `SQL_PROMPT`. Siehe `docs/sql-knowledge.md`.
