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