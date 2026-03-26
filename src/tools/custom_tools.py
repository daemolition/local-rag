"""
Custom tools for the agent
"""

# Standard library
import os
import io
import contextlib
from logging import getLogger

# Third party
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from langchain_core.tools import create_retriever_tool
from langchain_core.tools.structured import StructuredTool

logger = getLogger(__name__)


# === Pydantic Input Models ===

class ListFilesInput(BaseModel):
    """Input model for list_files tool."""
    pass


class PreviewDataInput(BaseModel):
    """Input model for preview_data tool."""
    filename: str = Field(
        description="Name der Datei aus der Dateiliste (z. B. 'sales_2024.xlsx')"
    )
    rows: int = Field(
        default=5,
        description="Anzahl der Zeilen für die Vorschau (Standard: 5)"
    )


class RunPandasInput(BaseModel):
    """Input model for run_pandas tool."""
    filename: str = Field(
        description="Name der Datei aus der Dateiliste (z. B. 'sales.xlsx')"
    )
    code: str = Field(
        description="""Python/Pandas-Code, der auf dem DataFrame 'df' ausgeführt wird.
        Beispiele:
        - result = df['Umsatz'].sum()
        - result = df.groupby('Kategorie')['Wert'].mean()
        - result = df[df['Datum'] > '2024-01-01']['Umsatz'].sum()
        WICHTIG: Weise das Ergebnis der Variable 'result' zu für die Rückgabe.
        """
    )


# === Tool Descriptions ===

DOCUMENT_SEARCH_DESCRIPTION = """
### Tool Name:
document_search_tool

### Tool Description:
Sucht und extrahiert relevante Textpassagen, Tabelleninhalte und Datenpunkte aus einer Wissensdatenbank, die PDF-, Excel-, CSV- und Docx-Dokumente enthält.

### Wann dieses Tool verwenden:
1. IMMER, wenn Fakten, Zahlen oder spezifische Details aus den hochgeladenen Dokumenten benötigt werden.
2. Wenn ein dokumentübergreifender Vergleich (z. B. Excel vs. PDF) durchgeführt werden muss.
3. Wenn Unklarheiten oder potenzielle Widersprüche in der Datenlage geprüft werden müssen.

### Anleitung für die Query-Formulierung:
- Da die Daten in kleinen Segmenten (Chunks) vorliegen, generiere präzise, kontextreiche Suchbegriffe.
- Kombiniere Entitäten (z. B. Projektname, Datum, Rechnungsnummer) mit dem gesuchten Attribut (z. B. "Gesamtsumme", "Frist", "Status").
- Wenn ein Vergleich zwischen Dateitypen nötig ist, führe nacheinander spezifische Suchen für die jeweiligen Dokumentinhalte durch.
- Vermeide vage Anfragen; nutze Fachbegriffe aus dem Kontext der Quelldokumente.

### Input:
Ein String, der die spezifische Suchanfrage in natürlicher Sprache oder als Schlagwortkombination enthält.

### Output:
Eine Liste von Textsegmenten (Chunks) inklusive Metadaten wie Dateiname, Seitenzahl oder Zeilennummer.
"""

LIST_FILES_DESCRIPTION = """
### Tool Name:
list_files

### Tool Description:
Listet alle verfügbaren Excel- (.xlsx) und CSV-Dateien (.csv) im konfigurierten Datenverzeichnis auf.
Dies ist der erste Schritt für jede Datenanalyse, um zu verstehen, welche Datensätze überhaupt zur Verfügung stehen.

### Wann dieses Tool verwenden:
1. IMMER als ERSTES, wenn der Nutzer nach Zahlen, Statistiken, Berechnungen oder Datenanalysen fragt.
2. Wenn unklar ist, welche Datensätze verfügbar sind.
3. Um die richtige Datei für eine nachfolgende Analyse zu identifizieren.

### Workflow:
1. Rufe `list_files` auf, um alle verfügbaren Dateien zu erhalten.
2. Analysiere die Dateinamen auf Relevanz zur Nutzerfrage (z. B. "sales" für Umsatzfragen).
3. Nutze anschließend `preview_data`, um den Inhalt verdächtiger Dateien zu prüfen.
4. Führe dann mit `run_pandas` die eigentliche Analyse durch.

### Input:
Keine Parameter erforderlich.

### Output:
Eine Liste von Dateinamen als Strings (z. B. ["sales_2024.xlsx", "customers.csv", "products.xlsx"]).
"""

PREVIEW_DATA_DESCRIPTION = """
### Tool Name:
preview_data

### Tool Description:
Zeigt die Spaltennamen und die ersten N Zeilen einer Excel- oder CSV-Datei an.
Ermöglicht eine schnelle Bewertung, ob die Daten für eine spezifische Frage relevant sind,
ohne die gesamte Datei laden und analysieren zu müssen.

### Wann dieses Tool verwenden:
1. NACH dem Aufruf von `list_files`, um den Inhalt einer Datei zu inspizieren.
2. Um zu prüfen, ob bestimmte Spalten (z. B. 'Umsatz', 'Datum', 'Kunde') vorhanden sind.
3. Um das Datenformat zu verstehen, bevor `run_pandas` aufgerufen wird.
4. Wenn der Nutzer fragt, "was in einer Datei steht" oder "welche Spalten es gibt".

### Workflow:
1. Erhalte Dateiliste via `list_files`.
2. Wähle eine möglicherweise relevante Datei.
3. Rufe `preview_data` mit dem Dateinamen auf.
4. Prüfe die Spalten und Beispieldaten auf Relevanz zur Nutzerfrage.
5. Bei Passung: Nutze `run_pandas` für die tiefe Analyse.

### Input:
- filename: Name der Datei aus der Dateiliste (z. B. "sales.xlsx")
- rows: Anzahl der anzuzeigenden Zeilen (Standard: 5)

### Output:
Ein formatierter String mit:
- Liste aller Spaltennamen
- Erste N Zeilen der Daten als Tabelle

Beispiel:
Spalten: ['Datum', 'Produkt', 'Umsatz', 'Menge']

   Datum     | Produkt  | Umsatz | Menge
------------|----------|--------|------
2024-01-01  | ProduktA | 1500   | 10
2024-01-02  | ProduktB | 2300   | 15
"""

RUN_PANDAS_DESCRIPTION = """
### Tool Name:
run_pandas

### Tool Description:
Führt Python/Pandas-Code auf einem geladenen DataFrame aus.
Dieses Tool ermöglicht komplexe Datenanalysen, statistische Berechnungen,
Filterungen, Gruppierungen und Aggregationen – wie ein professioneller Datenanalyst.

### Wann dieses Tool verwenden:
1. NACHDEM du mit `preview_data` die Struktur der Daten verstanden hast.
2. Wenn Berechnungen, Summen, Durchschnitte, Zählungen oder andere Statistiken benötigt werden.
3. Wenn der Nutzer spezifische Fragen zu Zahlen in den Daten stellt.
4. Wenn `document_search_tool` keine ausreichenden Ergebnisse liefert (für numerische Daten).

### Workflow:
1. Liste Dateien auf (`list_files`).
2. Inspiziere relevante Dateien (`preview_data`).
3. Formuliere den Pandas-Code basierend auf Spaltennamen und Analyseziel.
4. Weise das Ergebnis der Variable `result` zu (wichtig!).
5. Rufe `run_pandas` auf und erhalte das analytische Ergebnis.

### Input:
- filename: Name der Datei (z. B. "sales.xlsx")
- code: Python/Pandas-Code, der auf dem DataFrame 'df' ausgeführt wird

### Code-Beispiele:
- Gesamtumsatz: result = df['Umsatz'].sum()
- Durchschnitt: result = df['Wert'].mean()
- Gefilterte Summe: result = df[df['Jahr'] == 2024]['Umsatz'].sum()
- Gruppierung: result = df.groupby('Kategorie')['Umsatz'].sum()
- Count unique: result = df['Kunde'].nunique()
- Mehrere Metriken: result = df.agg({'Umsatz': ['sum', 'mean'], 'Menge': 'sum'})

### WICHTIG:
- Der DataFrame ist als Variable `df` verfügbar.
- Pandas ist als `pd` importiert.
- NumPy ist als `np` importiert.
- Das Ergebnis MUSS der Variable `result` zugewiesen werden.
- Nur lesende Operationen erlaubt (keine Datei-Exports).

### Sicherheit:
Folgende Befehle sind aus Sicherheitsgründen BLOCKIERT:
- os., sys., subprocess, __import__, open, to_csv, to_sql, to_json, eval(, exec(

### Output:
Ein String mit dem Analyseergebnis oder einer Fehlermeldung bei Problemen.
"""


class CustomTools:
    """Custom tools for RAG agent with pandas analytics capabilities."""
    
    def __init__(self, llm, retriever):
        self.llm = llm
        self.retriever = retriever
        self._cache: dict[str, pd.DataFrame] = {}
        self.DATA_DIR = os.getenv("DATA_DIR", "./data")
    
    def _get_dataframe(self, filename: str) -> pd.DataFrame:
        """Lädt DataFrame mit Caching."""
        if filename not in self._cache:
            path = os.path.join(self.DATA_DIR, filename)
            try:
                if filename.endswith('.xlsx'):
                    self._cache[filename] = pd.read_excel(path)
                elif filename.endswith('.csv'):
                    self._cache[filename] = pd.read_csv(path)
                else:
                    raise ValueError(f"Dateiformat nicht unterstützt: {filename}")
            except Exception as e:
                logger.error(f"Fehler beim Laden von {filename}: {e}")
                raise
        return self._cache[filename]
    
    def list_files(self) -> list[str]:
        """Listet alle xlsx/csv Dateien im Datenverzeichnis auf."""
        if not os.path.exists(self.DATA_DIR):
            return f"FEHLER: Datenverzeichnis '{self.DATA_DIR}' existiert nicht."
        
        files = os.listdir(self.DATA_DIR)
        data_files = [f for f in files if f.endswith(('.xlsx', '.csv'))]
        
        if not data_files:
            return f"Keine Excel- oder CSV-Dateien im Verzeichnis '{self.DATA_DIR}' gefunden."
        
        return data_files
    
    def preview_data(self, filename: str, rows: int = 5) -> str:
        """Zeigt Spalten und erste Zeilen einer Datei an."""
        try:
            df = self._get_dataframe(filename)
            
            if df.empty:
                return f"Die Datei '{filename}' ist leer."
            
            columns_str = ", ".join([f"'{col}'" for col in df.columns])
            preview_str = df.head(rows).to_string()
            
            return f"Spalten ({len(df.columns)}): {columns_str}\n\nAnzahl Zeilen: {len(df)}\n\nVorschau ({rows} Zeilen):\n{preview_str}"
            
        except Exception as e:
            return f"FEHLER beim Laden von '{filename}': {type(e).__name__}: {e}"
    
    def run_pandas(self, filename: str, code: str) -> str:
        """Führt Pandas-Code auf einem DataFrame aus."""
        try:
            df = self._get_dataframe(filename)
        except Exception as e:
            return f"FEHLER: Datei '{filename}' konnte nicht geladen werden: {e}"
        
        if df.empty:
            return f"Die Datei '{filename}' ist leer oder enthält keine Daten."
        
        # Guardrails / Security
        forbidden_keywords = [
            "os.", "sys.", "subprocess", "__import__", "open(",
            "to_csv", "to_sql", "to_json", "to_excel", "to_pickle",
            "eval(", "exec(", "compile(", "__builtins__",
            "import os", "import sys", "import subprocess"
        ]
        
        for word in forbidden_keywords:
            if word in code:
                return f"FEHLER: '{word}' ist aus Sicherheitsgründen blockiert."
        
        # Exec globals
        exec_globals = {
            "__builtins__": {
                "range": range, "len": len, "sum": sum, "min": min, "max": max,
                "abs": abs, "round": round, "sorted": sorted, "enumerate": enumerate,
                "zip": zip, "map": map, "filter": filter, "list": list, "dict": dict,
                "set": set, "tuple": tuple, "str": str, "int": int, "float": float,
                "bool": bool, "print": print, "isinstance": isinstance, "type": type,
                "True": True, "False": False, "None": None,
                "Exception": Exception, "ValueError": ValueError, "KeyError": KeyError,
                "TypeError": TypeError, "RuntimeError": RuntimeError, "IndexError": IndexError,
                "AttributeError": AttributeError, "ZeroDivisionError": ZeroDivisionError,
            },
            "df": df,
            "pd": pd,
            "np": np,
            "result": None,
        }
        
        output_buffer = io.StringIO()
        
        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(code, exec_globals)
            
            result = exec_globals.get("result")
            printed_output = output_buffer.getvalue().strip()
            
            report = []
            
            if printed_output:
                report.append(f"Konsolenausgabe:\n{printed_output}")
            
            if result is not None:
                report.append(f"Ergebnis:\n{result}")
            
            if not report:
                return "Code wurde ausgeführt, aber kein Ergebnis zurückgegeben.\nTipp: Weise das Ergebnis der Variable 'result' zu, z. B.: result = df['Spalte'].sum()"
            
            return "\n\n".join(report)
            
        except Exception as e:
            logger.error(f"Pandas-Ausführung fehlgeschlagen: {type(e).__name__}: {e}")
            return f"FEHLER bei der Ausführung: {type(e).__name__}: {e}\n\nKorrigiere den Code und versuche erneut."
    
    def get_tools(self) -> list:
        """Gibt alle verfügbaren Tools zurück."""
        
        # Document Search Tool
        document_search_tool = create_retriever_tool(
            retriever=self.retriever,
            name="document_search_tool",
            description=DOCUMENT_SEARCH_DESCRIPTION,
        )
        
        # List Files Tool
        list_files_tool = StructuredTool.from_function(
            func=self.list_files,
            name="list_files",
            description=LIST_FILES_DESCRIPTION,
            args_schema=ListFilesInput,
        )
        
        # Preview Data Tool
        preview_data_tool = StructuredTool.from_function(
            func=self.preview_data,
            name="preview_data",
            description=PREVIEW_DATA_DESCRIPTION,
            args_schema=PreviewDataInput,
        )
        
        # Run Pandas Tool
        run_pandas_tool = StructuredTool.from_function(
            func=self.run_pandas,
            name="run_pandas",
            description=RUN_PANDAS_DESCRIPTION,
            args_schema=RunPandasInput,
        )
        
        return [
            document_search_tool,
            list_files_tool,
            preview_data_tool,
            run_pandas_tool,
        ]