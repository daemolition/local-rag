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

"""Gemeinsamer Rueckgabetyp der Dokument-Loader: ein Document mit dem ganzen Markdown."""

import os

from langchain_core.documents import Document


def markdown_document(markdown: str, file_path: str) -> Document:
    return Document(
        page_content=markdown,
        metadata={
            "source": file_path,
            "filename": os.path.basename(file_path),
            "type": "document",
        },
    )
