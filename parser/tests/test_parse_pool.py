import glob
import os

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
