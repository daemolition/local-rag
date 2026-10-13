"""
title: Sanitizer Filter (ganzer Kontext)
version: 0.2

OpenWebUI-Filter fuer jeden Sanitizer nach docs/sanitizer-api.md (z. B. EntityGuard).

Unterschied zum einfachen Inlet-Filter: Er maskiert nicht nur die letzte Nachricht, sondern den
GANZEN Kontext (System-Prompt, Verlauf, neue Frage) in EINEM Aufruf. Dadurch
  * sieht das Modell auch frueher genannte Namen nie im Klartext (OpenWebUI schickt den Verlauf
    bei jeder Anfrage im Klartext erneut),
  * vergibt der Dienst im ganzen Kontext eindeutige Platzhalter ([NAME_1], [NAME_2] ...) und
    liefert EIN Mapping, mit dem outlet() die Antwort zurueckuebersetzt.
Fail-closed: Ist der Dienst nicht erreichbar oder zerstoert er die Trennmarken, wird die Anfrage
gestoppt statt unmaskiert weitergeleitet.
"""

import logging
import re
from typing import Optional

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MARKER = "=====#{}====="
_MARKER_RE = re.compile(r"=====#(\d+)=====")
TEXT_KEYS = ("sanitized_text", "filtered", "result", "text")  # EntityGuard liefert sanitized_text


def _slots(messages: list) -> list:
    """Alle Textstellen der Nachrichten als (Nachricht, Teil-Index oder None); Bilder u. a. bleiben."""
    slots = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            slots.append((message, None))
        elif isinstance(content, list):
            for i, part in enumerate(content):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    slots.append((message, i))
    return slots


def _get(slot) -> str:
    message, index = slot
    return message["content"] if index is None else message["content"][index]["text"]


def _set(slot, text: str) -> None:
    message, index = slot
    if index is None:
        message["content"] = text
    else:
        message["content"][index]["text"] = text


def _join(texts: list) -> str:
    return "".join(f"\n\n{MARKER.format(i)}\n\n{t}" for i, t in enumerate(texts)).lstrip("\n")


def _split(joined: str, count: int) -> list:
    if [int(m.group(1)) for m in _MARKER_RE.finditer(joined)] != list(range(count)):
        raise ValueError("der Dienst hat die Trennmarken des Verlaufs veraendert")
    parts = _MARKER_RE.split(joined)
    out = []
    for i in range(count):
        part = parts[2 + 2 * i]
        part = part[2:] if part.startswith("\n\n") else part.lstrip("\n")
        if i < count - 1 and part.endswith("\n\n"):
            part = part[:-2]
        out.append(part)
    return out


def mask_messages(messages: list, api_url: str, api_key: str = "", timeout: float = 5.0):
    """Maskiert alle Textstellen in einem Aufruf (veraendert ``messages`` direkt).

    Returns:
        Mapping Platzhalter -> Original.
    Raises:
        Exception: bei jedem Fehler (fail-closed); die Anfrage darf dann nicht weitergehen.
    """
    slots = _slots(messages)
    if not slots:
        return {}
    joined = _join([_get(s) for s in slots])
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # Zeitlimit waechst mit der Textlaenge: +1 s je 2000 Zeichen, hoechstens 60 s
    wait = min(60.0, timeout + len(joined) / 2000)
    # reuse_placeholders: gleicher Wert = gleicher Platzhalter (EntityGuard >= 1.2, sonst ignoriert)
    payload = {"text": joined, "reuse_placeholders": True}
    response = requests.post(api_url, json=payload, headers=headers, timeout=wait)
    response.raise_for_status()
    data = response.json()
    masked = next((data[k] for k in TEXT_KEYS if isinstance(data.get(k), str)), None)
    if masked is None:
        raise ValueError("ungueltige Antwort des Dienstes")
    for slot, text in zip(slots, _split(masked, len(slots))):
        _set(slot, text)
    mapping = data.get("mapping") or {}
    return mapping if isinstance(mapping, dict) else {}


def restore(text: str, mapping: dict) -> str:
    """Platzhalter zuruecksetzen, laengste zuerst ([NAME_10] vor [NAME_1])."""
    for placeholder in sorted(mapping, key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(default="http://localhost:9500/api/v1/sanitize", description="Sanitizer-Endpunkt")
        api_key: str = Field(default="", description="API-Key des Dienstes (EntityGuard: unter API-Schlüssel erzeugen)")
        timeout: int = Field(default=5, description="Grundlimit in Sekunden (waechst mit der Textlaenge)")
        restore_mapping: bool = Field(default=True, description="Platzhalter in der Antwort zurueckuebersetzen")

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __metadata__: dict = None, __user__: Optional[dict] = None) -> dict:
        messages = body.get("messages") or []
        if not messages:
            return body
        try:
            mapping = mask_messages(messages, self.valves.api_url, self.valves.api_key, self.valves.timeout)
        except Exception as e:
            logger.error("Sanitizer fehlgeschlagen: %s", e)
            raise Exception(f"Privacy stop: Security check failed: {e}")  # stoppt die Anfrage
        if __metadata__ is not None:
            __metadata__["sanitizer_mapping"] = mapping
        return body

    def outlet(self, body: dict, __metadata__: dict = None) -> dict:
        mapping = (__metadata__ or {}).get("sanitizer_mapping") or {}
        if not self.valves.restore_mapping or not mapping:
            return body
        for message in body.get("messages", []):
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                message["content"] = restore(message["content"], mapping)
        return body
