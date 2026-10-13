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
PII-Filter ueber das ganze Gespraech (Chat).

* ``mask_conversation``: Zusammenfassung, Verlauf und neue Frage gehen als **ein** Text mit
  Trennmarken in **einem** Aufruf an den Sanitizer. Dadurch vergibt der Dienst im ganzen Kontext
  eindeutige Platzhalter (``[NAME_1]``, ``[NAME_2]`` ...) und liefert ein gemeinsames Mapping.
  Kommen die Marken nicht unversehrt zurueck, wird abgebrochen (fail-closed).
* ``StreamDemasker``: setzt Platzhalter in der gestreamten Antwort schon waehrend des Streamens
  zurueck, auch wenn sie ueber Token-Grenzen gesplittet ankommen.
"""

import re
import threading
from contextvars import ContextVar

from app.utils.pii_filter_client import (
    PIIFilterClient,
    PIIFilterUnavailable,
    mapping_pairs,
    mask_or_fail,
)

# Bewusst ohne Buchstaben: spaCy-NER hat "=====MSG-1=====" teilweise als Entitaet erkannt (gemessen)
MARKER = "=====#{}====="
_MARKER_RE = re.compile(r"=====#(\d+)=====")
BASE_TIMEOUT_S = 5.0
CHARS_PER_EXTRA_SECOND = 2000
MAX_TIMEOUT_S = 60.0


def timeout_for(chars: int) -> float:
    """Zeitlimit waechst mit der Textlaenge: 5 s + 1 s je 2000 Zeichen, hoechstens 60 s."""
    return min(MAX_TIMEOUT_S, BASE_TIMEOUT_S + chars / CHARS_PER_EXTRA_SECOND)


def join_texts(texts: list[str]) -> str:
    return "".join(f"\n\n{MARKER.format(i)}\n\n{text}" for i, text in enumerate(texts)).lstrip("\n")


def split_texts(joined: str, count: int) -> list[str]:
    """Teilt den maskierten Text an den Marken; wirft, wenn sie nicht genau einmal und in Reihenfolge da sind."""
    found = [int(m.group(1)) for m in _MARKER_RE.finditer(joined)]
    if found != list(range(count)):
        raise PIIFilterUnavailable("der Filter hat die Trennmarken des Verlaufs verändert")
    parts = _MARKER_RE.split(joined)  # ['', '0', '\n\ntext0\n\n', '1', '\n\ntext1', ...]
    texts = []
    for i in range(count):
        part = parts[2 + 2 * i]
        part = part[2:] if part.startswith("\n\n") else part.lstrip("\n")
        if i < count - 1 and part.endswith("\n\n"):
            part = part[:-2]
        texts.append(part)
    return texts


def mask_conversation(client: PIIFilterClient, texts: list[str]) -> tuple[list[str], object]:
    """Maskiert alle ``texts`` in einem Aufruf.

    Returns:
        ``(maskierte Texte in gleicher Reihenfolge, Mapping Platzhalter -> Original)``.
    Raises:
        PIIFilterUnavailable: Dienst nicht erreichbar, Fehlerantwort oder zerstoerte Marken.
    """
    if not texts:
        return [], {}
    joined = join_texts(texts)
    try:
        # reuse_placeholders: optionaler Hinweis, gleicher Wert = gleicher Platzhalter (EntityGuard >= 1.2);
        # Dienste, die das Feld nicht kennen, ignorieren es.
        result = client.filter_text(
            joined, timeout=timeout_for(len(joined)), extra={"reuse_placeholders": True}
        )
    except Exception as e:  # filter_text faengt selbst; Sicherheitsnetz
        raise PIIFilterUnavailable(type(e).__name__) from None
    if result.error:
        raise PIIFilterUnavailable(result.error)
    return split_texts(result.filtered, len(texts)), result.mapping


def short_reason(error: str) -> str:
    """Kurzer, fuer Nutzer geeigneter Grund (ohne interne Adressen oder Ausnahmetexte)."""
    text = str(error)
    if text.startswith("HTTP "):
        return text.split(":")[0][:12]
    if "Timeout" in text or "timed out" in text:
        return "Zeitüberschreitung"
    if "Trennmarken" in text:
        return "Trennmarken des Verlaufs verändert"
    return "nicht erreichbar"


def demask_text(client: PIIFilterClient, text: str, mapping) -> str:
    return client.demask(text, mapping) if mapping else text


def merge_masked(known: dict, text: str, new_pairs: list[tuple[str, str]]) -> str:
    """Ordnet die Platzhalter eines spaeteren Filteraufrufs in die bekannten ein (siehe Plan Task 6)."""
    reverse = {original: placeholder for placeholder, original in known.items()}
    taken = {placeholder for placeholder, _ in new_pairs}
    rename: dict[str, str] = {}
    for placeholder, original in sorted(new_pairs, key=lambda p: len(p[0]), reverse=True):
        if original in reverse:
            target = reverse[original]
        elif known.get(placeholder, original) == original:
            target = placeholder
        else:
            n = 2
            while True:
                candidate = (
                    f"{placeholder[:-1]}_{n}{placeholder[-1]}"
                    if placeholder[-1:] in "]>)}"
                    else f"{placeholder}_{n}"
                )
                if candidate not in known and candidate not in taken:
                    break
                n += 1
            target = candidate
            taken.add(target)
        if target != placeholder:
            rename[placeholder] = target
        known[target] = original
        reverse[original] = target
    if rename:
        pattern = re.compile("|".join(re.escape(k) for k in sorted(rename, key=len, reverse=True)))
        text = pattern.sub(lambda m: rename[m.group(0)], text)
    return text


class PIISession:
    """Alle Platzhalter eines Chat-Requests: Kontext, Antwort und Werkzeug-Ergebnisse teilen ein Mapping."""

    def __init__(self, client, mapping=None):
        self.client = client
        self._known: dict[str, str] = {}
        self._lock = threading.Lock()
        for placeholder, original in mapping_pairs(mapping):
            self._known[placeholder] = original

    def pairs(self) -> list[tuple[str, str]]:
        with self._lock:
            return sorted(self._known.items(), key=lambda p: len(p[0]), reverse=True)

    def mapping(self) -> dict:
        with self._lock:
            return dict(self._known)

    def unmask(self, text: str) -> str:
        for placeholder, original in self.pairs():
            text = text.replace(placeholder, original)
        return text

    def mask_tool_text(self, text: str) -> str:
        """Maskiert Werkzeug-Text (nur mit eingerichtetem Filter). Fehler -> ``PIIFilterUnavailable``."""
        if self.client is None or not text:
            return text
        masked, mapping = mask_or_fail(self.client, text)
        pairs = mapping_pairs(mapping)
        if not pairs:
            return masked
        with self._lock:
            return merge_masked(self._known, masked, pairs)


_session: ContextVar["PIISession | None"] = ContextVar("pii_session", default=None)


def set_session(session: "PIISession | None"):
    return _session.set(session)


def get_session() -> "PIISession | None":
    return _session.get()


class StreamDemasker:
    """Setzt Platzhalter in einem Stream zurueck und haelt moegliche Platzhalter-Anfaenge zurueck."""

    def __init__(self, mapping):
        self._session = mapping if isinstance(mapping, PIISession) else None
        self._static = (
            sorted(mapping_pairs(mapping), key=lambda p: len(p[0]), reverse=True) if self._session is None else []
        )
        self._buffer = ""

    @property
    def _pairs(self):
        return self._session.pairs() if self._session is not None else self._static

    def _hold(self, text: str) -> int:
        """Laenge des Endes von ``text``, das der Anfang eines Platzhalters sein koennte."""
        longest = 0
        for placeholder, _original in self._pairs:
            for k in range(min(len(placeholder) - 1, len(text)), longest, -1):
                if text.endswith(placeholder[:k]):
                    longest = k
                    break
        return longest

    def _replace(self, text: str) -> str:
        for placeholder, original in self._pairs:
            text = text.replace(placeholder, original)
        return text

    def feed(self, chunk: str) -> str:
        if not self._pairs:
            return chunk
        self._buffer += chunk
        text = self._replace(self._buffer)
        hold = self._hold(text)
        self._buffer = text[len(text) - hold :] if hold else ""
        return text[: len(text) - hold] if hold else text

    def flush(self) -> str:
        rest, self._buffer = self._buffer, ""
        return self._replace(rest) if self._pairs else rest
