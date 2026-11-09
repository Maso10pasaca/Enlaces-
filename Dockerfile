FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    CT2_INTER_THREADS=1 \
    CT2_INTRA_THREADS=1 \
    HF_HOME=/tmp/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY server.py .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/huggingface \
    && chown -R appuser:appuser /app /tmp/huggingface
USER appuser

EXPOSE 8000
CMD ["python", "server.py"]
