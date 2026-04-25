"""
Custom PDF preprocessing using Docling with Tesseract OCR,
TableFormer table structure extraction, and picture description.
"""

import os
import logging
from typing import Callable

from langchain_core.documents import Document

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractOcrOptions,
    PictureDescriptionApiOptions,
    AcceleratorOptions,
    AcceleratorDevice,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker import HybridChunker
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


class PreprocessPDF:

    def __init__(self, progress_callback: Callable | None = None):
        """
        Initialisiert die Docling-basierte PDF-Preprocess-Pipeline.

        Args:
            progress_callback: Optionaler Callback für Fortschritts-Events.
        """
        self.progress_callback = progress_callback

        vision_baseurl = os.getenv("VISION_BASEURL", "")
        vision_api_key = os.getenv("VISION_API_KEY", "")
        api_key = os.getenv("API_KEY", "loc-123")

        tessdata_path = os.getenv("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/5/tessdata")
        if not os.path.exists(tessdata_path):
            tessdata_path = "/usr/share/tesseract-ocr/4.00/tessdata"
        if not os.path.exists(tessdata_path):
            tessdata_path = "/usr/share/tessdata"

        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice.CPU,
            num_threads=4,
        )
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = TesseractOcrOptions(
            lang=["deu"],
            path=tessdata_path,
        )
        pipeline_options.do_table_structure = True

        if vision_baseurl:
            pipeline_options.do_picture_description = True
            pipeline_options.enable_remote_services = True

            headers = {}
            auth_token = vision_api_key or api_key
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            pipeline_options.picture_description_options = PictureDescriptionApiOptions(
                url=vision_baseurl,
                params={
                    "model": os.getenv("VISION_MODEL", ""),
                    "max_completion_tokens": 200,
                },
                prompt=(
                    "Beschreibe das Bild auf Deutsch. "
                    "Fasse die wesentlichen Inhalte, Objekte und den Kontext prägnant zusammen."
                ),
                timeout=90,
                headers=headers,
            )
        else:
            pipeline_options.do_picture_description = False

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.tokenizer = AutoTokenizer.from_pretrained(embedding_model)
        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=512,
            merge_peers=True,
        )

    def _emit(self, event: dict):
        if self.progress_callback:
            try:
                self.progress_callback(event)
            except Exception:
                pass

    def process_with_docling(self, file_path: str) -> list:
        """
        Verarbeitet eine PDF mit Docling und gibt eine Liste von
        LangChain Document-Objekten zurück.
        """
        filename = os.path.basename(file_path)
        self._emit({"stage": "parsing", "file": filename, "chunks": 0})

        result = self.converter.convert(file_path)
        doc = result.document

        chunks = []
        for chunk in self.chunker.chunk(doc):
            chunks.append(
                Document(
                    page_content=chunk.text,
                    metadata={
                        "source": file_path,
                        "filename": filename,
                        "type": "pdf_chunk",
                    },
                )
            )

        self._emit({"stage": "parsing", "file": filename, "chunks": len(chunks)})
        logger.info(f"Docling: {filename} → {len(chunks)} Chunks")
        return chunks
