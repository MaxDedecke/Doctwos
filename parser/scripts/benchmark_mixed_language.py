"""Run a local, model-free parser coverage pass over a mixed-language tree.

This measures source classification, parser outcomes, diagnostics, parser-emitted
relationship types/resolution statuses, file sizes, and elapsed time. It does not
build the repository, call an embedding/chat endpoint, or claim retrieval quality.

Example::

    PYTHONPATH=parser .venv-parser/bin/python \
      parser/scripts/benchmark_mixed_language.py /path/to/checkout \
      --revision <git-commit>
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from core.language_detection import detect_language
from core.model import classify_completeness
from core.registry import STRUCTURE_PARSERS
from core.source_decoder import SourceDecodeError, decode_source


LANGUAGES = ("java", "xslt", "xml", "jsp", "shell")
SKIP_DIRS = {".git", "target", "build", "dist", "node_modules", "vendor"}


def source_paths(root: Path):
    for current, dirs, filenames in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.is_symlink() or not path.is_file():
                continue
            yield path.relative_to(root).as_posix(), path


def run(root: Path, revision: str) -> dict:
    counts: Counter = Counter()
    bytes_by_language: Counter = Counter()
    status_counts: Counter = Counter()
    diagnostic_counts: Counter = Counter()
    edge_counts: Counter = Counter()
    elapsed_by_language: Counter = Counter()
    largest_file_bytes = 0
    total_start = time.perf_counter()

    for relative, path in source_paths(root):
        language = detect_language(relative)
        raw = None
        if language not in LANGUAGES:
            if path.suffix:
                continue
            try:
                with path.open("rb") as source_file:
                    raw = source_file.read(4096)
            except OSError:
                continue
            language = detect_language(relative, content=raw)
            if language not in LANGUAGES:
                continue
        try:
            if raw is None or len(raw) == 4096:
                raw = path.read_bytes()
        except OSError:
            continue
        counts[(language, "detected")] += 1
        bytes_by_language[language] += len(raw)
        largest_file_bytes = max(largest_file_bytes, len(raw))
        start = time.perf_counter()
        try:
            source, _encoding = decode_source(raw)
        except SourceDecodeError:
            status_counts[(language, "decode_error")] += 1
            elapsed_by_language[language] += time.perf_counter() - start
            continue
        try:
            result = STRUCTURE_PARSERS[language].parse(source, relative)
            status, _reasons = classify_completeness(result)
            status_counts[(language, status)] += 1
            for diagnostic in result.diagnostics:
                diagnostic_counts[(language, diagnostic.severity)] += 1
            for edge in result.edges:
                edge_counts[(language, edge.type, edge.resolution)] += 1
        except Exception:
            status_counts[(language, "exception")] += 1
        finally:
            elapsed_by_language[language] += time.perf_counter() - start

    languages = {}
    for language in LANGUAGES:
        detected = counts[(language, "detected")]
        languages[language] = {
            "files": detected,
            "source_bytes": bytes_by_language[language],
            "parse_outcomes": {
                status: count
                for (item_language, status), count in sorted(status_counts.items())
                if item_language == language
            },
            "diagnostics": {
                severity: count
                for (item_language, severity), count in sorted(diagnostic_counts.items())
                if item_language == language
            },
            "relationships": {
                f"{edge_type}:{resolution}": count
                for (item_language, edge_type, resolution), count in sorted(edge_counts.items())
                if item_language == language
            },
            "parse_seconds": round(elapsed_by_language[language], 3),
        }

    return {
        "dataset_revision": revision,
        "parser_versions": {
            language: STRUCTURE_PARSERS[language].parser_version for language in LANGUAGES
        },
        "languages": languages,
        "largest_file_bytes": largest_file_bytes,
        "parse_wall_seconds": round(time.perf_counter() - total_start, 3),
        "limits": [
            "Model-free static parsing only; no build, embedding, retrieval, or chat request.",
            "Elapsed time is local to this host and is not a production capacity result.",
            "Text decoding uses the configured default UTF-8 without customer-specific fallbacks.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="repository checkout or source snapshot")
    parser.add_argument("--revision", required=True, help="immutable dataset revision or snapshot id")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"source root is not a directory: {root}")
    print(json.dumps(run(root, args.revision), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
