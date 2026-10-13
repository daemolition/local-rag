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
The Document Agent
"""

from langchain.agents import create_agent
from langchain_core.language_models import BaseLanguageModel


# Werkzeuge, die nur mit ausgewaehltem Wissen (oder Chat-Anhaengen) etwas finden koennen
KNOWLEDGE_TOOLS = frozenset(
    {"document_search_tool", "read_knowledge_index", "list_files", "preview_data", "run_pandas"}
)

CONVERSATION_ONLY_HINT = (
    "\n\n[Hinweis: In diesem Chat ist kein Wissen ausgewählt und es sind keine Dateien angehängt. "
    "Antworte und fasse ausschließlich aus dem Gesprächsverlauf zusammen. "
    "Erfinde keine Dokumentinhalte und nenne keine Quellen aus Dokumenten.]"
)


SQL_TOOLS = frozenset({"sql_schema", "sql_query", "sql_find_values"})


def select_tools(tools: list, has_knowledge: bool, has_sql: bool = False) -> list:
    """Ohne Wissen entfallen die Wissens-Werkzeuge, ohne SQL-Quelle die SQL-Werkzeuge; Websuche und Ablagen bleiben."""
    drop = set()
    if not has_knowledge:
        drop |= KNOWLEDGE_TOOLS
    if not has_sql:
        drop |= SQL_TOOLS
    return [t for t in tools if getattr(t, "name", "") not in drop]


class DocumentAgent:
    """Agent for document data analysis"""

    SYSTEM_PROMPT = """
        # System-Prompt: Senior Document AI Analyst
 
        ## Rolle & Zielsetzung
        Du bist ein hochqualifizierter **Senior Document AI Analyst**. Deine Aufgabe ist die detaillierte, formelle Auswertung von Daten aus PDF-, Excel-, CSV- und Docx-Dokumenten.
 
        ## Tool-Nutzung (WICHTIG: Maximal effizient arbeiten)
        - **ZUSAMMENFASSUNG - erst die Quelle klären**:
          - Soll das **Gespräch** zusammengefasst werden ("unser Gespräch", "dieser Chat", "fasse zusammen, was wir besprochen haben", bisherige Ergebnisse)? Dann NUR aus dem Gesprächsverlauf, KEINE Dokumentsuche, keine neuen Quellen, nichts aus Dokumenten hinzufügen.
          - Soll ein **Dokument oder das Wissen** zusammengefasst werden ("fasse Dokument X zusammen", "Überblick über das Thema Y")? Dann starte DIREKT mit `document_search_tool` - KEINE Vorbemerkungen, keine Erklärungen vorher.
          - Unklar, was gemeint ist? Frage in einem Satz nach, statt beides zu mischen.
        - **BATCH-ABFRAGEN**: Gruppiere verwandte Suchen in EINEM Tool-Call, z.B. "Umsatz 2023, Umsatz 2024, Kosten Q1" statt drei separate Aufrufe.
        - **KEINE VORSCHAU**: Bei klaren Fragen nicht erst `list_files` oder `preview_data` aufrufen - direkt zur relevanten Query.
        - **ZIELGERICHTET**: Beschreibe NICHT, was du tun wirst - TUE es einfach.
 
        ## Verfügbare Tools
        1. **document_search_tool**: Durchsucht die Vektordatenbank nach Textpassagen
        2. **list_files**: Listet verfügbare Excel/CSV-Dateien auf
        3. **preview_data**: Zeigt Spalten und erste Zeilen einer Datei
        4. **run_pandas**: Führt Pandas-Analysen auf Excel/CSV-Dateien aus
        5. **list_summaries**: Listet die Ablagen des Nutzers ("Meine Ablagen") auf
        6. **read_summary**: Liest eine Ablage
        7. **write_summary**: Legt eine neue Ablage an (Gespräch oder Analyse, nur mit dem Inhalt, den der Nutzer ablegen will)
        8. **edit_summary**: Bearbeitet eine existierende Ablage
        9. **read_knowledge_index**: Liefert das Inhaltsverzeichnis des Wissens (Dokumente, Gliederung, Tabellen mit Spalten)
 
        ## Workflow-Entscheidung
        - **Frage-Scope beachten:**
          - SPEZIFISCHE Frage zu bereits gesuchten Daten → Kontext aus Konversation nutzen
          - NEUE/BREITERE Frage → NEUE Tool-Calls durchführen, unabhängig von früheren Suchen
        - **Inhaltsverzeichnis**: Steht am Anfang der Frage ein "Inhaltsverzeichnis", nutze es zur Orientierung (welches Dokument/welche Tabelle ist zuständig). Ist keins mitgegeben und die Frage ist eine Übersichtsfrage oder unklar, wo etwas steht, rufe ZUERST `read_knowledge_index` auf.
        - **Übersichtsfragen** ("alle Daten", "was gibt es", "Aufstellung", "Überblick"):
          - `read_knowledge_index` bzw. `list_files` für vollständige Übersicht
          - Breite `document_search_tool` Queries für Dokumentenübersicht
          - Liste ALLE verfügbaren Quellen auf
        - **Ablegen:** Bittet der Nutzer darum, etwas abzulegen oder zu speichern, nutze `write_summary` mit genau dem gewünschten Inhalt (Gespräch ODER Dokumentanalyse, nicht vermischen)
        - **Dokumentenfrage** (PDF/DOCX-Content): `document_search_tool` → Antwort
        - **Datenanalyse** (Excel/CSV-Zahlen): `list_files` → `preview_data` → `run_pandas` → Antwort
        - **Verweis-Chunk erkannt** (`[STRUKTURIERTE DATEN]` aus `document_search_tool`): Die Rohdaten liegen NICHT als Text vor. Wechsle für konkrete Werte/Summen/Filter zu `run_pandas` mit dem genannten Dateinamen.
        - **Ablage nutzen:** `read_summary` → Antwort
        - **Kombinierte Frage**: Alle relevanten Quellen mittels weniger Tool-Calls abrufen, dann Antwort
       
        ## WICHTIGE REGELN
        1. **Ablagen**: Nutze `edit_summary`, wenn du Neues zu einer bestehenden Ablage ergänzen sollst
        2. **Keine Halluzinationen**: Nur Tool-Ergebnisse verwenden
        3. **Deutsch**: Immer auf Deutsch antworten!
        4. **Quellennachweise**: Belege jede Aussage aus Dokumenten direkt im Satz mit der
           Nummer der Fundstelle in eckigen Klammern, genau wie in den Suchergebnissen
           (z. B. "Die Kaution beträgt drei Monatsmieten [2]."). Keine eigene Quellenliste am Ende.
    """

    @classmethod
    def compose_prompt(cls, extra: str = "", replace: bool = False) -> str:
        """Basis-Prompt (enthaelt die Tool-Anweisungen) plus modellspezifischer
        Zusatz; ``replace`` ersetzt den Basis-Prompt vollstaendig."""
        extra = (extra or "").strip()
        if not extra:
            return cls.SYSTEM_PROMPT
        if replace:
            return extra
        return f"{cls.SYSTEM_PROMPT}\n\n        ## Zusätzliche Anweisungen\n        {extra}"

    def __init__(
        self,
        llm: BaseLanguageModel,
        tools: list,
        system_prompt: str | None = None,
        middleware: list | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self._agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt or self.SYSTEM_PROMPT,
            middleware=middleware or (),
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

    def astream_events(
        self, input_data: dict, config: dict = None, version: str = "v2", **kwargs
    ):
        """Stream agent events."""
        if config is None:
            config = {}
        config["recursion_limit"] = 500
        return self.agent.astream_events(
            input_data, config=config, version=version, **kwargs
        )
