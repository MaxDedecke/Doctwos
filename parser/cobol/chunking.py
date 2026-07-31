"""
parser/cobol/chunking.py
===========================
F-041: COBOL-bewusstes Chunking entlang Paragraph-/Section-Grenzen für den
RAG-Index — ein Chunk je Paragraph, mit zwei Ausnahmen:

- **Split bei Übergröße**: ein Paragraph, dessen Text `chunk_size` Zeichen
  überschreitet, wird zeilenweise (nie mitten in einer Zeile) in mehrere
  Chunks mit derselben Paragraph-Identität aufgeteilt (`meta["part"]`/
  `"parts"`, 1-basiert).
- **Merge bei Winzlingen**: aufeinanderfolgende Paragraphen unterhalb von
  `min_chunk_size` werden zu einem gemeinsamen Chunk zusammengefasst —
  begrenzt auf dieselbe Section, sonst würde eine Kette lauter kleiner
  Paragraphen über Section-Grenzen hinweg in einem Chunk landen (die
  Section-Grenze aus dem Feature-Titel).

Arbeitet auf den physischen Quellzeilen (nicht auf LogicalLines/Tokens) —
Chunk-Text ist für Embedding/Anzeige gedacht, nicht fürs weitere Parsen.
`Paragraph.start_line`/`end_line` sind laut divisions.py bereits physische
Zeilennummern (CLAUDE.md „Zeilennummern sind heilig").

Nur PROCEDURE-DIVISION-Paragraphen — DATA DIVISION/IDENTIFICATION DIVISION
kennen in COBOL keine Paragraphen und sind über ihre eigenen Entities
(DataItem, FileDescriptor) bereits strukturiert durchsuchbar, kein Chunking
nötig.
"""

from __future__ import annotations

from .model import Chunk, CobolProgram, Paragraph, SourceFormat

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_MIN_CHUNK_SIZE = 200


def chunk(
    program: CobolProgram,
    source_lines: list[str],
    source_format: SourceFormat,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    pending: list[Paragraph] = []

    def flush_pending() -> None:
        if not pending:
            return
        if len(pending) == 1:
            chunks.append(_paragraph_chunk(program, pending[0], source_lines, source_format))
        else:
            chunks.append(_merged_chunk(program, pending, source_lines, source_format))
        pending.clear()

    for paragraph in program.paragraphs:
        text = _text(paragraph.start_line, paragraph.end_line, source_lines)

        if len(text) > chunk_size:
            flush_pending()
            chunks.extend(_split_paragraph(program, paragraph, source_lines, source_format, chunk_size))
            continue

        if len(text) < min_chunk_size:
            if pending and pending[-1].section != paragraph.section:
                flush_pending()
            pending.append(paragraph)
            if _combined_len(pending, source_lines) >= min_chunk_size:
                flush_pending()
            continue

        flush_pending()
        chunks.append(_paragraph_chunk(program, paragraph, source_lines, source_format))

    flush_pending()
    return chunks


def _paragraph_chunk(program: CobolProgram, paragraph: Paragraph, source_lines: list[str], fmt: SourceFormat) -> Chunk:
    return Chunk(
        content=_text(paragraph.start_line, paragraph.end_line, source_lines),
        start_line=paragraph.start_line,
        end_line=paragraph.end_line,
        meta={
            "program": program.name,
            "section": paragraph.section,
            "paragraph": paragraph.name,
            "start_line": paragraph.start_line,
            "end_line": paragraph.end_line,
            "format": fmt,
        },
    )


def _merged_chunk(program: CobolProgram, paragraphs: list[Paragraph], source_lines: list[str], fmt: SourceFormat) -> Chunk:
    start_line = paragraphs[0].start_line
    end_line = paragraphs[-1].end_line
    content = "\n".join(_text(p.start_line, p.end_line, source_lines) for p in paragraphs)
    return Chunk(
        content=content,
        start_line=start_line,
        end_line=end_line,
        meta={
            "program": program.name,
            "section": paragraphs[0].section,
            "paragraphs": [p.name for p in paragraphs],
            "start_line": start_line,
            "end_line": end_line,
            "format": fmt,
        },
    )


def _split_paragraph(
    program: CobolProgram, paragraph: Paragraph, source_lines: list[str], fmt: SourceFormat, chunk_size: int
) -> list[Chunk]:
    lines = source_lines[paragraph.start_line - 1 : paragraph.end_line]
    n = len(lines)
    pieces: list[tuple[int, int, str]] = []
    i = 0
    while i < n:
        current: list[str] = []
        current_len = 0
        j = i
        while j < n:
            line = lines[j]
            if current_len > 0 and current_len + len(line) > chunk_size:
                break
            current.append(line)
            current_len += len(line) + 1
            j += 1
        if j == i:
            # eine einzelne Zeile ist bereits größer als chunk_size - trotzdem
            # aufnehmen statt in einer Endlosschleife hängen zu bleiben.
            current.append(lines[j])
            j += 1
        pieces.append((paragraph.start_line + i, paragraph.start_line + j - 1, "\n".join(current)))
        i = j

    total = len(pieces)
    result: list[Chunk] = []
    for idx, (start_line, end_line, text) in enumerate(pieces, start=1):
        result.append(
            Chunk(
                content=text,
                start_line=start_line,
                end_line=end_line,
                meta={
                    "program": program.name,
                    "section": paragraph.section,
                    "paragraph": paragraph.name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "format": fmt,
                    "part": idx,
                    "parts": total,
                },
            )
        )
    return result


def _text(start_line: int, end_line: int, source_lines: list[str]) -> str:
    return "\n".join(source_lines[start_line - 1 : end_line])


def _combined_len(paragraphs: list[Paragraph], source_lines: list[str]) -> int:
    return sum(len(_text(p.start_line, p.end_line, source_lines)) for p in paragraphs)
