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
PDF-spezifisches Preprocessing.

Nutzt partition_pdf mit Bildextraktion (extract_images_in_pdf=True) und
delegiert Chunk-Building + VisionLLM-Verarbeitung an PreprocessBase.
"""

# Third party
from unstructured.partition.pdf import partition_pdf

# Custom imports
from app.components.preprocess_base import PreprocessBase, _clear_dir


class PreprocessPDF(PreprocessBase):
    """PDF-Preprocessing mit unstructured partition_pdf + Bildextraktion."""

    def process_with_unstructured(self, file_path: str) -> list:
        """Verarbeitet die PDF und gibt eine Liste von LangChain-Dokumenten zurück."""

        images_dir = "./data/images"

        _clear_dir(images_dir)

        elements = partition_pdf(
            filename=file_path,
            strategy="hi_res",
            languages=["deu"],
            extract_images_in_pdf=True,
            extract_image_block_output_dir=images_dir,
            infer_table_structure=False,
            pdf_image_dpi=150
        )

        chunks = self.build_chunks(elements, file_path, image_map=None)

        _clear_dir(images_dir)

        return chunks