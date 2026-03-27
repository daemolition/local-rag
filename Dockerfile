FROM python:3.12-slim-bookworm

LABEL maintainer="local-document-rag"
LABEL architecture="arm64"

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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --upgrade pip setuptools wheel \
    && pip install uv \
    && uv pip install --system unstructured[pdf] \
    && uv pip install --system imagehash pillow \
    && uv pip install --system --no-dev -e .

COPY . .

RUN mkdir -p /app/files /app/processed_files /app/summaries /app/local_qdrant.db /app/images

EXPOSE 5000

CMD ["python", "run.py"]