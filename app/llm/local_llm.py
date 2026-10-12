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
Local LLM with vision - supports separate chat and vision models
"""

# Standard library
import time

from langchain_core.messages import HumanMessage

from app.llm.factory import build_chat_llm
from app.utils.phase_logger import Phase, phase_logger


class VisionLLM:
    """Modell fuer Bildbeschreibungen und die Kontextanreicherung beim Einlesen.

    Das Modell kommt aus Verbindungen und Modellen (Administration): ``VISION_MODEL_REF``
    waehlt es auf der Seite "Einlesen & Modelle", ohne Auswahl gilt das Standardmodell.
    Aufgeloest wird bei jedem Aufruf, Aenderungen wirken also sofort.
    """

    def __init__(self):
        self._llm = None
        self._signature = None

    def _resolve(self):
        from app.database_service import get_db_service
        from app.llm import registry
        from app.settings_service import SettingsService

        session = get_db_service().get_session()
        try:
            ref = SettingsService(session).get("VISION_MODEL_REF", "") or None
        finally:
            session.close()
        try:
            return registry.resolve_model(ref)
        except registry.ModelUnavailableError:
            if ref:  # gewaehltes Modell weg: auf das Standardmodell zurueckfallen
                return registry.resolve_model(None)
            raise

    @property
    def llm(self):
        """Nicht-streamendes LLM des Vision-Modells (nach Aenderungen neu gebaut)."""
        resolved = self._resolve()
        if self._llm is None or self._signature != resolved.signature():
            self._llm = build_chat_llm(
                resolved.base_url,
                resolved.api_key,
                resolved.model_id,
                {**resolved.params, "thinking": "none"},
                streaming=False,
            )
            self._signature = resolved.signature()
            self.vision_model = resolved.model_id
        return self._llm

    vision_model = ""

    def generate_image_message(
        self, image: str, instruction: str = None
    ) -> HumanMessage:
        """Generiert die Message für den Call ans Visionmodell"""

        img_size_kb = len(image) * 3 / 4 / 1024

        phase_logger.log_phase(
            Phase.VISION_PROCESSING, f"Bild verarbeiten | Größe: {img_size_kb:.1f}KB"
        )

        if not instruction:
            instruction = """
            ## Rolle: 
            Du bist ein spezialisierter Analyst für unstructurierte Dokumente. Deine Aufgabe ist es, Tabellen und Prozessdiagramme in präzise, suchoptimierte Markdown-Beschreibungen zu übersetzen.

            ### Anweisungen:

            **Strukturelle Einordnung:** Beginne mit dem Typ (z. B. "Ablaufdiagramm Genehmigungsprozess" oder "Tabelle Überstundenvergütung").
            **Logik-Extraktion (Wenn-Dann):** Analysiere das Bild gezielt nach Bedingungen und Konsequenzen. Formuliere diese als klare Sätze (z. B. "Wenn [Bedingung], dann [Folge/Aktion]").
            **Daten-Highlights:** Extrahiere bei Tabellen nur die wichtigsten Schwellenwerte, Fristen oder Beträge.
            Erstelle eine kompakte Markdown-Tabelle der Kernwerte (max. 8 Zeilen).

            ## Zuständigkeiten: 
            Nenne explizit alle im Bild vorkommenden Rollen, Abteilungen oder Gremien (z. B. "Personalrat", "IT-Abteilung", "Vorgesetzter").

            ## Zusammenfassung: 
            Schreibe einen abschließenden Satz über den Hauptzweck des Bildes für die Indexierung.

            ## Formatierungsvorgaben:

            * Gib ausschließlich das Markdown-Ergebnis aus.
            * Keine Einleitung ("Hier ist..."), keine Metadaten über das Bild-Preprocessing.
            * Nutze klare Hierarchien mit ### Überschriften.
            * Antworte ausschließlich aus Deutsch
            """

        message = HumanMessage(
            content=[
                {"type": "text", "text": instruction},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                },
            ]
        )

        return message

    def generate(self, message: HumanMessage) -> str:
        """Generiert den Text mit VISION-Modell (für Bilder)"""
        llm = self.llm  # loest das Modell auf und setzt vision_model
        start_time = time.time()
        phase_logger.log_phase(
            Phase.LLM_CALL, f"LLM-Call gestartet | Model: {self.vision_model}"
        )

        result = llm.invoke([message])

        duration = time.time() - start_time
        phase_logger.log_phase(
            Phase.LLM_CALL,
            f"LLM-Response erhalten | Model: {self.vision_model}",
            duration=duration,
        )

        return result.content
