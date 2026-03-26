"""
Custom tools for the agent
"""

# Third party
from langchain_core.tools import create_retriever_tool

class CustomTools:
    """Custom tool class"""
    def __init__(
        self,
        llm,
        retriever
    ):
        self.llm = llm
        self.retriever = retriever
        
    def get_tools(self):        
        
        description = """
            ### Tool Name:
            document_retriever

            ### Tool Description:
            Sucht und extrahiert relevante Textpassagen, Tabelleninhalte und Datenpunkte aus einer Wissensdatenbank, die PDF-, Excel-, CSV- und Docx-Dokumente enthält. 

            Verwende dieses Tool immer, wenn:
            1. Fakten, Zahlen oder spezifische Details aus den hochgeladenen Dokumenten benötigt werden.
            2. Ein dokumentübergreifender Vergleich (z. B. Excel vs. PDF) durchgeführt werden muss.
            3. Unklarheiten oder potenzielle Widersprüche in der Datenlage geprüft werden müssen.

            Anleitung für die Query-Formulierung:
            - Da die Daten in kleinen Segmenten (Chunks) vorliegen, generiere präzise, kontextreiche Suchbegriffe.
            - Kombiniere Entitäten (z. B. Projektname, Datum, Rechnungsnummer) mit dem gesuchten Attribut (z. B. "Gesamtsumme", "Frist", "Status").
            - Wenn ein Vergleich zwischen Dateitypen nötig ist, führe nacheinander spezifische Suchen für die jeweiligen Dokumentinhalte durch.
            - Vermeide vage Anfragen; nutze Fachbegriffe aus dem Kontext der Quelldokumente.

            Input: Ein String, der die spezifische Suchanfrage in natürlicher Sprache oder als Schlagwortkombination enthält.
            Output: Eine Liste von Textsegmenten (Chunks) inklusive Metadaten wie Dateiname, Seitenzahl oder Zeilennummer.
            """
         
        document_search_tool = create_retriever_tool(
            retriever=self.retriever,
            name="document_search",
            description=description,            
        )
        
        return [document_search_tool]
            
            
    
        