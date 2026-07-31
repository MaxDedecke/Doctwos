#!/usr/bin/env python3
"""
scripts/loadtest_ingest_synthetic_corpus.py
==============================================
AP-9 (Härtung, NF-010 Lasttest): misst Persistenz- (Pass 1, cobol_persist.py)
und Nachauflösungsdurchsatz (Pass 2, tasks/edge_resolver.py) gegen eine echte
Postgres-Instanz, für den synthetischen Ersatzkorpus aus
scripts/generate_synthetic_cobol_corpus.py. Ergänzt die reine
In-Memory-Parserdurchsatzmessung (die braucht keine DB) um den Teil, der bei
einem echten Monorepo-Sync tatsächlich Zeit kostet: UPSERT je Entity
(inkl. Flush für die Eltern-ID-Auflösung, siehe cobol_persist.py-Kommentar)
und der globale CALL/COPY-Auflösungspass am Ende.

Schreibt absichtlich mit project_id=None, source_id=None (beide Spalten
sind nullable) — kein Fixture-Projekt/keine Wissensquelle nötig. Alle
erzeugten Zeilen tragen file_path mit Präfix "loadtest/", damit sie danach
gezielt und ausschließlich über diesen Präfix wieder gelöscht werden können
(--cleanup), unabhängig von sonstigem Inhalt der DB.

Läuft NICHT vom Host aus (DATABASE_URL zeigt auf den Hostnamen "db", nur im
Docker-Netz auflösbar, siehe docs/UMSETZUNGSSTAND.md). Aufruf:

    docker cp scripts/loadtest_ingest_synthetic_corpus.py doctus-parser:/app/
    docker cp loadtest/synthetic-corpus doctus-parser:/tmp/synthetic-corpus
    docker exec doctus-parser python /app/loadtest_ingest_synthetic_corpus.py /tmp/synthetic-corpus
    docker exec doctus-parser python /app/loadtest_ingest_synthetic_corpus.py --cleanup
"""

import argparse
import asyncio
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

from cobol.parse import parse_program, parse_copybook  # noqa: E402
from cobol_persist import persist_parse_result  # noqa: E402
from tasks.edge_resolver import resolve_global_edges  # noqa: E402
from db import SessionLocal  # noqa: E402
from models.database import CodeEntity, CodeEdge  # noqa: E402
from ollama_client import get_embeddings_batch  # noqa: E402


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:32]


def cleanup(db) -> None:
    n = db.query(CodeEntity).filter(CodeEntity.file_path.like("loadtest/%")).delete(synchronize_session=False)
    db.commit()
    print(f"Aufgeräumt: {n} loadtest/-Entities gelöscht (CASCADE nimmt die Kanten mit).")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", nargs="?", type=Path)
    ap.add_argument("--embed-sample", type=int, default=300, help="Anzahl Chunks für den Embedding-Durchsatz-Sample")
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    if args.cleanup:
        cleanup(db)
        db.close()
        return

    if args.corpus_dir is None:
        ap.error("corpus_dir ist erforderlich außer bei --cleanup")

    base = args.corpus_dir
    cpy_paths = sorted((base / "copybooks").glob("*.cpy"))
    pgm_paths = sorted((base / "programs").glob("*.cbl"))
    copybook_index = {p.stem: [str(p)] for p in cpy_paths}

    t_parse = 0.0
    t_persist = 0.0
    total_entities = total_edges = 0
    all_chunks: list[str] = []

    t0 = time.perf_counter()

    for p in cpy_paths:
        text = p.read_text()
        rel = f"loadtest/copybooks/{p.name}"
        tp0 = time.perf_counter()
        result = parse_copybook(text, rel)
        t_parse += time.perf_counter() - tp0
        tp1 = time.perf_counter()
        stats = persist_parse_result(
            db, project_id=None, source_id=None, file_path=rel,
            content_hash=content_hash(text), result=result,
        )
        t_persist += time.perf_counter() - tp1
        total_entities += stats["entities"]
        total_edges += stats["edges"]

    db.commit()
    print(f"Copybooks persistiert: {len(cpy_paths)}")

    for i, p in enumerate(pgm_paths, start=1):
        text = p.read_text()
        rel = f"loadtest/programs/{p.name}"
        tp0 = time.perf_counter()
        result = parse_program(text, rel, copybook_index)
        t_parse += time.perf_counter() - tp0
        tp1 = time.perf_counter()
        stats = persist_parse_result(
            db, project_id=None, source_id=None, file_path=rel,
            content_hash=content_hash(text), result=result,
        )
        t_persist += time.perf_counter() - tp1
        total_entities += stats["entities"]
        total_edges += stats["edges"]
        all_chunks.extend(c.content for c in result.chunks)

        if i % 200 == 0:
            db.commit()
            print(f"  {i}/{len(pgm_paths)} Programme committet...")

    db.commit()
    t_ingest = time.perf_counter() - t0
    print(f"Programme persistiert: {len(pgm_paths)}")
    print(f"Entities gesamt: {total_entities:,}, Kanten gesamt: {total_edges:,}")
    print(f"Parse-Zeit: {t_parse:.2f}s, Persistenz-Zeit (inkl. Flush): {t_persist:.2f}s, gesamt: {t_ingest:.2f}s")
    print(f"Durchsatz: {len(pgm_paths) / t_ingest:.1f} Programme/s (Parse+Persistenz)")

    # Pass 2: globale CALL/COPY-Auflösung (source_id=None wie beim Schreiben oben)
    unresolved_before = (
        db.query(CodeEdge)
        .filter(CodeEdge.source_id.is_(None), CodeEdge.resolution == "unresolved")
        .count()
    )
    t2 = time.perf_counter()
    resolved = resolve_global_edges(db, source_id=None)
    t_resolve = time.perf_counter() - t2
    db.commit()
    print(f"Pass 2 (globale Auflösung): {resolved}/{unresolved_before} Kanten aufgelöst in {t_resolve:.2f}s")

    # Embedding-Durchsatz-Sample — dominiert bei echten Beständen typischerweise
    # die Gesamtdauer stärker als Parsen/Persistieren (Netzwerk-Roundtrip zu Ollama).
    sample = all_chunks[: args.embed_sample]
    if sample:
        te0 = time.perf_counter()
        embeddings = await get_embeddings_batch(sample)
        t_embed = time.perf_counter() - te0
        print(
            f"Embedding-Sample: {len(sample)} Chunks in {t_embed:.2f}s "
            f"({len(sample) / t_embed:.1f} Chunks/s, {len(embeddings)} Vektoren erhalten)"
        )
        chunk_chars = sum(len(c) for c in sample)
        print(f"  Ø Chunk-Länge im Sample: {chunk_chars / len(sample):.0f} Zeichen")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
