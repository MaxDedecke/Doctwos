FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

WORKDIR /app

# Build tools only exist in this stage (O-167); they don't end up in the
# runtime image below.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# git/tesseract/poppler are used at runtime (Git-Connector per Subprozess,
# OCR-Pfad) und bleiben deshalb in dieser Stage - anders als build-essential/
# libpq-dev, die nur die Builder-Stage braucht.
RUN apt-get update && apt-get install -y \
    git \
    tesseract-ocr \
    tesseract-ocr-deu \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Nur der fuer den Betrieb noetige Code (O-167): kein tests/, kein
# requirements-dev.txt, keine Build-Werkzeuge im fertigen Image.
COPY chunk_reindex.py cobol_persist.py code_parser.py db.py git_utils.py \
     healthcheck_beat.py ollama_client.py utils.py worker.py ./
COPY cobol/ cobol/
COPY connectors/ connectors/
COPY core/ core/
COPY models/ models/
COPY tasks/ tasks/

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
