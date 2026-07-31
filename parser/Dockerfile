FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    tesseract-ocr \
    tesseract-ocr-deu \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The parser worker environment.
# Copier standard files.

COPY . .

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
