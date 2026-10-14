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
Startwerte der Prompts fuer Bildbeschreibung und Kontext-Anreicherung.

Zur Laufzeit gelten die Werte aus der Datenbank (Tabelle ``settings``, Admin-Seite
"Einlesen & Modelle"). Diese Texte sind nur der Samen fuer frische Datenbanken
(``DatabaseService._init_settings``) und die letzte Rueckfallebene, falls ein Wert fehlt.
Alembic-Migration 0018 traegt ihre eigene Kopie.
"""

from textwrap import dedent

VISION_PROMPT = dedent(
    """\
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
).strip()

# Platzhalter: {dokument} (Auszug aus dem Gesamtdokument), {abschnitt} (der zu verortende Chunk)
CONTEXT_PROMPT = (
    "Du bist ein Dokumenten-Indexierer. "
    "Gib NUR 1-2 kurze Sätze zurück, die den Abschnitt im Gesamtdokument verorten.\n\n"
    "### Gesamtdokument (Auszug):\n{dokument}\n\n"
    "### Abschnitt:\n{abschnitt}\n\n"
    "### Kontext-Einordnung:"
)

CONTEXT_EXCERPT_CHARS = 2000

# Zweiter Durchgang fuer Tabellen aus PDFs (Bild der Tabelle + Docling-Entwurf)
TABLES_PROMPT = (
    "Du liest eine Tabelle aus einem Dokument. Das Bild zeigt die Tabelle, darunter steht ein automatisch "
    "erzeugter Entwurf, der Fehler enthalten kann (verschobene Spalten, vertauschte oder fehlende Zellen).\n\n"
    "Gib die Tabelle so aus, wie sie im Bild steht, als Markdown-Tabelle:\n"
    "- Eine Kopfzeile, dann die Trennzeile, dann alle Datenzeilen. Keine Zeile weglassen, keine erfinden.\n"
    "- Zellen wörtlich übernehmen, auch Zahlen, Einheiten, Währungszeichen und Schreibweisen (kein Umrechnen, kein Runden).\n"
    "- Verbundene Zellen in jede Zeile oder Spalte wiederholen, die sie überspannen. Mehrzeilige Zellen in einer Zelle zusammenfassen.\n"
    "- Leere Zellen bleiben leer. Hat die Tabelle mehrere Kopfzeilen, verbinde sie zu einer Kopfzeile (z. B. „Umsatz Q1“).\n"
    "- Ein senkrechter Strich in einer Zelle wird als \\| geschrieben.\n\n"
    "Gib ausschließlich die Markdown-Tabelle aus, ohne Einleitung und ohne Erklärung."
)

# Bilder, die im Chat angehaengt werden (Foto, Screenshot, Scan): Text daraus wird durchsuchbar
IMAGES_PROMPT = (
    "Du erschließt ein Bild, das ein Nutzer in einen Chat hochgeladen hat, damit sein Inhalt per Textsuche "
    "gefunden und beantwortet werden kann.\n\n"
    "Gib in dieser Reihenfolge aus:\n"
    "1. Eine Zeile, was das Bild ist (z. B. Foto, Screenshot, Scan eines Briefs, Diagramm, Tabelle).\n"
    "2. Alle lesbaren Texte wörtlich und vollständig, in Leserichtung (Zahlen, Einheiten und Schreibweisen unverändert). "
    "Unleserliches als [unleserlich] markieren, nichts ergänzen.\n"
    "3. Tabellen als Markdown-Tabelle, Diagramme und Abläufe als kurze Sätze (Wenn-Dann, Beteiligte, Werte).\n"
    "4. Bei Fotos ohne Text: eine sachliche Beschreibung dessen, was zu sehen ist.\n\n"
    "Erfinde nichts, was nicht im Bild steht. Antworte ausschließlich auf Deutsch und gib nur das Ergebnis aus, "
    "ohne Einleitung."
)

TABLES_MAX_ROW_DEVIATION = 30  # Prozent Abweichung der Zeilenzahl vom Entwurf, ab der die Antwort verworfen wird
