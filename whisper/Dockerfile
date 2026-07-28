FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY server.py ./

# Modell zur Build-Zeit auf CPU/int8 vorladen, damit die Gewichte im
# Huggingface-Cache-Layer landen und der Containerstart nicht auf einen
# Download wartet. Buildumgebungen haben i.d.R. keine GPU - device/compute_type
# hier sind nur fuers Herunterladen relevant, die Laufzeit laedt dieselben
# gecachten Gewichte spaeter mit device=cuda/compute_type=float16 (WHISPER_DEVICE/
# WHISPER_COMPUTE_TYPE env). Wenn WHISPER_MODEL geaendert wird, mit
# --build-arg WHISPER_MODEL=... neu bauen, damit der Cache zum Runtime-Modell passt.
ARG WHISPER_MODEL=large-v3-turbo
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

EXPOSE 9000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9000"]
