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
Gemeinsame Basisklasse fuer Dokumenten-Preprocessing (PDF, DOCX, etc.).

Verarbeitung erfolgt einheitlich ueber Docling (DoclingDocument). Diese
Basis stellt bereit:
  - ChunkBuilder: Titel-zu-Titel-Chunking, Tabellen = eigener Chunk,
    gleiche Metadata-Shape wie bisher (source/filename/title/type).
  - build_chunks_from_docling(): iteriert doc.iterate_items() in
    Lesereihenfolge (SECTION_HEADER -> neuer Abschnitt, TableItem -> HTML,
    PictureItem -> VisionLLM-Beschreibung, TextItem -> Text).
  - Bild-Deduplikation via perceptual Hash (imagehash).
  - VisionLLM-Aufrufe mit Retry/Backoff.
"""

# Standard library
import base64
import logging
import os
import time
from io import BytesIO

import imagehash
from docling_core.types.doc import PictureItem, TableItem, TextItem

# Third party
from langchain_core.documents import Document

# Custom imports
from app.llm.local_llm import VisionLLM

logger = logging.getLogger(__name__)


def _pil_to_b64(pil_image) -> str:
    """Encodiert ein PIL-Bild in Base64 (PNG)."""
    buf = BytesIO()
    pil_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8").replace("\n", "")


def _get_picture_image(picture):
    """Liefert das PIL-Bild eines Docling PictureItem oder None.

    Benoetigt PdfPipelineOptions(generate_picture_images=True), damit
    picture.image gesetzt ist.
    """
    img_ref = getattr(picture, "image", None)
    if img_ref is None:
        return None
    try:
        return img_ref.pil_image
    except Exception:
        return None


class ChunkBuilder:
    """Akkumulator fuer Titel-zu-Titel-Chunking.

    Erzeugt LangChain-Dokumente mit der festen Metadata-Shape
    (source/filename/title/type='document_chunk' + optionale zusaetzliche
    Metadata pro Abschnitt). Tabellen werden als eigener Chunk ausgegeben
    (Flush vorher und nachher) und erben den Titel des aktuellen Abschnitts.
    Bildbeschreibungen werden als [BILD-BESCHREIBUNG: ...]-Marker eingebettet.
    Der Titel bleibt ueber Flushes hinweg erhalten (nur content wird
    zurueckgesetzt) — genauso wie die bisherige DOCX-Implementierung.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.chunks: list[Document] = []
        self.title = self.filename
        self.metadata: dict = {}
        self.content: list = []

    def _doc(self) -> Document:
        text_parts = []
        for item in self.content:
            if isinstance(item, dict) and "image" in item:
                text_parts.append(f"[BILD-BESCHREIBUNG: {item['image']}]")
            else:
                text_parts.append(str(item))
        return Document(
            page_content="\n".join(text_parts),
            metadata={
                "source": self.file_path,
                "filename": self.filename,
                "title": self.title,
                "type": "document_chunk",
                **self.metadata,
            },
        )

    def _flush(self):
        if self.content:
            self.chunks.append(self._doc())
        self.content = []

    def start_section(self, title: str, metadata: dict | None = None) -> None:
        """Schliesst den laufenden Chunk ab und beginnt einen neuen Abschnitt."""
        self._flush()
        self.title = title
        self.metadata = metadata or {}

    def add_text(self, text: str) -> None:
        if text and text.strip():
            self.content.append(text)

    def add_image(self, description: str) -> None:
        self.content.append({"image": description})

    def add_table(self, rendered_text: str) -> None:
        """Tabelle als eigener Chunk (erbt den aktuellen Abschnittstitel)."""
        self._flush()
        self.content.append(rendered_text)
        self._flush()

    def finish(self) -> list[Document]:
        self._flush()
        return self.chunks


class PreprocessBase:
    """Basis-Klasse fuer Dokumenten-Preprocessing via Docling.

    Subklassen (PreprocessPDF, PreprocessDOCX) implementieren
    process_document(file_path) und rufen self.build_chunks_from_docling()
    mit dem konvertierten DoclingDocument auf.
    """

    def __init__(
        self, model: VisionLLM = None, max_retries: int = 3, retry_delay: float = 2.0
    ):
        self.model = model or VisionLLM()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # ---- Bild-Hilfsfunktionen (formatunabhaengig) ----

    def process_image_with_retry(
        self,
        b64image: str,
        image_path: str,
        current_image: int,
        unique_image_count: int,
    ) -> dict:
        """Verarbeitet ein Bild mit Retry-Logik fuer LLM-Timeouts."""
        message = self.model.generate_image_message(b64image)

        retry_count = 0
        last_error = None

        while retry_count < self.max_retries:
            try:
                description = self.model.generate(message)
                desc_text = (
                    description.content
                    if hasattr(description, "content")
                    else str(description)
                )
                return {"image": desc_text}
            except Exception as e:
                retry_count += 1
                last_error = e
                logger.warning(
                    f"Bild {current_image}/{unique_image_count} - "
                    f"Versuch {retry_count}/{self.max_retries} fehlgeschlagen: {str(e)[:100]}"
                )
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay * retry_count)

        logger.error(
            f"Bild {current_image}/{unique_image_count} - "
            f"Alle {self.max_retries} Versuche fehlgeschlagen: {image_path}"
        )
        return {
            "error": f"LLM-Error nach {self.max_retries} Versuchen: {str(last_error)[:100]}"
        }

    def _collect_unique_pictures(self, doc) -> dict:
        """Pre-Pass: sammelt einzigartige Bilder (phash-Dedup).

        Returns:
            {picture_self_ref: PIL.Image} fuer die erste Vorkommen jedes
            einzigartigen Bildes (in Lesereihenfolge).
        """
        unique_pil: dict = {}
        seen_hashes = []
        for pic in doc.pictures:
            pil = _get_picture_image(pic)
            if pil is None:
                continue
            try:
                h = imagehash.phash(pil)
            except Exception:
                continue
            if any(h - sh < 5 for sh in seen_hashes):
                continue
            seen_hashes.append(h)
            unique_pil[pic.self_ref] = pil
        return unique_pil

    # ---- Chunk-Building (formatunabhaengig, Docling-basiert) ----

    def build_chunks_from_docling(self, doc, file_path: str) -> list[Document]:
        """Baut LangChain-Dokumente aus einem DoclingDocument.

        Iteriert doc.iterate_items() in Lesereihenfolge:
          - SECTION_HEADER / TITLE  -> neuer Abschnitt (Titel-zu-Titel-Split)
          - TableItem               -> HTML im eigenen Chunk (Spans erhalten)
          - PictureItem             -> VisionLLM-Beschreibung (mit Dedup)
          - sonstiges TextItem      -> Text im aktuellen Abschnitt

        Args:
            doc: DoclingDocument (aus DocumentConverter.convert().document).
            file_path: Pfad zur Quelldatei.

        Returns:
            Liste von LangChain Document-Objekten.
        """
        builder = ChunkBuilder(file_path)

        unique_pil = self._collect_unique_pictures(doc)
        unique_image_count = len(unique_pil)
        current_image = 0

        for item, _level in doc.iterate_items():
            if isinstance(item, TableItem):
                try:
                    html = item.export_to_html(doc=doc)
                except TypeError:
                    html = item.export_to_html()
                if html and html.strip():
                    builder.add_table(html)
            elif isinstance(item, PictureItem):
                pil = unique_pil.get(item.self_ref)
                if pil is None:
                    continue  # Duplikat oder ohne Bild
                current_image += 1
                print(
                    f"Verarbeite Bild {current_image}/{unique_image_count}", flush=True
                )
                b64image = _pil_to_b64(pil)
                result = self.process_image_with_retry(
                    b64image,
                    f"<docling_picture:{item.self_ref}>",
                    current_image,
                    unique_image_count,
                )
                if "image" in result:
                    builder.add_image(result["image"])
                elif "error" in result:
                    logger.error(f"Bild übersprungen: {result['error']}")
            elif isinstance(item, TextItem):
                label_name = item.label.name if hasattr(item, "label") else ""
                if label_name in ("SECTION_HEADER", "TITLE") and item.text.strip():
                    builder.start_section(item.text.strip())
                else:
                    builder.add_text(item.text)

        return builder.finish()
