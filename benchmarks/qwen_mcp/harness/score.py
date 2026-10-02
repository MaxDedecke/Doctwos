"""Deterministischer Rubrik-Scorer (kein LLM-Richter) plus Pruefung der Zitierbelege."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CITATION_RX = re.compile(
    r"(?P<file>[A-Za-z0-9_./\\-]+\.(?:cbl|cpy|cob|jcl|java|xml|properties|json|yml|yaml|sql))"
    r"(?:\s*(?:[:#]|,?\s*(?:Zeilen?|lines?|Z\.|L\.)\s*)\s*(?P<a>\d{1,5})(?:\s*[-–]\s*(?P<b>\d{1,5}))?)?",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", ""))


def item_hit(item: dict, answer: str) -> bool:
    return all(any(re.search(alt, answer, re.IGNORECASE) for alt in group) for group in item["all"])


@lru_cache(maxsize=None)
def corpus_index(corpus: str) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for f in (ROOT / corpus).rglob("*"):
        if f.is_file():
            index.setdefault(f.name.lower(), []).append(f)
    return index


@lru_cache(maxsize=None)
def line_count(path: Path) -> int:
    return len(path.read_text(errors="replace").splitlines())


def citation_check(answer: str, corpus: str) -> dict:
    """Je Dateizitat: existiert die Datei im gepinnten Checkout, und liegt eine genannte Zeile in der Datei?"""
    index = corpus_index(corpus)
    seen: set[tuple] = set()
    total = valid_file = with_line = valid_line = 0
    for m in CITATION_RX.finditer(answer):
        name = Path(m.group("file").replace("\\", "/")).name.lower()
        key = (name, m.group("a"), m.group("b"))
        if key in seen:
            continue
        seen.add(key)
        total += 1
        paths = index.get(name)
        if not paths:
            continue
        valid_file += 1
        if m.group("a"):
            with_line += 1
            end = int(m.group("b") or m.group("a"))
            if any(int(m.group("a")) >= 1 and end <= line_count(p) for p in paths):
                valid_line += 1
    return {
        "cite_n": total,
        "cite_file_valid": valid_file,
        "cite_line_n": with_line,
        "cite_line_valid": valid_line,
        "cite_file_rate": (valid_file / total) if total else None,
        "cite_line_rate": (valid_line / with_line) if with_line else None,
    }


def score_session(task: dict, project: dict, answer: str, threshold: float) -> dict:
    text = norm(answer)
    total = sum(i["weight"] for i in task["items"])
    got = {i["id"]: item_hit(i, text) for i in task["items"]}
    earned = sum(i["weight"] for i in task["items"] if got[i["id"]])
    pen = sum(p["weight"] for p in task.get("penalties", []) if re.search(p["regex"], text, re.IGNORECASE))
    rubric = max(0.0, earned - pen) / total
    out = {"rubric": round(rubric, 4), "items": got, "usable": rubric >= threshold}
    out.update(citation_check(answer, project["corpus"]))
    return out
