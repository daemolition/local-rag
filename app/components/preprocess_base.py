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
Gemeinsame Basisklasse für Dokumenten-Preprocessing (PDF, DOCX, etc.).

Stellt die geteilte Logik bereit:
  - Bild-Deduplikation via perceptual Hash (imagehash)
  - VisionLLM-Aufrufe mit Retry/Backoff
  - Base64-Encodierung
  - Chunk-Building (Element → LangChain Document, [BILD-BESCHREIBUNG: ...])
  - Verzeichnis-Cleanup (Docker-Mountpoint-sicher)
"""

# Standard library
import os
import base64
import shutil
import time
import logging

# Third party
from langchain_core.documents import Document
from PIL import Image
import imagehash

# Custom imports
from app.llm.local_llm import VisionLLM


def _clear_dir(path: str) -> None:
    """Leert den Inhalt eines Verzeichnisses, ohne das Verzeichnis selbst zu
    loeschen. Notwendig, weil ./images (./data/images) in Docker unter dem
    /app/data-Mountpoint liegt und shutil.rmtree() auf einem Mountpoint mit
    [Errno 16] Device or resource busy fehlschlaegt. Legt das Verzeichnis an,
    falls es nicht existiert."""
    os.makedirs(path, exist_ok=True)
    for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path) and not os.path.islink(entry_path):
            shutil.rmtree(entry_path)
        else:
            try:
                os.remove(entry_path)
            except IsADirectoryError:
                shutil.rmtree(entry_path)


logger = logging.getLogger(__name__)


class PreprocessBase:
    """Basis-Klasse für Dokumenten-Preprocessing.

    Subklassen (PreprocessPDF, PreprocessDOCX) implementieren
    process_with_unstructured(file_path) und rufen self.build_chunks()
    mit den unstructured-Elementen auf.
    """

    def __init__(
        self, model: VisionLLM = None, max_retries: int = 3, retry_delay: float = 2.0
    ):
        self.model = model or VisionLLM()
        self.duplicate_images: set = set()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # ---- Bild-Hilfsfunktionen (formatunabhängig) ----

    def find_duplicate_images(self, images_dir: str, threshold: int = 5) -> set:
        """Findet ähnliche Bilder basierend auf phash (perceptual hash)."""
        hashes = {}
        duplicates = set()

        if not os.path.exists(images_dir):
            return duplicates

        image_files = sorted(
            [
                f
                for f in os.listdir(images_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
            ]
        )

        for img_file in image_files:
            img_path = os.path.join(images_dir, img_file)
            try:
                img = Image.open(img_path)
                h = imagehash.phash(img)

                for existing_path, existing_hash in hashes.items():
                    if h - existing_hash < threshold:
                        duplicates.add(img_path)
                        break
                else:
                    hashes[img_path] = h
            except Exception:
                continue

        return duplicates

    def process_image_with_retry(
        self,
        b64image: str,
        image_path: str,
        current_image: int,
        unique_image_count: int,
    ) -> dict:
        """Verarbeitet ein Bild mit Retry-Logik für LLM-Timeouts."""
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

    def encode_image(self, image_path: str) -> str:
        """Helferfunktion zum Encodieren des Bildes in Base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8").replace("\n", "")

    # ---- Chunk-Building (formatunabhängig) ----

    def build_chunks(
        self, elements: list, file_path: str, image_map: dict | None = None
    ) -> list[Document]:
        """Baut LangChain-Dokumente aus unstructured-Elementen.

        Args:
            elements: Liste von unstructured-Elementen (aus partition_*).
            file_path: Pfad zur Quelldatei.
            image_map: Optionales Mapping {element_index: image_description}.
                       Falls gesetzt, werden Bildbeschreibungen an der Position
                       des entsprechenden Elements in den Textfluss eingebettet
                       (für DOCX, wo Bilder via XML-Position ermittelt wurden).
                       Falls None, werden Image-Elemente mit image_path-Metadata
                       verarbeitet (PDF-Pfad).

        Returns:
            Liste von LangChain Document-Objekten.
        """
        images_dir = "./data/images"
        filename = os.path.basename(file_path)

        # Duplikate nur via image_path-Metadata verarbeiten (PDF-Pfad)
        if image_map is None:
            self.duplicate_images = self.find_duplicate_images(images_dir)
        else:
            self.duplicate_images = set()

        # Anzahl einzigartiger Bilder (für Progress-Anzeige)
        if image_map is None:
            unique_image_count = sum(
                1
                for el in elements
                if el.category == "Image"
                and getattr(el.metadata, "image_path", None)
                and os.path.exists(getattr(el.metadata, "image_path", None))
                and getattr(el.metadata, "image_path", None)
                not in self.duplicate_images
            )
        else:
            unique_image_count = len(image_map)

        current_image = 0

        chunks: list[Document] = []
        current_chunk: dict = {"title": filename, "content": [], "metadata": {}}

        def create_langchain_doc(chunk_dict: dict) -> Document:
            text_parts = []
            for item in chunk_dict["content"]:
                if isinstance(item, dict) and "image" in item:
                    text_parts.append(f"[BILD-BESCHREIBUNG: {item['image']}]")
                else:
                    text_parts.append(str(item))

            return Document(
                page_content="\n".join(text_parts),
                metadata={
                    "source": file_path,
                    "filename": filename,
                    "title": chunk_dict.get("title", "kein Titel"),
                    "type": "document_chunk",
                    **chunk_dict.get("metadata", {}),
                },
            )

        for idx, el in enumerate(elements):
            # Bild aus image_map (DOCX-Pfad: Position über XML ermittelt)
            if image_map is not None and idx in image_map:
                current_image += 1
                print(
                    f"Verarbeite Bild {current_image}/{unique_image_count}", flush=True
                )
                current_chunk["content"].append({"image": image_map[idx]})
                continue

            if el.category == "Title":
                if current_chunk["content"]:
                    chunks.append(create_langchain_doc(current_chunk))
                current_chunk = {
                    "title": el.text,
                    "content": [],
                    "metadata": el.metadata.to_dict(),
                }
            elif el.category == "Image":
                image_path = getattr(el.metadata, "image_path", None)
                if image_path and os.path.exists(image_path):
                    if image_path in self.duplicate_images:
                        continue
                    current_image += 1
                    print(
                        f"Verarbeite Bild {current_image}/{unique_image_count}",
                        flush=True,
                    )
                    b64image = self.encode_image(image_path)
                    result = self.process_image_with_retry(
                        b64image, image_path, current_image, unique_image_count
                    )
                    if "image" in result:
                        current_chunk["content"].append({"image": result["image"]})
                    elif "error" in result:
                        logger.error(f"Bild übersprungen: {result['error']}")
            else:
                if el.text.strip():
                    current_chunk["content"].append(el.text)

        if current_chunk["content"]:
            chunks.append(create_langchain_doc(current_chunk))

        return chunks
