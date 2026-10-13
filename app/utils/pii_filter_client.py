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
PII-Filter Client für externen PII-Maskierungs-Service
"""

from logging import getLogger
from typing import Optional
import requests

logger = getLogger(__name__)


FILTERED_KEYS = ("filtered", "sanitized_text", "result", "text")
MAPPING_KEYS = ("mapping", "entities", "detected", "pii_detected")


def _first_present(data: dict, keys: tuple):
    """Wert des ersten vorhandenen Schluessels (auch leer: ein leerer Text ist eine gueltige Antwort)."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def parse_response(data, text: str) -> tuple[str, str, object]:
    """Liest die Antwort eines Sanitizer-Dienstes (siehe docs/sanitizer-api.md).

    Returns:
        ``(original, filtered, mapping)``. Ohne gefilterten Text in der Antwort gilt der Eingabetext
        (nichts maskiert), ohne Mapping ``{}``.
    """
    if not isinstance(data, dict):
        return text, text, {}
    filtered = _first_present(data, FILTERED_KEYS)
    original = data.get("original") or data.get("input") or text
    mapping = _first_present(data, MAPPING_KEYS)
    return original, text if filtered is None else str(filtered), mapping if mapping is not None else {}


def mapping_pairs(mapping) -> list[tuple[str, str]]:
    """``[(Platzhalter, Original), ...]`` aus dem Mapping (dict oder Liste von Objekten)."""
    if isinstance(mapping, dict):
        items = mapping.items()
    elif isinstance(mapping, list):
        items = [
            (e.get("placeholder"), e.get("original")) for e in mapping if isinstance(e, dict)
        ]
    else:
        return []
    return [(str(p), str(o)) for p, o in items if p and o]


class PIIFilterUnavailable(Exception):
    """Der eingerichtete PII-Filter hat nicht geantwortet oder einen Fehler gemeldet."""


class PIIFilterResult:
    """Ergebnis eines PII-Filter-Aufrufs"""

    def __init__(
        self,
        original: str,
        filtered: str,
        mapping=None,
        error: Optional[str] = None,
    ):
        self.original = original
        self.filtered = filtered
        self.mapping = (
            mapping if mapping is not None else {}
        )  # entityguard-Format: {"[NAME_1]": "Max Mustermann", ...}
        self.error = error

    def __repr__(self):
        if self.error:
            return f"<PIIFilterResult(error='{self.error}')>"
        return f"<PIIFilterResult(entities={len(self.mapping)})>"


class PIIFilterClient:
    """Client für externen PII-Filter-Service"""

    def __init__(self, full_url: str, api_key: str = None, timeout: float = 5.0):
        """
        Args:
            full_url: Vollständige URL zum Endpoint (z.B. http://localhost:9500/api/v1/sanitize)
            api_key: Optionaler API Key (wird als "Authorization: Bearer" gesendet)
            timeout: Request timeout in Sekunden
        """
        self.full_url = full_url
        self.api_key = api_key
        self.timeout = timeout

    def demask(self, text: str, mapping) -> str:
        """
        Ersetzt Platzhalter im Text mit den originalen Werten aus dem Mapping.

        Args:
            text: Der gefilterte Text mit Platzhaltern (z.B. "[NAME_1]")
            mapping: entweder {"placeholder": "original", ...} (entityguard-Format)
                oder eine Liste von Objekten mit "placeholder"/"original" (legacy)

        Returns:
            Demaskierter Text mit originalen PII-Werten
        """
        if not mapping or not text:
            return text

        result = text

        for placeholder, original in mapping_pairs(mapping):
            result = result.replace(placeholder, original)

        return result

    def filter_text(
        self, text: str, timeout: Optional[float] = None, extra: Optional[dict] = None
    ) -> PIIFilterResult:
        """
        Sendet Text an PII-Filter-Service und erhält maskierte Version zurück.

        Args:
            text: Der zu filternde Text

        Returns:
            PIIFilterResult mit original, filtered, entities oder error
        """
        if not text:
            return PIIFilterResult(original=text, filtered=text)

        # Verwende die vollständige URL direkt
        url = self.full_url

        try:
            # Request-Body vorbereiten
            json_body = {"text": text, **(extra or {})}

            headers = {"Content-Type": "application/json"}
            # API Key als Bearer-Token, nur wenn vorhanden
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.post(
                url,
                json=json_body,
                headers=headers,
                timeout=timeout or self.timeout,
            )

            if response.status_code != 200:
                logger.warning(
                    f"PII-Filter API returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )
                return PIIFilterResult(
                    original=text, filtered=text, error=f"HTTP {response.status_code}"
                )

            data = response.json()

            original_text, filtered_text, mapping = parse_response(data, text)

            return PIIFilterResult(
                original=original_text, filtered=filtered_text, mapping=mapping
            )

        except requests.exceptions.Timeout:
            logger.warning(f"PII-Filter timeout after {timeout or self.timeout}s")
            return PIIFilterResult(
                original=text, filtered=text, error=f"Timeout ({timeout or self.timeout:g}s)"
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"PII-Filter request failed: {e}")
            return PIIFilterResult(original=text, filtered=text, error=str(e))

        except Exception as e:
            logger.error(f"PII-Filter unexpected error: {e}")
            return PIIFilterResult(original=text, filtered=text, error=str(e))


def mask_or_fail(client: "PIIFilterClient", text: str) -> tuple[str, object]:
    """Maskiert ``text`` oder wirft ``PIIFilterUnavailable`` (fail-closed).

    Returns:
        ``(Text fuer das Modell, Mapping zum Zuruecksetzen der Antwort)``; ohne erkannte Werte der
        unveraenderte Text und ein leeres Mapping.
    """
    try:
        result = client.filter_text(text)
    except Exception as e:  # filter_text faengt selbst, das hier ist das Sicherheitsnetz
        raise PIIFilterUnavailable(type(e).__name__) from None
    if result.error:
        raise PIIFilterUnavailable(result.error)
    if result.filtered != result.original:
        return result.filtered, result.mapping
    return text, []

