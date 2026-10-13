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
Einstellungen der Einlese-Aufgaben "Bildbeschreibung" (vision) und "Kontext-Anreicherung"
(context): Prompt, Modell, Parameter. Alles liegt in der Datenbank (``settings``) und wird
bei jedem Aufruf frisch gelesen; ``app/ingest/prompts.py`` liefert nur die Samen.
"""

from app.database_service import get_db_service
from app.ingest import prompts
from app.models import Setting
from app.settings_service import SettingsService

TASKS = ("vision", "context")
MAX_PROMPT_CHARS = 8000

_PROMPT_KEY = {"vision": "VISION_PROMPT", "context": "CONTEXT_PROMPT"}
_SEED = {"VISION_PROMPT": prompts.VISION_PROMPT, "CONTEXT_PROMPT": prompts.CONTEXT_PROMPT}
_ENABLED_KEY = {"vision": "INGEST_VISION_ENABLED", "context": "INGEST_CONTEXT_ENRICHMENT"}


def _float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def _int(raw: str | None) -> int | None:
    try:
        return int(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def load_task(task: str) -> dict:
    """Prompt, Modell und Parameter einer Aufgabe (siehe Modul-Docstring)."""
    if task not in TASKS:
        raise ValueError(f"Unbekannte Aufgabe: {task}")
    prefix = task.upper()
    prompt_key = _PROMPT_KEY[task]
    session = get_db_service().get_session()
    try:
        s = SettingsService(session)
        stored = session.query(Setting).filter_by(key=prompt_key).first()
        prompt = (s.get(prompt_key) or "").strip() or _SEED[prompt_key]
        default_prompt = ((stored.default_value if stored else "") or "").strip() or _SEED[prompt_key]
        return {
            "enabled": s.get_bool(_ENABLED_KEY[task], True),
            "model_ref": s.get(f"{prefix}_MODEL_REF", "") or "",
            "temperature": _float(s.get(f"{prefix}_TEMPERATURE")),
            "max_tokens": _int(s.get(f"{prefix}_MAX_TOKENS")),
            "prompt": prompt,
            "default_prompt": default_prompt,
            "excerpt_chars": s.get_int("CONTEXT_EXCERPT_CHARS", prompts.CONTEXT_EXCERPT_CHARS)
            if task == "context"
            else None,
        }
    finally:
        session.close()


def render_context_prompt(template: str, dokument: str, abschnitt: str) -> str:
    """Setzt Auszug und Abschnitt ein (``str.replace``: geschweifte Klammern im Text sind harmlos)."""
    return template.replace("{dokument}", dokument).replace("{abschnitt}", abschnitt)


def validate_prompt(task: str, text: str) -> str | None:
    """Fehlermeldung oder ``None``."""
    text = (text or "").strip()
    if not text:
        return "Der Prompt darf nicht leer sein"
    if len(text) > MAX_PROMPT_CHARS:
        return f"Der Prompt ist zu lang (höchstens {MAX_PROMPT_CHARS} Zeichen)"
    if task == "context" and "{abschnitt}" not in text:
        return "Der Kontext-Prompt muss den Platzhalter {abschnitt} enthalten"
    return None
