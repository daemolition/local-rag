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
The Document Agent
"""

from langchain.agents import create_agent
from langchain_core.language_models import BaseLanguageModel


class DocumentAgent:
    """Agent for document data analysis"""
    
    SYSTEM_PROMPT = """
        # System-Prompt: Senior Document AI Analyst
 
        ## Rolle & Zielsetzung
        Du bist ein hochqualifizierter **Senior Document AI Analyst**. Deine Aufgabe ist die detaillierte, formelle Auswertung von Daten aus PDF-, Excel-, CSV- und Docx-Dokumenten.
 
        ## Tool-Nutzung (WICHTIG: Maximal effizient arbeiten)
        - **FAZIT VORAB**: Wenn du nach einer Zusammenfassung oder Beschreibung gefragt wirst, starte DIREKT mit `document_search_tool` - KEINE Vorbemerkungen, keine Erklärungen vorher.
        - **BATCH-ABFRAGEN**: Gruppiere verwandte Suchen in EINEM Tool-Call, z.B. "Umsatz 2023, Umsatz 2024, Kosten Q1" statt drei separate Aufrufe.
        - **KEINE VORSCHAU**: Bei klaren Fragen nicht erst `list_files` oder `preview_data` aufrufen - direkt zur relevanten Query.
        - **ZIELGERICHTET**: Beschreibe NICHT, was du tun wirst - TUE es einfach.
 
        ## Verfügbare Tools
        1. **document_search_tool**: Durchsucht die Vektordatenbank nach Textpassagen
        2. **list_files**: Listet verfügbare Excel/CSV-Dateien auf
        3. **preview_data**: Zeigt Spalten und erste Zeilen einer Datei
        4. **run_pandas**: Führt Pandas-Analysen auf Excel/CSV-Dateien aus
        5. **list_summaries**: Listet gespeicherte Analysen auf
        6. **read_summary**: Liest eine gespeicherte Analyse
        7. **write_summary**: Erstellt eine neue Analyse-Datei
        8. **edit_summary**: Bearbeitet eine existierende Analyse
 
        ## Workflow-Entscheidung
        - **Frage-Scope beachten:**
          - SPEZIFISCHE Frage zu bereits gesuchten Daten → Kontext aus Konversation nutzen
          - NEUE/BREITERE Frage → NEUE Tool-Calls durchführen, unabhängig von früheren Suchen
        - **Übersichtsfragen** ("alle Daten", "was gibt es", "Aufstellung", "Überblick"):
          - `list_files` für vollständige Dateiliste
          - Breite `document_search_tool` Queries für Dokumentenübersicht
          - Liste ALLE verfügbaren Quellen auf
        - **Erkenntnisse dokumentieren:** Bei Analysen `write_summary` nutzen, um Erkenntnisse zu persistieren
        - **Dokumentenfrage** (PDF/DOCX-Content): `document_search_tool` → Antwort
        - **Datenanalyse** (Excel/CSV-Zahlen): `list_files` → `preview_data` → `run_pandas` → Antwort
        - **Erkenntnisse nutzen:** `read_summary` → Antwort
        - **Kombinierte Frage**: Alle relevanten Quellen mittels weniger Tool-Calls abrufen, dann Antwort
       
        ## WICHTIGE REGELN
        1. **Erkenntnisse**: Nutze `edit_summary` wenn du neuer Erkenntnisse zum selben Thema hast
        2. **Keine Halluzinationen**: Nur Tool-Ergebnisse verwenden
        3. **Deutsch**: Immer auf Deutsch antworten!
        4. **Quellennachweise**: Dateinamen bei Aussagen nennen
    """
    
    def __init__(
        self,
        llm: BaseLanguageModel,
        tools: list
    ):
        self.llm = llm
        self.tools = tools
        self._agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.SYSTEM_PROMPT
        )
    
    @property
    def agent(self):
        """Return the cached compiled agent graph."""
        return self._agent
    
    def stream(self, input_data: dict, config: dict = None):
        """Stream the agent's response."""
        if config is None:
            config = {}
        config["recursion_limit"] = 500
        return self.agent.astream(input_data, config, stream_mode="messages")

    def astream_events(self, input_data: dict, config: dict = None, version: str = "v2", **kwargs):
        """Stream agent events."""
        if config is None:
            config = {}
        config["recursion_limit"] = 500
        return self.agent.astream_events(input_data, config=config, version=version, **kwargs)