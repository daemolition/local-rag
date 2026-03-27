"""
Local LLM with vision
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
        Initialisiert das Vision Model
        
        Args:
            model (str): Das Model
            base_url (str): Die API über das das Visionmodel erreichbar ist
            api_key (str): Der API Key für den API zugriff (für lokal Dummy)
            
        Methods:
            initialize_llm: Initialisiert das llm in der Klasse
        """
        
        self.model = os.getenv("MODEL", "granite3.2-vision:2b-q8_0")
        self.base_url = os.getenv("BASEURL", "http://192.168.1.35:11434/v1")
        self.temperature = os.getenv("TEMPERATURE", 0.1)
        self.top_p = os.getenv("TOP_P", 0.2)
        self.api_key = os.getenv("API_KEY", "loc-123")
        self._llm = None
        
        # Initialisiert das Model direkt mein Aufruf
        self.llm = self.initialize_llm()
        
    
    def initialize_llm(self):
        """Initialisiert das Vision Model"""
        return ChatOpenAI(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            streaming=True
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
        """Generiert den Text"""
        start_time = time.time()
        phase_logger.log_phase(Phase.LLM_CALL, f"LLM-Call gestartet | Model: {self.model}")
        
        result = self.llm.invoke([message])
        
        duration = time.time() - start_time
        phase_logger.log_phase(Phase.LLM_CALL, f"LLM-Response erhalten | Model: {self.model}", duration=duration)
        
        return result.content
    
    
    def generate_stream(self, prompt: str):
        messages = [HumanMessage(content=prompt)]
        
        start_time = time.time()
        phase_logger.log_phase(Phase.STREAMING, "LLM-Streaming gestartet")
        
        for chunk in self.llm.stream(messages):
            yield chunk
        
        duration = time.time() - start_time
        phase_logger.log_phase(Phase.STREAMING, "LLM-Streaming abgeschlossen", duration=duration)