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
PDF Loader wrapper
"""

# Standard library
from typing import Iterator

# Third party
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader

# Custom imports
from . import PreprocessPDF


class CustomPDFLoader(BaseLoader):
    """Wrapper Class for custom loader"""

    def __init__(self, file_path: str, model=None):
        self.file_path = file_path
        self.processor = PreprocessPDF(model=model)

    def lazy_load(self) -> Iterator[Document]:
        """Loading wrapper"""

        # Documents from unstructured process
        documents = self.processor.process_with_unstructured(self.file_path)

        for doc in documents:
            # Yield the docs
            yield doc
