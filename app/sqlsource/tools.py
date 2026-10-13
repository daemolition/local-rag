# Open Knowledge UI - A privacy-focused, self-hosted RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""Werkzeuge fuer SQL-Quellen. Die Quellen kommen aus dem Scope des Requests (wie bei der Dokumentsuche)."""

from logging import getLogger

from langchain_core.tools.structured import StructuredTool
from pydantic import BaseModel, Field

from app.pii_session import get_session
from app.retrieval import get_scope_or_none
from app.sqlsource import format as fmt
from app.sqlsource.config import parse_config
from app.toolworker import config as worker_config
from app.toolworker.client import ToolWorkerUnavailable, get_client
from app.utils.phase_logger import Phase, phase_logger
from app.utils.pii_filter_client import PIIFilterUnavailable

logger = getLogger(__name__)

SCHEMA_DESCRIPTION = """
Zeigt Tabellen, Spalten, Schlüssel und Beziehungen der verbundenen SQL-Datenbank.
Rufe das zuerst auf, wenn du die Struktur nicht kennst. `source` ist nur nötig, wenn mehrere Datenbanken verbunden sind.
"""

QUERY_DESCRIPTION = """
Führt EINE lesende SQL-Abfrage (SELECT) auf der verbundenen Datenbank aus und gibt die Ergebnisse als Tabelle zurück.
Nur SELECT ist erlaubt, nur freigegebene Tabellen und Spalten, das Ergebnis ist auf wenige Zeilen begrenzt:
aggregiere mit COUNT/SUM/AVG und GROUP BY, statt viele Zeilen zu laden. Verwende die Schreibweise der Spalten aus
`sql_schema`. `source` ist nur nötig, wenn mehrere Datenbanken verbunden sind.
"""


class SchemaInput(BaseModel):
    source: str = Field(default="", description="Name der Datenbank (nur bei mehreren nötig)")


class QueryInput(BaseModel):
    query: str = Field(description="Eine einzelne SELECT-Abfrage")
    source: str = Field(default="", description="Name der Datenbank (nur bei mehreren nötig)")


class _Fail(Exception):
    pass


def _resolve(source: str):
    scope = get_scope_or_none()
    entries = scope.sql_sources if scope else ()
    if not entries:
        raise _Fail("Keine SQL-Datenbank ausgewählt.")
    wanted = (source or "").strip().lower()
    if not wanted:
        if len(entries) == 1:
            return entries[0]
        raise _Fail("Mehrere SQL-Datenbanken sind verbunden, gib die Quelle an: " + ", ".join(f"„{e[1]}“" for e in entries))
    for entry in entries:
        if entry[1].lower() == wanted:
            return entry
    raise _Fail(f"Unbekannte Quelle „{source}“. Verfügbar: " + ", ".join(f"„{e[1]}“" for e in entries))


def _unmask(text: str) -> str:
    session = get_session()
    return session.unmask(text) if session else text


def _mask(text: str) -> str:
    session = get_session()
    if session is None:
        return text
    try:
        return session.mask_tool_text(text)
    except PIIFilterUnavailable:
        return "FEHLER: Der PII-Filter ist nicht erreichbar, die Ergebnisse wurden nicht an das Modell übergeben."


def _call(action: str, cfg, extra: dict):
    limits = worker_config.load_sql()
    payload = {
        "connection": cfg.connection(),
        "allowed_tables": sorted(cfg.allowed_tables()) if cfg.allowed_tables() else None,
        "blocked_columns": {t: sorted(c) for t, c in cfg.blocked().items()},
        "limits": {"row_limit": limits.row_limit, "timeout_s": limits.timeout_s, "max_cell_chars": limits.max_cell_chars},
        **extra,
    }
    try:
        return get_client("sql").sql(action, payload, limits.timeout_s + 15), limits
    except ToolWorkerUnavailable as e:
        raise _Fail(f"SQL-Dienst nicht verfügbar. {e}") from None


class SqlTools:
    def get_tools(self) -> list:
        def sql_schema(source: str = "") -> str:
            phase_logger.log_phase(Phase.TOOL_EXECUTION, "Tool: sql_schema")
            try:
                _id, name, raw = _resolve(_unmask(source))
                out, _ = _call("schema", parse_config(raw), {})
            except _Fail as e:
                return f"FEHLER: {e}"
            if not out.get("ok"):
                return f"FEHLER: {out.get('error') or 'Schema nicht lesbar'}"
            return fmt.schema_text(name, out.get("tables") or [])

        def sql_query(query: str, source: str = "") -> str:
            phase_logger.log_phase(Phase.TOOL_EXECUTION, f"Tool: sql_query | {query[:60]}")
            try:
                _id, name, raw = _resolve(_unmask(source))
                out, limits = _call("query", parse_config(raw), {"sql": _unmask(query)})
            except _Fail as e:
                return f"FEHLER: {e}"
            if not out.get("ok"):
                return _mask(f"FEHLER: {out.get('error') or 'Abfrage fehlgeschlagen'}")
            return _mask(fmt.result_text(name, out["columns"], out["rows"], bool(out.get("truncated")), limits.row_limit))

        return [
            StructuredTool.from_function(func=sql_schema, name="sql_schema", description=SCHEMA_DESCRIPTION, args_schema=SchemaInput),
            StructuredTool.from_function(func=sql_query, name="sql_query", description=QUERY_DESCRIPTION, args_schema=QueryInput),
        ]
