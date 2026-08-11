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
PDF-spezifisches Preprocessing via Docling.

Nutzt DocumentConverter mit Tesseract-OCR (CLI) und TableFormer
(do_table_structure=True) fuer saubere Tabellenextraktion. Bilder werden
ueber generate_picture_images=True als PIL-Bilder zur Verfuegung gestellt
und in Lesereihenfolge via VisionLLM beschrieben.
"""

# Third party
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

# Custom imports
from app.components.preprocess_base import PreprocessBase


class PreprocessPDF(PreprocessBase):
    """PDF-Preprocessing mit Docling (Layout, Tabellen, OCR, Bilder)."""

    def _build_converter(self) -> DocumentConverter:
        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=True,
            generate_picture_images=True,
            images_scale=2,
            ocr_options=TesseractCliOcrOptions(lang=["deu", "eng"]),
        )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def process_document(self, file_path: str) -> list:
        """Verarbeitet die PDF und gibt eine Liste von LangChain-Dokumenten zurueck."""
        converter = self._build_converter()
        result = converter.convert(file_path)
        doc = result.document
        return self.build_chunks_from_docling(doc, file_path)
