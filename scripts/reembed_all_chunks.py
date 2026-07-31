#!/usr/bin/env python3
"""
scripts/reembed_all_chunks.py
==============================
Recomputes DocumentChunk.embedding for every row using the currently
configured EMBED_MODEL. Needed once after a schema/embedding-model
migration (e.g. nomic-embed-text -> bge-m3, see
backend/alembic/versions/b1c2d3e4f5a6_bge_m3_embedding_dims.py) that
nulls out existing embeddings because the vector dimensions changed.

Usage (inside the doctus-parser container, which has EMBED_MODEL/DATABASE_URL/
OLLAMA_BASE_URL wired up and models/database.py + ollama_client.py on path):
    docker exec doctus-parser python /app/reembed_all_chunks.py
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from core import config
from db import SessionLocal
from models.database import DocumentChunk
from ollama_client import get_embedding


async def main():
    db = SessionLocal()
    try:
        chunks = db.query(DocumentChunk).all()
        total = len(chunks)
        print(f"Berechne Embeddings für {total} Chunks mit Modell '{config.EMBED_MODEL}'...")
        for i, chunk in enumerate(chunks, start=1):
            chunk.embedding = await get_embedding(chunk.content, model=config.EMBED_MODEL)
            if i % 10 == 0 or i == total:
                print(f"  {i}/{total}")
        db.commit()
        print("Fertig — alle Embeddings neu berechnet und gespeichert.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
