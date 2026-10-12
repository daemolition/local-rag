# Local Document RAG - A privacy-focused, local RAG system
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

"""Aufbereitung der Treffer fuer das LLM (mit Quellenangabe)."""

from langchain_core.documents import Document

NO_RESULTS = "Keine passenden Textstellen gefunden."


def _pages(meta: dict) -> str:
    """\"Seite 3\" bzw. \"Seiten 3–4\" oder leer."""
    start, end = meta.get("page_start"), meta.get("page_end")
    if start is None:
        return ""
    return f"Seite {start}" if end in (None, start) else f"Seiten {start}–{end}"


def format_hits(docs: list[Document], numbers: list[int] | None = None) -> str:
    """Jeder Treffer mit Nummer und Dateiname, damit das LLM Quellen nennen kann.

    ``numbers``: Quellennummern des Requests (siehe ``record_sources``); sie bleiben ueber
    mehrere Suchen hinweg eindeutig, damit ``[2]`` im Antworttext genau eine Quelle meint.
    """
    if not docs:
        return NO_RESULTS
    blocks = []
    for k, doc in enumerate(docs):
        i = numbers[k] if numbers and k < len(numbers) else k + 1
        meta = doc.metadata or {}
        source = meta.get("filename") or "unbekannt"
        chunks = meta.get("chunks")
        if chunks and chunks[0] != chunks[1]:
            where = f" (Abschnitte {chunks[0] + 1}–{chunks[1] + 1})"
        elif meta.get("chunk_index") is not None:
            where = f" (Abschnitt {meta['chunk_index'] + 1})"
        else:
            where = ""
        pages = _pages(meta)
        if pages:
            where = f" ({pages}{', ' + where.strip(' ()') if where else ''})"
        blocks.append(f"[{i}] Quelle: {source}{where}\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(blocks)


def source_entry(doc: Document) -> dict:
    """Quellenangabe eines Treffers fuer die Anzeige im Chat (mit Score)."""
    meta = doc.metadata or {}
    chunks = meta.get("chunks")
    idx = meta.get("chunk_index")
    return {
        "filename": meta.get("filename") or "unbekannt",
        "score": meta.get("score"),
        "section": (
            f"{chunks[0] + 1}–{chunks[1] + 1}"
            if chunks and chunks[0] != chunks[1]
            else (idx + 1 if isinstance(idx, int) else None)
        ),
        "headers": meta.get("headers"),
        "page": _pages(meta) or None,
        "snippet": doc.page_content.strip()[:240],
    }


def record_sources(docs: list[Document]) -> list[int]:
    """Merkt die Treffer im Scope des Requests (Anzeige unter der Antwort) und liefert ihre
    Quellennummern; dieselbe Stelle behaelt bei erneuter Suche ihre Nummer."""
    from app.retrieval import get_scope_or_none

    scope = get_scope_or_none()
    if scope is None:
        return list(range(1, len(docs) + 1))
    numbers = []
    for doc in docs:
        entry = source_entry(doc)
        found = next(
            (e for e in scope.sources if (e["filename"], e["section"]) == (entry["filename"], entry["section"])),
            None,
        )
        if found is None:
            entry["n"] = len(scope.sources) + 1
            scope.sources.append(entry)
            found = entry
        numbers.append(found["n"])
    return numbers
