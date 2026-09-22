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

# Development-only test image. The source tree and tests are mounted by the
# parser-test service in docker-compose.dev.yml; production keeps using the
# runtime stage below and therefore does not contain pytest or test sources.
FROM builder AS dev

RUN apt-get update && apt-get install -y git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt .
RUN pip install --no-cache-dir --user -r requirements-dev.txt
ENV PATH=/root/.local/bin:$PATH

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
COPY chunk_reindex.py structure_persist.py code_parser.py db.py git_utils.py \
     healthcheck_beat.py insight_review.py link_dirty.py ollama_client.py utils.py worker.py ./
COPY cobol/ cobol/
COPY java/ java/
COPY maven/ maven/
COPY markup/ markup/
COPY xslt/ xslt/
COPY shell/ shell/
COPY connectors/ connectors/
COPY core/ core/
COPY models/ models/
COPY tasks/ tasks/

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
