"""Zitate einer Agentenantwort mit dem Quelltext abgleichen, wenn die Recherche die Stelle nicht selbst gelesen hat.

Die Quellenprüfung (`chat_sources.validate_answer_sources`) lässt nur Zitate gelten, die ein Werkzeug in diesem
Durchgang geliefert hat. Das schützt davor, eine Nachbardatei als Beleg auszugeben, hatte aber zwei Folgen
(Katalogtest 08.11.2026):

- Eine existierende, passende Stelle, die das Modell nur nicht ausdrücklich gelesen hatte, galt als „nicht belegt“.
- Ein erfundener Pfad blieb im Text stehen und wurde nur markiert.

Hier wird eine nicht abgerufene Fundstelle im Worktree nachgeschlagen. Sie wird verlinkt, wenn die zitierte Zeile
mit ihrer Umgebung zum zitierenden Satz passt (ein dort genannter Bezeichner kommt vor, oder der Satz nennt die
Datei selbst). Ein Pfad, den es nicht gibt, wird auf die eine Datei mit gleichem Paketpfad korrigiert oder aus dem
Text entfernt. Für Beziehungsaussagen ohne Index-Kante wird geprüft, ob der zitierte Quelltext sie zeigt: Dann ist
sie im Quelltext belegt, aber nicht als Kante im Index, und wird für Leser so unterschieden.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Callable, Optional

from services import agent_repo_tools as repo_tools
from services.chat_sources import (
    _BACKTICK_RE,
    _FENCE_RE,
    _FILE_LINE_RE,
    _IDENTIFIER_RE,
    extract_tool_edge_pairs,
    extract_tool_sources,
    record_agent_source,
    tool_evidence_text,
    validate_answer_sources,
)

logger = logging.getLogger(__name__)

WINDOW = 8
# Für Beziehungsaussagen: Das Modell zitiert oft den Methodenanfang, der Aufruf steht einige Zeilen tiefer.
CLAIM_WINDOW = 15
_WORD_RE = re.compile(r"[A-Za-z_][\w-]{3,}")


class SourceReader:
    """Lesender Zugriff auf den Worktree einer Git-Quelle."""

    def __init__(self, repository_id: int):
        self.repository_id = repository_id

    def available(self) -> bool:
        return os.path.isdir(repo_tools.get_repo_path(self.repository_id))

    def window(self, path: str, line: int, radius: int = WINDOW) -> Optional[str]:
        """Zeilen um ``line``; None, wenn Datei oder Zeile nicht existieren."""
        result = repo_tools.view_repo_file(
            self.repository_id, path, max(1, line - radius), line + radius
        )
        if result.get("error") or not 1 <= line <= result.get("total_lines", 0):
            return None
        return result.get("content", "")

    def same_package(self, path: str) -> list[str]:
        """Dateien mit gleichem Namen, deren Pfad auf dieselben letzten Verzeichnisse endet (mindestens zwei).

        Ein Zitat nur mit Dateinamen (`Foo.java:12`) passt auf alle gleichnamigen Dateien."""
        parts = path.replace("\\", "/").strip("/").split("/")
        if len(parts) == 1:
            return repo_tools.find_repo_files(self.repository_id, parts[0])
        if len(parts) < 3:
            return []
        candidates = repo_tools.find_repo_files(self.repository_id, parts[-1])
        best, best_depth = [], 2
        for candidate in candidates:
            depth = _common_suffix(candidate.split("/"), parts)
            if depth > best_depth:
                best, best_depth = [candidate], depth
            elif depth == best_depth and depth > 2:
                best.append(candidate)
        return best


def _common_suffix(a: list[str], b: list[str]) -> int:
    count = 0
    while count < min(len(a), len(b)) and a[-1 - count].lower() == b[-1 - count].lower():
        count += 1
    return count


def _identifiers(text: str) -> set[str]:
    """Bezeichner eines Satzes, in ihre Namensteile zerlegt (`userDAO.securityChecks` -> userdao, securitychecks)."""
    names: set[str] = set()
    for raw in _BACKTICK_RE.findall(text):
        if not _FILE_LINE_RE.match(raw.strip()):
            names.update(_WORD_RE.findall(raw))
    names.update(_IDENTIFIER_RE.findall(_BACKTICK_RE.sub(" ", text)))
    parts: set[str] = set()
    for name in names:
        parts.update(piece for piece in re.split(r"[.#:/()]+", name) if len(piece) >= 4)
    return {part.casefold() for part in parts}


def _covered(path: str, line: int, sources: list[dict]) -> Optional[str]:
    """Pfad der Quelle, die die Zeile belegt (ein bloßer Dateiname passt auf ihre Datei), sonst None."""
    key = path.replace("\\", "/").lstrip("./").lower()
    for source in sources:
        file = str(source.get("file") or "").replace("\\", "/").lstrip("./")
        lines = source.get("lines") or []
        lowered = file.lower()
        if len(lines) >= 2 and (lowered == key or ("/" not in key and lowered.endswith("/" + key))):
            if min(lines[0], lines[1]) <= line <= max(lines[0], lines[1]):
                return file
    return None


def _fits(window: str, sentence: str, path: str) -> bool:
    text = window.casefold()
    stem = os.path.splitext(os.path.basename(path))[0].casefold()
    names = _identifiers(sentence)
    return stem in names or any(name in text for name in names - {stem})


def reconcile_citations(
    answer: str, sources: list[dict], reader: SourceReader, source_id: Optional[int]
) -> str:
    """Verlinkt passende, nicht abgerufene Fundstellen, korrigiert oder entfernt Pfade, die es nicht gibt.

    Bleibt danach kein belegtes Zitat übrig, kommt die Antwort unverändert zurück: Eine Antwort ohne jeden Beleg
    verwirft die Quellenprüfung als Ganzes, sie darf durch das Entfernen nicht stimmig erscheinen."""
    original = answer
    scan = _FENCE_RE.sub(" ", answer)
    lines = scan.splitlines()
    removed: list[str] = []
    for raw in dict.fromkeys(_BACKTICK_RE.findall(scan)):
        match = _FILE_LINE_RE.match(raw.strip())
        if not match:
            continue
        path, line = match.group(1).replace("\\", "/").lstrip("./"), int(match.group(2))
        if _covered(path, line, sources):
            continue
        sentence = " ".join(text for text in lines if f"`{raw}`" in text)
        window = reader.window(path, line)
        if window is not None:
            if _fits(window, sentence, path):
                record_agent_source(sources, path, line, line, source_id)
            continue
        candidates = [c for c in reader.same_package(path) if reader.window(c, line) is not None]
        if len(candidates) == 1 and _fits(reader.window(candidates[0], line), sentence, path):
            if "/" in path:
                fixed = f"{candidates[0]}:{line}"
                logger.info("Korrigiere Zitatpfad %s -> %s", raw, fixed)
                answer = answer.replace(f"`{raw}`", f"`{fixed}`")
            record_agent_source(sources, candidates[0], line, line, source_id)
            continue
        if len(candidates) > 1:
            continue  # mehrdeutiger Dateiname: nicht raten, die Quellenprüfung markiert ihn
        # Den Pfad gibt es im Repository nicht: nicht als Fundstelle stehen lassen.
        name = os.path.basename(path)
        logger.warning("Entferne erfundenen Zitatpfad %s", raw)
        answer = answer.replace(f"`{raw}`", f"{name} (Fundstelle im Repository nicht gefunden)")
        removed.append(name)
    if removed and not any(
        (match := _FILE_LINE_RE.match(raw.strip()))
        and _covered(match.group(1), int(match.group(2)), sources)
        for raw in _BACKTICK_RE.findall(_FENCE_RE.sub(" ", answer))
    ):
        return original
    if removed:
        answer = (
            answer.rstrip()
            + "\n\n> Hinweis: Für "
            + ", ".join(dict.fromkeys(removed))
            + " nannte die Antwort einen Pfad, den es im Repository nicht gibt; er wurde entfernt."
        )
    return answer


def claim_in_cited_source(
    answer: str, claim: str, sources: list[dict], reader: SourceReader
) -> bool:
    """Zeigt eine im selben Absatz zitierte, belegte Stelle alle Bezeichner der Beziehungsaussage?"""
    names = _identifiers(claim)
    if not names:
        return False
    for paragraph in answer.split("\n"):
        if claim not in paragraph:
            continue
        for raw in _BACKTICK_RE.findall(paragraph):
            match = _FILE_LINE_RE.match(raw.strip())
            if not match:
                continue
            path = _covered(match.group(1), int(match.group(2)), sources)
            if path is None:
                continue
            window = reader.window(path, int(match.group(2)), CLAIM_WINDOW)
            if window is None:
                continue
            found = sum(1 for name in names if name in window.casefold())
            # Der Aufrufer steht oft weiter oben als die Aufrufstelle; zwei Namen genügen.
            if found >= min(2, len(names)):
                return True
    return False


class ToolEvidence:
    """Was die Werkzeuge eines Agentenlaufs belegt haben: gelesene Stellen und Kanten.

    ``observe`` nimmt jedes Werkzeugereignis entgegen; ``validate`` prüft die fertige Antwort gegen diese Belege und,
    wo eine Git-Quelle vorliegt, gegen deren Quelltext.
    """

    def __init__(self, repository_id: Optional[int]):
        self.repository_id = repository_id
        self.sources: list[dict] = []
        self.edge_pairs: set[tuple[str, str]] = set()

    def observe(self, event: dict) -> None:
        extract_tool_sources(event, self.sources, self.repository_id)
        self.edge_pairs.update(extract_tool_edge_pairs(event))

    def validate(self, answer: str, agent_steps: list, question: str) -> tuple[str, bool]:
        reader = SourceReader(self.repository_id) if self.repository_id else None
        if reader is not None and not reader.available():
            reader = None
        source_supported: Optional[Callable[[str], bool]] = None
        if reader is not None:
            answer = reconcile_citations(answer, self.sources, reader, self.repository_id)

            def source_supported(claim: str) -> bool:
                return claim_in_cited_source(answer, claim, self.sources, reader)

        return validate_answer_sources(
            answer,
            self.sources,
            self.edge_pairs,
            evidence_text=tool_evidence_text(agent_steps, question) if agent_steps else None,
            source_supported=source_supported,
        )
