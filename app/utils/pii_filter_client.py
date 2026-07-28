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

"""
PII-Filter Client für externen PII-Maskierungs-Service
"""

from logging import getLogger
from typing import List, Optional
import requests

logger = getLogger(__name__)


class PIIFilterResult:
    """Ergebnis eines PII-Filter-Aufrufs"""

    def __init__(
        self,
        original: str,
        filtered: str,
        mapping: Optional[List[dict]] = None,
        error: Optional[str] = None,
    ):
        self.original = original
        self.filtered = filtered
        self.mapping = (
            mapping or []
        )  # [{"placeholder": "[NAME_1]", "original": "Max Mustermann", "type": "person"}, ...]
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
            api_key: Optionaler API Key
            timeout: Request timeout in Sekunden
        """
        self.full_url = full_url
        self.api_key = api_key
        self.timeout = timeout

    def demask(self, text: str, mapping: list) -> str:
        """
        Ersetzt Platzhalter im Text mit den originalen Werten aus dem Mapping.

        Args:
            text: Der gefilterte Text mit Platzhaltern (z.B. "[NAME_1]")
            mapping: Liste von Mapping-Objekten mit "placeholder" und "original"

        Returns:
            Demaskierter Text mit originalen PII-Werten
        """
        if not mapping or not text:
            return text

        result = text
        for entry in mapping:
            placeholder = entry.get("placeholder")
            original = entry.get("original")

            if placeholder and original:
                result = result.replace(placeholder, original)

        return result

    def filter_text(self, text: str) -> PIIFilterResult:
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
            json_body = {"text": text}

            # API Key nur hinzufügen wenn vorhanden
            if self.api_key:
                json_body["api_key"] = self.api_key

            response = requests.post(
                url,
                json=json_body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
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

            # Flexibles Parsing: Unterstützt verschiedene Response-Formate
            # Erwartetes Format: {"original": "...", "filtered": "...", "mapping": [...]}
            # Mapping: [{"placeholder": "[NAME_1]", "original": "Max Mustermann", "type": "person"}, ...]
            filtered_text = (
                data.get("filtered")
                or data.get("sanitized_text")
                or data.get("result")
                or data.get("text")
                or text
            )

            original_text = data.get("original") or data.get("input") or text

            # Mapping für Demaskierung (bevorzugt) oder entities (legacy)
            mapping = (
                data.get("mapping")
                or data.get("entities")
                or data.get("detected")
                or data.get("pii_detected")
                or []
            )

            return PIIFilterResult(
                original=original_text, filtered=filtered_text, mapping=mapping
            )

        except requests.exceptions.Timeout:
            logger.warning(f"PII-Filter timeout after {self.timeout}s")
            return PIIFilterResult(
                original=text, filtered=text, error=f"Timeout ({self.timeout}s)"
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"PII-Filter request failed: {e}")
            return PIIFilterResult(original=text, filtered=text, error=str(e))

        except Exception as e:
            logger.error(f"PII-Filter unexpected error: {e}")
            return PIIFilterResult(original=text, filtered=text, error=str(e))
