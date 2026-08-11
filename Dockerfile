FROM python:3.12-slim-bookworm

LABEL maintainer="local-document-rag"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-deu \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv via pip (system-wide, direkt verfügbar)
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies system-wide (no .venv!)
RUN uv pip install --system -e .

# Embedding- + Sparse-Modell zur Build-Zeit in den Cache laden,
# damit der Containerstart nicht auf einen Download wartet (Start-Timeout-Fix).
# Verwendet FastEmbed (ONNX) statt HuggingFace/Torch — schnellerer Start,
# kein PyTorch-Overhead. Wenn EMBEDDING_MODEL geaendert wird, mit
# --build-arg EMBEDDING_MODEL=... neu bauen, damit der Name mit dem
# runtime EMBEDDING_MODEL (DB/Env) uebereinstimmt.
# Hinweis: fastembed erwartet den HF-Org-Prefix (z. B. sentence-transformers/...).
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from langchain_community.embeddings import FastEmbedEmbeddings; \
      FastEmbedEmbeddings(model_name='${EMBEDDING_MODEL}')" \
 && python -c "from langchain_qdrant import FastEmbedSparse; \
      FastEmbedSparse(model_name='Qdrant/bm25')"

# Docling-Modelle (Layout/DocLayNet + TableFormer) zur Build-Zeit in den
# HF-Cache laden, damit der Containerstart nicht auf einen Download wartet.
# Docling lädt die Gewichte erst beim convert(), nicht beim Instanziieren —
# deshalb wird hier eine Minimal-PDF (via Pillow, bereits Dep) erzeugt und
# konvertiert. torch läuft CPU-only (siehe pyproject.toml [tool.uv.sources]).
# OCR erfolgt über die Tesseract-CLI (apt-Packages oben).
RUN python -c "\
from PIL import Image; \
Image.new('RGB',(100,100),'white').save('/tmp/_warm.pdf'); \
from docling.document_converter import DocumentConverter, PdfFormatOption; \
from docling.datamodel.base_models import InputFormat; \
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions; \
conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=PdfPipelineOptions(do_ocr=True, do_table_structure=True, ocr_options=TesseractCliOcrOptions(lang=['deu','eng'])))}); \
conv.convert('/tmp/_warm.pdf'); \
import os; os.remove('/tmp/_warm.pdf')"


# Standalone Tailwind-CLI v3 (kein Node noetig) in einem separaten, cachebaren
# Layer laden. Ersetzt den render-blockierenden Play-CDN durch self-hosted CSS.
RUN curl -sL -o /usr/local/bin/tailwindcss \
      https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
 && chmod +x /usr/local/bin/tailwindcss

# Copy rest of application
COPY . .

# Vorkompiliertes Tailwind-CSS erzeugen: scannt Templates/JS und schreibt
# app/static/css/tailwind.css. Laeuft bei jedem Build, damit die CSS zu den
# Templates synchron bleibt (Binary aus dem Cache-Layer oben wird reused).
# Danach Binary entfernen, um das Runtime-Image klein zu halten.
RUN tailwindcss -i ./app/static/css/tailwind.input.css \
               -o ./app/static/css/tailwind.css --minify \
 && rm -f /usr/local/bin/tailwindcss

# Create directories. Die Daten-Subdirs (files/processed_files/images/
# summaries) legt ensure_directories zur Laufzeit unter /app/data an (das
# app-data-Volume ueberlagert /app/data leer).
RUN mkdir -p /app/data

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "run_linux.py"]
