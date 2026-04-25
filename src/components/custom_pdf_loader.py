"""
PDF Loader wrapper
"""
from typing import Iterator, Callable

from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader

from .preprocess_pdf import PreprocessPDF


class CustomPDFLoader(BaseLoader):
    """Wrapper Class for custom loader"""

    def __init__(self, file_path: str, model=None, progress_callback: Callable | None = None):
        self.file_path = file_path
        self.processor = PreprocessPDF(progress_callback=progress_callback)

    def lazy_load(self) -> Iterator[Document]:
        """Loading wrapper"""
        documents = self.processor.process_with_docling(self.file_path)
        for doc in documents:
            yield doc
