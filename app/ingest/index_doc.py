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

"""
Inhaltsverzeichnis (``index.md``) pro Knowledge.

Die Vektorsuche findet Textstellen, aber sie sagt nicht, *was es gibt*: Fragen wie
"welche Vertraege liegen vor?" oder "in welcher Tabelle steht der Umsatz?" brauchen einen
Ueberblick. Die Datei listet pro Dokument Titel, Gliederung und extrahierte Tabellen sowie
die strukturierten Dateien (CSV/Excel) mit ihren Spalten.

Sie wird nach jedem Einlesen, Loeschen und Umbenennen **aus dem Bestand neu erzeugt**
(nicht angehaengt) und kann deshalb nicht veralten. Kleine Verzeichnisse bekommt das Modell
direkt mit der Frage, grosse ueber das Werkzeug ``read_knowledge_index``.
"""

import csv
import re
from datetime import datetime
from logging import getLogger
from pathlib import Path

logger = getLogger(__name__)

INDEX_NAME = "index.md"
# Ab dieser Groesse (alle Knowledge zusammen) gibt es das Verzeichnis nur noch per Werkzeug.
INLINE_MAX_CHARS = 4000
# Obergrenze fuer das, was ans Modell geht.
TOOL_MAX_CHARS = 12000
MAX_HEADINGS = 12
_HEADING = re.compile(r"^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$")
_TABLE_FILE = re.compile(r"^(?P<stem>.+)--(?P<fg>[0-9a-f]{8})--tabelle-(?P<n>\d+)\.csv$")
STRUCTURED = {".csv", ".xlsx", ".xls"}


def index_path(paths) -> Path:
    return Path(paths.markdown_dir) / INDEX_NAME


def _outline(markdown: str) -> list[str]:
    """Ueberschriften bis Ebene 3 (ohne den Dokumenttitel an erster Stelle doppelt)."""
    titles: list[str] = []
    in_code = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m and m.group(2) not in titles:
            titles.append(m.group(2))
    return titles


def _csv_info(path: Path) -> tuple[list[str], int | None]:
    """(Spalten, Zeilenzahl) einer CSV ohne sie komplett zu laden; Excel: nur Spalten."""
    try:
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                return header, sum(1 for _ in reader)
        import pandas as pd

        return [str(c) for c in pd.read_excel(path, nrows=0).columns], None
    except Exception:
        return [], None


def _describe(path: Path, shown_name: str) -> str:
    columns, rows = _csv_info(path)
    parts = []
    if rows is not None:
        parts.append(f"{rows} Zeilen")
    if columns:
        parts.append("Spalten: " + ", ".join(columns[:20]) + (" …" if len(columns) > 20 else ""))
    return f"`{shown_name}`" + (f" ({'; '.join(parts)})" if parts else "")


def build_index(knowledge: dict, documents: list, paths) -> str:
    """Baut das Inhaltsverzeichnis. ``documents`` sind ``UserDocument``-Zeilen."""
    data_dir = Path(paths.data_dir)
    files = sorted(p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in STRUCTURED) if data_dir.is_dir() else []
    tables_by_doc: dict[str, list[Path]] = {}
    plain_files: list[Path] = []
    for f in files:
        m = _TABLE_FILE.match(f.name)
        if m:
            tables_by_doc.setdefault(m.group("fg"), []).append(f)
        else:
            plain_files.append(f)

    lines = [f"# Inhaltsverzeichnis: {knowledge['name']}", ""]
    if knowledge.get("description"):
        lines += [knowledge["description"], ""]
    n_tables = sum(len(v) for v in tables_by_doc.values())
    lines += [
        f"Stand: {datetime.now():%d.%m.%Y %H:%M} · {len(documents)} Dokumente · "
        f"{n_tables + len(plain_files)} Tabellen/Datendateien",
        "",
    ]

    lines += ["## Dokumente", ""]
    if not documents:
        lines += ["Noch keine Dokumente.", ""]
    for doc in sorted(documents, key=lambda d: d.filename.lower()):
        lines.append(f"### {doc.filename}")
        if doc.uploaded_at:
            lines.append(f"- Eingelesen am {doc.uploaded_at:%d.%m.%Y}")
        outline = []
        if doc.markdown_path and Path(doc.markdown_path).is_file():
            outline = _outline(Path(doc.markdown_path).read_text(encoding="utf-8"))
        if outline:
            shown = outline[:MAX_HEADINGS]
            lines.append("- Gliederung: " + " · ".join(shown) + (" · …" if len(outline) > MAX_HEADINGS else ""))
        short = re.sub(r"[^0-9a-f]", "", doc.document_id)[:8]
        for table in sorted(tables_by_doc.get(short, [])):
            lines.append("- Tabelle: " + _describe(table, f"{paths.name_prefix}{table.name}"))
        lines.append("")

    if plain_files:
        lines += ["## Strukturierte Dateien (Auswertung mit run_pandas)", ""]
        lines += [f"- {_describe(f, paths.name_prefix + f.name)}" for f in plain_files]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def refresh_index(knowledge_id: int | None) -> bool:
    """Erzeugt ``index.md`` des Knowledge neu (oder entfernt sie, wenn abgeschaltet).

    Fehler werden geloggt und nie weitergereicht: Das Verzeichnis darf das Einlesen nicht stoeren.
    """
    try:
        from app.database_service import get_db_service
        from app.knowledge import get_knowledge, knowledge_paths
        from app.settings_service import SettingsService

        knowledge = get_knowledge(knowledge_id)
        if not knowledge:
            return False
        paths = knowledge_paths(knowledge)
        session = get_db_service().get_session()
        try:
            enabled = SettingsService(session).get_bool("INGEST_INDEX_ENABLED", True)
        finally:
            session.close()
        target = index_path(paths)
        if not enabled:
            target.unlink(missing_ok=True)
            return False
        documents = get_db_service().get_all_documents(knowledge_id=knowledge["id"])
        text = build_index(knowledge, documents, paths)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Inhaltsverzeichnis konnte nicht erzeugt werden: {e}")
        return False


def _read_texts(indexes) -> list[str]:
    texts = []
    for _name, path in indexes:
        p = Path(path)
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                texts.append(text)
    return texts


def read_indexes(max_chars: int = TOOL_MAX_CHARS) -> str:
    """Die Verzeichnisse der Knowledge im aktuellen Scope (gekuerzt auf ``max_chars``)."""
    from app.retrieval import get_scope_or_none  # lazy: vermeidet einen Importzyklus

    scope = get_scope_or_none()
    texts = _read_texts(scope.indexes if scope else ())
    if not texts:
        return "Kein Inhaltsverzeichnis vorhanden."
    joined = "\n\n---\n\n".join(texts)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit("\n", 1)[0] + "\n\n… (gekürzt – für Details gezielt suchen)"
    return joined


def inline_hint(indexes, max_chars: int = INLINE_MAX_CHARS) -> str:
    """Hinweistext mit dem Verzeichnis, wenn es klein genug ist; sonst leer.

    Grosse Verzeichnisse gibt es nur per Werkzeug, sonst wuerde jede Antwort viele Tokens kosten.
    """
    joined = "\n\n".join(_read_texts(indexes))
    if not joined or len(joined) > max_chars:
        return ""
    return (
        "\n\n[Inhaltsverzeichnis des durchsuchbaren Wissens (zur Orientierung, nutze für "
        f"Details die Suche):\n{joined}]"
    )
