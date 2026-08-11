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
DOCX/DOC/ODT-spezifisches Preprocessing via Docling.

Frueher wurde DOCX per python-docx + ZIP-Bildextraktion verarbeitet, damit
Bilder an der richtigen Textfluss-Position landen. Docling loest das ueber
die einheitliche DoclingDocument-Repraesentation: doc.iterate_items()
 liefert Text, Tabellen und Bilder in Lesereihenfolge. Damit entfaellt der
komplette python-docx-Sonderweg.

DOCX/DOC nutzen den Word-Backend (WordFormatOption), ODT den ODT-Backend
(OdtFormatOption). Tabellen kommen direkt aus dem Dokumentmodell (kein
TableFormer noetig).
"""

# Standard library
import os

from docling.datamodel.base_models import InputFormat

# Third party
from docling.document_converter import (
    DocumentConverter,
    OdtFormatOption,
    WordFormatOption,
)

# Custom imports
from app.components.preprocess_base import PreprocessBase


class PreprocessDOCX(PreprocessBase):
    """DOCX/DOC/ODT-Preprocessing mit Docling."""

    def _format_option_for(self, file_path: str):
        """Waehlt Backend anhand der Endung (.odt -> ODT-Backend, sonst Word)."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".odt":
            return InputFormat.ODT, OdtFormatOption()
        # .docx und .doc nutzen beide den Word-Backend (.doc best-effort).
        return InputFormat.DOCX, WordFormatOption()

    def process_document(self, file_path: str) -> list:
        """Verarbeitet DOCX/DOC/ODT und gibt LangChain-Dokumente zurueck."""
        input_format, format_option = self._format_option_for(file_path)
        converter = DocumentConverter(format_options={input_format: format_option})
        result = converter.convert(file_path)
        return self.build_chunks_from_docling(result.document, file_path)
