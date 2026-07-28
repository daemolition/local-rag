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
Web-Suche Tool für SearXNG Metasuchmaschine
"""

import time
import requests
from logging import getLogger
from app.utils.phase_logger import phase_logger, Phase
from pydantic import BaseModel, Field
from langchain_core.tools.structured import StructuredTool

logger = getLogger(__name__)


class WebSearchInput(BaseModel):
    """Input model für web_search_tool."""

    query: str = Field(
        description="Die Suchanfrage in natürlicher Sprache (z.B. 'Was ist die Hauptstadt von Frankreich?')"
    )
    num_results: int = Field(
        default=10, description="Anzahl der Suchergebnisse (Standard: 10, Maximum: 50)"
    )
    categories: str = Field(
        default="general",
        description="Durchsuchbare Kategorien, Komma-getrennt (z.B. 'general,news,science')",
    )


WEB_SEARCH_DESCRIPTION = """
### Tool Name:
web_search_tool

### Tool Description:
Durchsucht das Web mittels SearXNG Metasuchmaschine nach Informationen, die nicht in der lokalen
Vektordatenbank oder den hochgeladenen Dokumenten vorhanden sind. Dieses Tool dient als Ergänzung
zum RAG-System: Immer wenn eine Nutzerfrage Wissen erfordert, das weder in den Dokumenten noch
im internen Wissen des Modells abgebildet ist, kann dieses Tool externe Quellen abrufen.

### Wann dieses Tool verwenden:
1. Wenn die Nutzerfrage Themen betrifft, die **nicht in den hochgeladenen Dokumenten** enthalten sind.
2. Wenn die lokale Vektordatenbank (`document_search_tool`) **keine passenden Ergebnisse** liefert.
3. Wenn aktuelle, tagesaktuelle oder sehr spezifische Informationen benötigt werden, die das RAG-System nicht abdeckt.
4. Zur Ergänzung und Validierung von Fakten, bei denen die internen Quellen lückenhaft sein könnten.

### Workflow:
1. Prüfe zuerst, ob `document_search_tool` die Frage beantworten kann.
2. Nur wenn die lokalen Dokumente keine ausreichende Antwort liefern, formuliere eine präzise Suchanfrage.
3. Rufe `web_search_tool` mit der Query auf.
4. Analysiere die Suchergebnisse und extrahiere relevante Informationen.
5. Kombiniere die externen Ergebnisse mit dem Kontext aus den lokalen Dokumenten.

### Input:
- query: Die Suchanfrage (präzise, mit Keywords)
- num_results: Anzahl Ergebnisse (Standard: 10, Maximum: 50)
- categories: Kategorien (z.B. 'general,news,science,tech')

### Output:
Ein formatierter String mit:
- Titel der Suchergebnisse
- URL der Quelle
- Kurze Zusammenfassung/Content-Snippet
- Veröffentlichtes Datum (falls verfügbar)

### Beispiel-Output:
```
Ergebnisse für 'Hauptstadt Frankreich Einwohnerzahl':

1. **Frankreich – Wikipedia**
   URL: https://de.wikipedia.org/wiki/Frankreich
   Zusammenfassung: Frankreich ist ein Land in Westeuropa mit der Hauptstadt Paris...

2. **Paris: Bevölkerung, Fläche & Geschichte**
   URL: https://example.com/paris-daten
   Veröffentlicht: 2024-03-10
   Zusammenfassung: Paris hat rund 2,1 Millionen Einwohner im Stadtgebiet...
```

### WICHTIG:
- Nutze dieses Tool **nur dann**, wenn die lokalen Dokumente und das interne Wissen nicht ausreichen.
- SearXNG durchsucht multiple Quellen gleichzeitig (Google, Bing, Wikipedia, etc.).
- Ergebnisse sind bereits nach Relevanz sortiert.
- Bei Zeitangaben immer das Veröffentlichungsdatum der Quelle nennen.
- Formuliere die Query neutral und faktenbasiert, nicht als Nachrichten-Suche.
"""


def create_web_search_tool(
    searxng_url: str, default_categories: str = "general", pii_filter_client=None
) -> callable:
    """
    Erstellt ein web_search_tool für die gegebene SearXNG-Instanz.

    Args:
        searxng_url: URL der SearXNG-Instanz
        default_categories: Standard-Kategorien für die Suche
        pii_filter_client: Optionaler PII-Filter-Client zum Filtern von Queries

    Returns:
        Strukturiertes Tool für LangChain
    """

    def _web_search(query: str, num_results: int = 10, categories: str = None) -> str:
        """Führt Web-Suche via SearXNG durch."""

        start_time = time.time()

        # Query durch PII-Filter schicken (bevor sie an SearXNG geht!)
        search_query = query
        if pii_filter_client:
            try:
                filter_result = pii_filter_client.filter_text(query)
                if filter_result.mapping:
                    logger.info(
                        f"Web-Suche Query: {len(filter_result.mapping)} PII-Entitäten gefiltert"
                    )
                search_query = filter_result.filtered
            except Exception as e:
                logger.warning(
                    f"PII-Filter für Web-Suche fehlgeschlagen: {e} - verwende Original-Query"
                )

        phase_logger.log_phase(
            Phase.TOOL_EXECUTION, f"Tool: web_search | Query: {search_query[:100]}"
        )

        if not searxng_url:
            phase_logger.log_phase(
                Phase.TOOL_EXECUTION,
                "Tool: web_search | Fehler: Keine SearXNG URL konfiguriert",
                duration=0.0,
            )
            return "FEHLER: SearXNG-URL ist nicht konfiguriert. Bitte im Settings-Panel 'SEARCH_SEARXNG_URL' setzen."

        # Num_results auf 50 begrenzen
        num_results = min(max(1, num_results), 50)
        search_categories = categories or default_categories

        # SearXNG API Endpoint
        search_url = f"{searxng_url.rstrip('/')}/search"

        try:
            response = requests.get(
                search_url,
                params={
                    "q": search_query,
                    "format": "json",
                    "categories": search_categories,
                    "pageno": 1,
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                phase_logger.log_phase(
                    Phase.TOOL_EXECUTION,
                    f"Tool: web_search | HTTP {response.status_code}",
                    duration=0.0,
                )
                return f"FEHLER: SearXNG API returned HTTP {response.status_code}"

            data = response.json()
            results = data.get("results", [])

            if not results:
                duration = time.time() - start_time
                phase_logger.log_phase(
                    Phase.TOOL_EXECUTION,
                    "Tool: web_search | Keine Ergebnisse gefunden",
                    duration=duration,
                )
                return f"Keine Suchergebnisse für '{search_query}' gefunden."

            # Ergebnisse formatieren
            formatted = [f"Ergebnisse für '{search_query}':\n"]

            for i, result in enumerate(results[:num_results], 1):
                title = result.get("title", "Ohne Titel")
                url = result.get("url", "")
                content = result.get("content", "")
                published_date = result.get("publishedDate", "")

                entry = f"{i}. **{title}**\n"
                entry += f"   URL: {url}\n"
                if published_date:
                    entry += f"   Veröffentlicht: {published_date}\n"
                if content:
                    entry += (
                        f"   Zusammenfassung: {content[:200]}...\n"
                        if len(content) > 200
                        else f"   Zusammenfassung: {content}\n"
                    )

                formatted.append(entry)

            duration = time.time() - start_time
            phase_logger.log_phase(
                Phase.TOOL_EXECUTION,
                f"Tool: web_search | {len(results)} Ergebnisse gefunden",
                duration=duration,
            )

            return "\n".join(formatted)

        except requests.exceptions.Timeout:
            phase_logger.log_phase(
                Phase.TOOL_EXECUTION, "Tool: web_search | Timeout", duration=0.0
            )
            return "FEHLER: SearXNG-Request timeout nach 10 Sekunden."

        except requests.exceptions.RequestException as e:
            phase_logger.log_phase(
                Phase.TOOL_EXECUTION, f"Tool: web_search | Fehler: {e}", duration=0.0
            )
            return f"FEHLER: Verbindung zu SearXNG fehlgeschlagen: {e}"

        except Exception as e:
            phase_logger.log_phase(
                Phase.TOOL_EXECUTION,
                f"Tool: web_search | Unerwarteter Fehler: {e}",
                duration=0.0,
            )
            return f"FEHLER: {type(e).__name__}: {e}"

    return StructuredTool.from_function(
        func=_web_search,
        name="web_search_tool",
        description=WEB_SEARCH_DESCRIPTION,
        args_schema=WebSearchInput,
    )
