import re
from typing import Dict, List

# O-084: Default-Mindestgröße für einen Chunk, bevor er mit dem nächsten
# zusammengelegt wird. Bewusst derselbe Wert wie cobol/chunking.py
# DEFAULT_MIN_CHUNK_SIZE -- dieselbe Kategorie Problem (ein fast
# bedeutungsloser Winzling-Chunk landet einzeln im Vektorindex), hier nur
# ohne COBOL-spezifische Section-Grenze.
DEFAULT_MIN_CHUNK_SIZE = 200

_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]?\s")


class CodeParser:
    """
    Generic line-based text chunker used for all file types (code, documents,
    markdown). Historically dispatched to per-language AST parsers via
    `languages/`, but that layer never actually extracted anything in
    production (PARSER_REGISTRY was always empty, extract_references() always
    returned []) — see docs/TECH_DEBT_CLEANUP_PLAN.md §1. Only chunking, which
    was always language-agnostic, survives.
    """

    def __init__(self, language_name: str):
        self.language_name = language_name

    def chunk_file(
        self,
        content: str,
        chunk_size: int = 1000,
        overlap_size: int = 150,
        boundary_lines: frozenset[int] | None = None,
        min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
    ) -> List[Dict]:
        """
        Splits the file content into logical text chunks of a given maximum character size,
        with an overlap of characters to preserve context across boundaries.

        Args:
            content: The raw text content of the file.
            chunk_size: Target size in characters for each chunk.
            overlap_size: Target size in characters for chunk overlap.
            boundary_lines: O-083, optional. 1-based line numbers where a new
                chunk should preferably start (e.g. Confluence-Section-
                Überschriften, siehe connectors/base.py::_section_boundaries).
                Bricht den aktuellen Chunk ab, sobald so eine Zeile erreicht
                wird, auch wenn `chunk_size` noch nicht ausgeschöpft ist --
                `chunk_size` bleibt die harte Obergrenze, ist aber nicht mehr
                der einzige Auslöser. Kein Overlap über eine solche Grenze
                hinweg (sonst würde der neue Chunk mit Text der alten Section
                beginnen und die spätere section-Zuordnung über
                chunk["start_line"] verfälschen). Nur Aufrufer, die
                strukturierte Abschnittsgrenzen kennen, übergeben das -- ohne
                Angabe unverändertes rein zeichenzahl-basiertes Verhalten.
            min_chunk_size: O-084. Aufeinanderfolgende Chunks unterhalb dieser
                Größe werden zusammengelegt (analog zu cobol/chunking.py, aber
                ohne Section-Konzept -- nur `boundary_lines` begrenzt das
                Zusammenlegen, falls angegeben). Gilt für alle Aufrufer,
                nicht nur solche mit `boundary_lines`.

        Returns:
            A list of dictionaries containing:
                - 'content': The string content of the chunk.
                - 'start_line': The 1-based start line of the chunk in the original file.
                - 'end_line': The 1-based end line of the chunk in the original file.
        """
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks = []
        n = len(lines)
        i = 0
        boundaries = boundary_lines or frozenset()

        while i < n:
            current_chunk_lines = []
            current_len = 0
            start_line = i + 1
            cut_at_boundary = False

            j = i
            while j < n:
                line = lines[j]
                if current_len > 0 and (j + 1) in boundaries:
                    cut_at_boundary = True
                    break
                if current_len > 0 and current_len + len(line) > chunk_size:
                    break
                current_chunk_lines.append(line)
                current_len += len(line) + 1  # Include newline length approximation
                j += 1

            end_line = j

            # O-085: current_len==0 zwingt oben IMMER genau eine Zeile in den
            # Chunk (verhindert eine Endlosschleife) -- ist diese eine Zeile
            # selbst länger als chunk_size, entsteht sonst ein übergroßer
            # Chunk ohne weitere Aufteilung. An Wort-/Satzgrenzen aufteilen
            # statt unverändert zu übernehmen.
            if len(current_chunk_lines) == 1 and len(current_chunk_lines[0]) > chunk_size:
                for piece in _split_oversized_line(current_chunk_lines[0], chunk_size):
                    chunks.append(
                        {"content": piece, "start_line": start_line, "end_line": end_line}
                    )
            else:
                chunks.append(
                    {
                        "content": "\n".join(current_chunk_lines),
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                )

            if j == n:
                break

            if cut_at_boundary:
                i = j
                continue

            # Compute overlap to find next starting index
            overlap_len = 0
            next_start = j
            while next_start > i:
                line_len = len(lines[next_start - 1]) + 1
                if overlap_len + line_len > overlap_size:
                    break
                overlap_len += line_len
                next_start -= 1

            # Prevent infinite loops if progress is blocked
            if next_start == i:
                i = j
            else:
                i = next_start

        return _merge_small_chunks(chunks, min_chunk_size, boundaries)


def _merge_small_chunks(
    chunks: List[Dict], min_chunk_size: int, boundaries: frozenset[int]
) -> List[Dict]:
    """O-084: legt aufeinanderfolgende Chunks unterhalb von `min_chunk_size`
    zu einem gemeinsamen Chunk zusammen -- analog zu cobol/chunking.py::chunk()s
    Pending-Merge-Logik, aber ohne Section-Objekt: `boundaries` (dieselben
    1-basierten Zeilennummern wie `boundary_lines`) begrenzt das Zusammenlegen
    stattdessen, damit O-083s Section-Trennung nicht wieder verwischt wird.
    Ohne `boundaries` (die meisten Aufrufer) wird fortlaufend gemergt, bis die
    Mindestgröße erreicht ist -- wie bei COBOL, nur ohne Grenzkonzept."""
    merged: List[Dict] = []
    pending: List[Dict] = []

    def flush() -> None:
        if not pending:
            return
        if len(pending) == 1:
            merged.append(pending[0])
        else:
            merged.append(
                {
                    "content": "\n".join(c["content"] for c in pending),
                    "start_line": pending[0]["start_line"],
                    "end_line": pending[-1]["end_line"],
                }
            )
        pending.clear()

    for chunk in chunks:
        if len(chunk["content"]) < min_chunk_size:
            if pending and chunk["start_line"] in boundaries:
                flush()
            pending.append(chunk)
            if sum(len(c["content"]) for c in pending) >= min_chunk_size:
                flush()
            continue
        flush()
        merged.append(chunk)

    flush()
    return merged


def _split_oversized_line(line: str, chunk_size: int) -> List[str]:
    """O-085: eine einzelne Zeile über `chunk_size` wird an Satz- oder
    Wortgrenzen in mehrere Teile zerlegt, statt unverändert einen einzigen
    übergroßen Chunk zu bilden. Passiert bei Confluence z. B., wenn
    `_html_to_text()` einen langen `<p>`-Absatz ohne internes `<br/>` in eine
    einzige durchgehende Zeile umwandelt. Bevorzugt die letzte Satzgrenze
    innerhalb des Limits, fällt sonst auf die letzte Wortgrenze zurück; ein
    einzelnes token ohne jedes Leerzeichen über `chunk_size` (z. B. eine sehr
    lange URL) wird hart nach Zeichen geschnitten, um zu terminieren."""
    if len(line) <= chunk_size:
        return [line]

    pieces: List[str] = []
    remaining = line
    while len(remaining) > chunk_size:
        cut = _find_cut_point(remaining, chunk_size)
        pieces.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _find_cut_point(text: str, limit: int) -> int:
    window = text[: limit + 1]

    last_sentence_end = None
    for match in _SENTENCE_END_RE.finditer(window):
        if match.end() <= limit:
            last_sentence_end = match.end()
    if last_sentence_end:
        return last_sentence_end

    last_space = window.rfind(" ", 0, limit)
    if last_space > 0:
        return last_space + 1

    # Kein Leerzeichen im gesamten Limit-Fenster (z. B. eine sehr lange URL
    # ohne Leerzeichen) -- hart schneiden, sonst würde die Schleife nie
    # vorankommen.
    return limit
