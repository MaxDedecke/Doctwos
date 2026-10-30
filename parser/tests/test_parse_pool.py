import asyncio
import glob
import os
import signal
from unittest.mock import patch

import pytest

from connectors.git import GitConnector
from core.registry import STRUCTURE_PARSERS
import parse_pool

_CORPUS = os.path.join(os.path.dirname(__file__), "cobol_corpus")


def _sample() -> tuple[str, str]:
    paths = sorted(glob.glob(os.path.join(_CORPUS, "**", "*.cbl"), recursive=True))
    assert paths, "kein COBOL-Beispiel im Korpus"
    with open(paths[0], encoding="utf-8", errors="replace") as f:
        return f.read(), os.path.basename(paths[0])


def test_pool_result_matches_in_process_parse():
    text, path = _sample()
    expected = STRUCTURE_PARSERS["cobol"].parse(text, path, prepared_source=None)
    pool = parse_pool.create_pool(2, {})
    try:
        actual = pool.submit(parse_pool._parse_in_worker, "cobol", text, path, None).result(
            timeout=120
        )
    finally:
        pool.shutdown(wait=True)
    assert [(e.type, e.name, e.start_line, e.end_line) for e in actual.entities] == [
        (e.type, e.name, e.start_line, e.end_line) for e in expected.entities
    ]
    assert len(actual.chunks) == len(expected.chunks)


_GOOD_COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. GOOD{n}.
       PROCEDURE DIVISION.
           STOP RUN.
"""


def _parse_or_die(lang, text, path, profile):
    """Steht für eine Giftdatei: Der Prozess stirbt wie beim Speicher-Kill des Kernels."""
    if "POISON" in text:
        os.kill(os.getpid(), signal.SIGKILL)
    return STRUCTURE_PARSERS[lang].parse(text, path, prepared_source=None)


def _doc(name, content):
    return {
        "title": name,
        "content": content,
        "url": f"file:///{name}",
        "source_type": "Git",
        "storage_key": name,
        "extra_meta": {"language": "cobol"},
    }


@pytest.mark.anyio
async def test_a_file_that_kills_its_parse_process_only_costs_that_file():
    connector = GitConnector(source_id=-1)
    connector._parse_workers = 2

    async def embeddings(texts, model=None):
        return [[0.1] * 1024 for _ in texts]

    poison = _doc("POISON.cbl", "      * POISON\n" + _GOOD_COBOL.format(n=0))
    good = [_doc(f"GOOD{n}.cbl", _GOOD_COBOL.format(n=n)) for n in (1, 2, 3)]
    semaphore = asyncio.Semaphore(4)
    try:
        with (
            patch("connectors.git.parse_pool._parse_in_worker", _parse_or_die),
            patch("connectors.git.get_embeddings_batch", side_effect=embeddings),
            patch("connectors.git.get_embedding_input_budget", return_value=8100),
        ):
            results = await asyncio.gather(
                *(connector._embed_document(doc, semaphore) for doc in [poison, *good])
            )
            # Der Pool ist danach wieder da, statt alles Weitere im Hauptprozess zu parsen.
            after = await connector._embed_document(
                _doc("GOOD4.cbl", _GOOD_COBOL.format(n=4)), semaphore
            )
    finally:
        if connector._parse_pool is not None:
            connector._parse_pool.shutdown(wait=False)

    doc, chunks, parse_result = results[0]
    assert parse_result is None
    assert doc["extra_meta"]["parse_status"] == "partial"
    assert "POISON" in "".join(chunk["content"] for chunk in chunks)
    assert all(result[2] is not None for result in results[1:])
    assert after[2] is not None
    assert connector._parse_workers == 2 and connector._parse_pool is not None
