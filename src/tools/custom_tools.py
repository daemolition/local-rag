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


class ListSummariesInput(BaseModel):
    """Input model for list_summaries tool."""
    pass


class ReadSummaryInput(BaseModel):
    """Input model for read_summary tool."""
    filename: str = Field(
        description="Name der Markdown-Datei aus der Liste (z. B. 'analysis_2024.md')"
    )


class WriteSummaryInput(BaseModel):
    """Input model for write_summary tool."""
    filename: str = Field(
        description="Name für die neue Markdown-Datei (z. B. 'sales_summary.md')"
    )
    content: str = Field(
        description="Der Markdown-Inhalt, der in die Datei geschrieben werden soll"
    )


class EditSummaryInput(BaseModel):
    """Input model for edit_summary tool."""
    filename: str = Field(
        description="Name der existierenden Markdown-Datei (z. B. 'analysis.md')"
    )
    content: str = Field(
        description="Der zusätzliche Inhalt, der hinzugefügt oder eingefügt werden soll"
    )
    mode: str = Field(
        default="append",
        description="""Bearbeitungsmodus:
        - 'append': Fügt Inhalt am Ende der Datei hinzu
        - 'prepend': Fügt Inhalt am Anfang der Datei hinzu
        - 'replace': Ersetzt den gesamten Inhalt der Datei
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

LIST_SUMMARIES_DESCRIPTION = """
### Tool Name:
list_summaries

### Tool Description:
Listet alle verfügbaren Markdown-Analysen im summaries-Verzeichnis auf.
Dies ist der erste Schritt, um zu verstehen, welche gespeicherten Analysen bereits existieren.

### Wann dieses Tool verwenden:
1. Wenn der Nutzer wissen möchte, welche Analysen bereits gespeichert wurden.
2. Vor dem Lesen oder Bearbeiten einer Analyse, um den korrekten Dateinamen zu ermitteln.
3. Um den Fortschritt einer Analyse zu überprüfen (weitere Teile hinzugefügt?).

### Workflow:
1. Rufe `list_summaries` auf, um alle verfügbaren Analysen zu sehen.
2. Wähle eine relevante Analyse basierend auf dem Dateinamen.
3. Nutze `read_summary`, um den Inhalt zu lesen.
4. Nutze `edit_summary`, um die Analyse zu erweitern.

### Input:
Keine Parameter erforderlich.

### Output:
Eine Liste von Dateinamen als Strings (z. B. ["analysis_2024.md", "sales_overview.md"]).
"""

READ_SUMMARY_DESCRIPTION = """
### Tool Name:
read_summary

### Tool Description:
Liest den vollständigen Inhalt einer gespeicherten Markdown-Analyse aus dem summaries-Verzeichnis.

### Wann dieses Tool verwenden:
1. Um eine existierende Analyse zu überprüfen.
2. Um eine Analyse als Grundlage für eine neue Analyse zu nutzen.
3. Um den aktuellen Stand einer fortlaufenden Analyse zu sehen.
4. Wenn der Nutzer nach dem Inhalt einer spezifischen Analyse fragt.

### Workflow:
1. Liste Analysen mit `list_summaries` auf.
2. Wähle die gewünschte Datei.
3. Rufe `read_summary` mit dem Dateinamen auf.
4. Analysiere den Inhalt und fahre fort.

### Input:
- filename: Name der Markdown-Datei (z. B. "analysis_2024.md")

### Output:
Der vollständige Inhalt der Markdown-Datei als String.

### WICHTIG:
- Nur Dateien mit .md Endung erlaubt.
- Pfad-Traversal (../ etc.) ist blockiert.
"""

WRITE_SUMMARY_DESCRIPTION = """
### Tool Name:
write_summary

### Tool Description:
Erstellt eine neue Markdown-Analyse-Datei im summaries-Verzeichnis oder überschreibt eine existierende.

### Wann dieses Tool verwenden:
1. Um eine neue Analyse zu starten und zu speichern.
2. Um wichtige Erkenntnisse aus einer Dokumentenanalyse zu persistieren.
3. Um Teilergebnisse zu speichern, die später zu einem Gesamtbild kombiniert werden.
4. Um eine Analyse als Vorlage für zukünftige Analysen zu erstellen.

### Workflow:
1. Führe Analysen durch (document_search, run_pandas, etc.).
2. Strukturiere die Ergebnisse als Markdown.
3. Speichere die Analyse mit `write_summary`.
4. Erweitere später mit `edit_summary` bei Bedarf.

### Input:
- filename: Name der neuen Datei (z. B. "quarterly_report.md")
- content: Der Markdown-Inhalt der Datei

### Markdown-Struktur empfohlen:
```markdown
# Analyse: [Titel]

## Zusammenfassung
[Kurze Zusammenfassung]

## Hauptergebnisse
- Ergebnis 1
- Ergebnis 2

## Details
[Ausführliche Analyse]

## Quellen
- Dokument A
- Tabelle B
```

### Output:
Bestätigung, dass die Datei erstellt wurde, oder eine Fehlermeldung.
"""

EDIT_SUMMARY_DESCRIPTION = """
### Tool Name:
edit_summary

### Tool Description:
Bearbeitet eine existierende Markdown-Analyse-Datei, um neue Erkenntnisse hinzuzufügen oder den Inhalt zu aktualisieren.

### Wann dieses Tool verwenden:
1. Um eine existierende Analyse zu erweitern (append).
2. Um neue Erkenntnisse am Anfang hinzuzufügen (prepend).
3. Um eine Analyse komplett zu aktualisieren (replace).
4. Um mehrere Teilergebnisse zu einem Gesamtbild zusammenzuführen.

### Workflow für Gesamtbild-Erstellung:
1. Erstelle initiale Analyse mit `write_summary`.
2. Führe weitere Analysen durch.
3. Füge neue Abschnitte mit `edit_summary` (mode='append') hinzu.
4. Wiederhole, bis das Gesamtbild vollständig ist.

### Input:
- filename: Name der existierenden Datei (z. B. "analysis.md")
- content: Der hinzuzufügende oder ersetzende Inhalt
- mode: Bearbeitungsmodus:
  * 'append': Fügt Inhalt am Ende hinzu (Standard)
  * 'prepend': Fügt Inhalt am Anfang hinzu
  * 'replace': Ersetzt den gesamten Inhalt

### Beispiele:
- Neue Sektion anhängen: mode='append', content='\n\n## Neue Erkenntnisse\n\n...'
- Wichtige Erkenntnis voranstellen: mode='prepend', content='# WICHTIG: ...\n\n...'
- Komplett neu schreiben: mode='replace', content='# Analyse: ...\n\n...'

### Output:
Bestätigung, dass die Datei bearbeitet wurde, oder eine Fehlermeldung.
"""


class CustomTools:
    """Custom tools for RAG agent with pandas analytics and summary management capabilities."""
    
    def __init__(self, llm, retriever):
        self.llm = llm
        self.retriever = retriever
        self._cache: dict[str, pd.DataFrame] = {}
        self.DATA_DIR = os.getenv("DATA_DIR", "./data")
        self.SUMMARIES_DIR = os.getenv("SUMMARIES_DIR", "./summaries")
    
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
    
    def _validate_summary_filename(self, filename: str) -> str:
        """Validiert und bereinigt den Dateinamen für summaries."""
        if not filename:
            raise ValueError("Dateiname darf nicht leer sein.")
        
        filename = os.path.basename(filename)
        
        if not filename.endswith('.md'):
            filename = f"{filename}.md"
        
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError(f"Ungültiger Dateiname: {filename}")
        
        return filename
    
    def _ensure_summaries_dir(self):
        """Stellt sicher, dass das summaries-Verzeichnis existiert."""
        os.makedirs(self.SUMMARIES_DIR, exist_ok=True)
    
    def list_summaries(self) -> list[str]:
        """Listet alle Markdown-Dateien im summaries-Verzeichnis auf."""
        self._ensure_summaries_dir()
        
        if not os.path.exists(self.SUMMARIES_DIR):
            return f"FEHLER: Summaries-Verzeichnis '{self.SUMMARIES_DIR}' existiert nicht."
        
        files = os.listdir(self.SUMMARIES_DIR)
        md_files = [f for f in files if f.endswith('.md')]
        
        if not md_files:
            return f"Keine Markdown-Dateien im Verzeichnis '{self.SUMMARIES_DIR}' gefunden."
        
        return sorted(md_files)
    
    def read_summary(self, filename: str) -> str:
        """Liest den Inhalt einer Markdown-Datei aus dem summaries-Verzeichnis."""
        try:
            filename = self._validate_summary_filename(filename)
            self._ensure_summaries_dir()
            
            filepath = os.path.join(self.SUMMARIES_DIR, filename)
            
            if not os.path.exists(filepath):
                return f"FEHLER: Datei '{filename}' nicht gefunden. Nutze list_summaries, um verfügbare Dateien zu sehen."
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return f"Datei: {filename}\n\n{content}"
            
        except ValueError as e:
            return f"FEHLER: {e}"
        except Exception as e:
            return f"FEHLER beim Lesen von '{filename}': {type(e).__name__}: {e}"
    
    def write_summary(self, filename: str, content: str) -> str:
        """Erstellt oder überschreibt eine Markdown-Datei im summaries-Verzeichnis."""
        try:
            filename = self._validate_summary_filename(filename)
            self._ensure_summaries_dir()
            
            if not content or not content.strip():
                return "FEHLER: Inhalt darf nicht leer sein."
            
            filepath = os.path.join(self.SUMMARIES_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Summary erstellt: {filename}")
            return f"ERFOLG: Datei '{filename}' wurde erstellt im Verzeichnis '{self.SUMMARIES_DIR}'."
            
        except ValueError as e:
            return f"FEHLER: {e}"
        except Exception as e:
            logger.error(f"Fehler beim Schreiben von {filename}: {e}")
            return f"FEHLER beim Schreiben von '{filename}': {type(e).__name__}: {e}"
    
    def edit_summary(self, filename: str, content: str, mode: str = "append") -> str:
        """Bearbeitet eine existierende Markdown-Datei."""
        try:
            filename = self._validate_summary_filename(filename)
            self._ensure_summaries_dir()
            
            valid_modes = ["append", "prepend", "replace"]
            if mode not in valid_modes:
                return f"FEHLER: Ungültiger Modus '{mode}'. Gültige Modi: {', '.join(valid_modes)}"
            
            if not content or not content.strip():
                return "FEHLER: Inhalt darf nicht leer sein."
            
            filepath = os.path.join(self.SUMMARIES_DIR, filename)
            
            if mode == "replace":
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Summary ersetzt: {filename}")
                return f"ERFOLG: Datei '{filename}' wurde vollständig ersetzt."
            
            if not os.path.exists(filepath):
                return f"FEHLER: Datei '{filename}' existiert nicht. Nutze write_summary, um eine neue Datei zu erstellen."
            
            with open(filepath, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            
            if mode == "append":
                new_content = existing_content.rstrip() + "\n\n" + content.lstrip()
            elif mode == "prepend":
                new_content = content.rstrip() + "\n\n" + existing_content.lstrip()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            logger.info(f"Summary bearbeitet ({mode}): {filename}")
            return f"ERFOLG: Inhalt wurde {'angehängt' if mode == 'append' else 'vorangestellt'} an Datei '{filename}'."
            
        except ValueError as e:
            return f"FEHLER: {e}"
        except Exception as e:
            logger.error(f"Fehler beim Bearbeiten von {filename}: {e}")
            return f"FEHLER beim Bearbeiten von '{filename}': {type(e).__name__}: {e}"
    
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
        
        # List Summaries Tool
        list_summaries_tool = StructuredTool.from_function(
            func=self.list_summaries,
            name="list_summaries",
            description=LIST_SUMMARIES_DESCRIPTION,
            args_schema=ListSummariesInput,
        )
        
        # Read Summary Tool
        read_summary_tool = StructuredTool.from_function(
            func=self.read_summary,
            name="read_summary",
            description=READ_SUMMARY_DESCRIPTION,
            args_schema=ReadSummaryInput,
        )
        
        # Write Summary Tool
        write_summary_tool = StructuredTool.from_function(
            func=self.write_summary,
            name="write_summary",
            description=WRITE_SUMMARY_DESCRIPTION,
            args_schema=WriteSummaryInput,
        )
        
        # Edit Summary Tool
        edit_summary_tool = StructuredTool.from_function(
            func=self.edit_summary,
            name="edit_summary",
            description=EDIT_SUMMARY_DESCRIPTION,
            args_schema=EditSummaryInput,
        )
        
        return [
            document_search_tool,
            list_files_tool,
            preview_data_tool,
            run_pandas_tool,
            list_summaries_tool,
            read_summary_tool,
            write_summary_tool,
            edit_summary_tool,
        ]