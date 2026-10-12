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
Websuche und PII-Filter aus den aktuellen Einstellungen.

Die Websuche (SearXNG) ist ein Werkzeug, das pro Modell zugeschaltet wird (Modelle >
Konfigurieren). Sie steht nur zur Verfuegung, wenn SearXNG UND ein aktiver PII-Filter
eingerichtet sind: Suchanfragen verlassen das System, deshalb werden sie vorher maskiert.
Alles wird bei jedem Aufruf frisch aus den Einstellungen gelesen.
"""

from logging import getLogger

from app.database_service import get_db_service
from app.settings_service import SettingsService

logger = getLogger(__name__)

_clients: dict[tuple, object] = {}


def _settings() -> dict:
    session = get_db_service().get_session()
    try:
        s = SettingsService(session)
        return {
            "searxng_url": (s.get("SEARCH_SEARXNG_URL") or "").strip(),
            "categories": s.get("SEARCH_SEARXNG_CATEGORIES", "general") or "general",
            "pii_url": (s.get("PII_FILTER_URL") or "").strip(),
            "pii_key": s.get("PII_FILTER_API_KEY") or "",
            "pii_enabled": s.get_bool("PII_FILTER_ENABLED", True),
        }
    finally:
        session.close()


def pii_client():
    """PII-Filter-Client oder ``None``, wenn nicht eingerichtet bzw. abgeschaltet."""
    cfg = _settings()
    if not (cfg["pii_url"] and cfg["pii_enabled"]):
        return None
    key = (cfg["pii_url"], cfg["pii_key"])
    if key not in _clients:
        from app.utils.pii_filter_client import PIIFilterClient

        _clients[key] = PIIFilterClient(full_url=cfg["pii_url"], api_key=cfg["pii_key"] or None)
    return _clients[key]


def web_search_available() -> bool:
    cfg = _settings()
    return bool(cfg["searxng_url"] and cfg["pii_url"] and cfg["pii_enabled"])


def build_web_search_tool():
    """Das Websuche-Werkzeug oder ``None``, wenn SearXNG bzw. der PII-Filter fehlt."""
    cfg = _settings()
    if not (cfg["searxng_url"] and cfg["pii_url"] and cfg["pii_enabled"]):
        return None
    from app.tools.web_search_tool import create_web_search_tool

    return create_web_search_tool(
        searxng_url=cfg["searxng_url"],
        default_categories=cfg["categories"],
        pii_filter_client=pii_client(),
    )
