"""
Local LLM with vision - supports separate chat and vision models
"""
# Standard library
import os
import time

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from src.utils.phase_logger import phase_logger, Phase

class VisionLLM:

    def __init__(self):
        """
        Initialisiert das LLM mit getrennten Chat- und Vision-Modellen.

        Args:
            Chat-Modell: Für Agent-Interaktionen und normale Chats
            Vision-Modell: Für Bildverarbeitung

        Methods:
            initialize_llm: Initialisiert das llm in der Klasse
        """

        # Chat model configuration (fallback to legacy MODEL env var)
        self.chat_model = os.getenv("CHAT_MODEL", os.getenv("MODEL", "qwen3:8b"))
        self.chat_base_url = os.getenv("CHAT_BASEURL", os.getenv("BASEURL", "http://192.168.1.35:11434/v1"))
        self.chat_temperature = float(os.getenv("CHAT_TEMPERATURE", os.getenv("TEMPERATURE", "0.1")))
        self.chat_top_p = float(os.getenv("CHAT_TOP_P", os.getenv("TOP_P", "0.2")))

        # Vision model configuration (fallback to chat model settings)
        self.vision_model = os.getenv("VISION_MODEL", self.chat_model)
        self.vision_base_url = os.getenv("VISION_BASEURL", self.chat_base_url)

        # Common settings
        self.api_key = os.getenv("API_KEY", "loc-123")

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
        import base64
        
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