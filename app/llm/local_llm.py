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
import os
import time

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.utils.phase_logger import phase_logger, Phase

class VisionLLM:

    def __init__(self):
        """
        Initialisiert das LLM mit getrennten Chat- und Vision-Modellen.

        Chat-/Vision-Konfiguration wird aus der Settings-DB gelesen (UI = Source of
        Truth), mit Fallback auf env fuer den Standalone-Betrieb ohne App-Context.

        Args:
            Chat-Modell: Fuer Agent-Interaktionen und normale Chats
            Vision-Modell: Fuer Bildverarbeitung

        Methods:
            initialize_llm: Initialisiert das llm in der Klasse
        """

        # Defaults
        chat_model = "qwen3:8b"
        chat_base_url = "http://localhost:11434/v1"
        chat_temperature = "0.1"
        chat_top_p = "0.2"
        api_key = "ollama"

        try:
            # Settings aus DB lesen (eigene Session, thread-safe via Engine)
            from app.database_service import get_db_service
            from app.settings_service import SettingsService
            db = get_db_service()
            session = db.get_session()
            settings = SettingsService(session)
            chat_model = settings.get("CHAT_MODEL", chat_model) or chat_model
            chat_base_url = settings.get("CHAT_BASEURL", chat_base_url) or chat_base_url
            chat_temperature = settings.get("CHAT_TEMPERATURE", chat_temperature) or chat_temperature
            chat_top_p = settings.get("CHAT_TOP_P", chat_top_p) or chat_top_p
            vision_model = settings.get("VISION_MODEL", chat_model) or chat_model
            vision_base_url = settings.get("VISION_BASEURL", chat_base_url) or chat_base_url
            api_key = settings.get("API_KEY", api_key) or api_key
            session.close()
        except Exception:
            # Standalone-Fallback (kein DB-Kontext, z. B. Skripte): env
            chat_model = os.getenv("CHAT_MODEL", chat_model)
            chat_base_url = os.getenv("CHAT_BASEURL", chat_base_url)
            chat_temperature = os.getenv("CHAT_TEMPERATURE", chat_temperature)
            chat_top_p = os.getenv("CHAT_TOP_P", chat_top_p)
            vision_model = os.getenv("VISION_MODEL", chat_model)
            vision_base_url = os.getenv("VISION_BASEURL", chat_base_url)
            api_key = os.getenv("API_KEY", api_key)

        self.chat_model = chat_model
        self.chat_base_url = chat_base_url
        self.chat_temperature = float(chat_temperature or "0.1")
        self.chat_top_p = float(chat_top_p or "0.2")

        # Vision model configuration (fallback to chat model settings)
        self.vision_model = vision_model
        self.vision_base_url = vision_base_url

        self.api_key = api_key

        # Initialize LLMs
        self.llm = self._initialize_vision_llm()
        self.llm_stream = self._initialize_chat_llm(streaming=True)


    def _initialize_chat_llm(self, streaming: bool = False):
        """Initialisiert das Chat-LLM (für Agent-Interaktionen)"""
        return ChatOpenAI(
            model=self.chat_model,
            base_url=self.chat_base_url,
            api_key=self.api_key,
            streaming=streaming,
            temperature=self.chat_temperature,
            top_p=self.chat_top_p
        )


    def _initialize_vision_llm(self):
        """Initialisiert das Vision-LLM (für Bildverarbeitung)"""
        return ChatOpenAI(
            model=self.vision_model,
            base_url=self.vision_base_url,
            api_key=self.api_key,
            streaming=False
        )
        
    def generate_image_message(self, image: str, instruction: str = None) -> HumanMessage:
        """Generiert die Message für den Call ans Visionmodell"""
        
        img_size_kb = len(image) * 3 / 4 / 1024
        
        phase_logger.log_phase(Phase.VISION_PROCESSING, f"Bild verarbeiten | Größe: {img_size_kb:.1f}KB")
        
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
                {
                    "type": "text", 
                    "text": instruction  
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image}"}
                }
            ]
        )
        
        return message

        
    def generate(self, message: HumanMessage) -> str:
        """Generiert den Text mit VISION-Modell (für Bilder)"""
        start_time = time.time()
        phase_logger.log_phase(Phase.LLM_CALL, f"LLM-Call gestartet | Model: {self.vision_model}")

        result = self.llm.invoke([message])

        duration = time.time() - start_time
        phase_logger.log_phase(Phase.LLM_CALL, f"LLM-Response erhalten | Model: {self.vision_model}", duration=duration)

        return result.content


    def generate_stream(self, prompt: str):
        """Generiert gestreamten Text mit CHAT-Modell (für Chat)"""
        messages = [HumanMessage(content=prompt)]

        start_time = time.time()
        phase_logger.log_phase(Phase.STREAMING, f"LLM-Streaming gestartet | Model: {self.chat_model}")

        for chunk in self.llm_stream.stream(messages):
            yield chunk

        duration = time.time() - start_time
        phase_logger.log_phase(Phase.STREAMING, f"LLM-Streaming abgeschlossen | Model: {self.chat_model}", duration=duration)