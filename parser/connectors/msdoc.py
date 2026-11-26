"""
parser/connectors/msdoc.py
==========================
Text aus dem binären Word-Format (.doc, Word 6/95 und Word 97–2003) ohne externe Konverter.

Eine .doc ist ein OLE-Container (``olefile``, BSD-2). Der Text steckt im Strom ``WordDocument``; welche Bytes zu
welcher Textposition gehören, steht in der Stückliste (CLX/PlcPcd).

- Word 97–2003: Stückliste im Tabellenstrom (``0Table`` oder ``1Table``); jedes Stück ist komprimiert (8 Bit,
  Windows-1252) oder UTF-16.
- Word 6/95: Stückliste im Strom ``WordDocument`` selbst und nur bei schnell gespeicherten Dateien; sonst liegt der
  Text am Stück ab ``fcMin``. Immer 8 Bit in der ANSI-Codepage des Dokuments (aus den Dokumenteigenschaften).

Gelesen werden Haupttext, Fuß- und Endnoten sowie Textfelder. Bewusst nicht unterstützt (mit klarer Meldung): Word 2.0 und ältere,
asiatische Word-95-Varianten, verschlüsselte Dokumente und beschädigte Dateien.
Grundlage: [MS-DOC] 2.5 (FIB) und 2.8.35 (Clx/PlcPcd); Word-6-FIB wie in antiword/wvWare dokumentiert.
"""

import codecs
import re
import struct

from connectors.office import UnsupportedFormat

_WORD_MAGIC = 0xA5EC
_WORD6_MAGIC = 0xA5DC  # Word 6.0 und Word 95 (nFib 101 bzw. 104)

# Teilbereiche des Textstroms in Dateireihenfolge (ccpText … ccpHdrTxbx). Titel None: wird nicht übernommen
# (Kopf-/Fußzeilen wiederholen sich je Seite, Makro- und Kommentartext sind kein Dokumentinhalt).
_STORIES = (
    ("text", ""),
    ("footnotes", "Fußnoten"),
    ("headers", None),
    ("macros", None),
    ("comments", None),
    ("endnotes", "Endnoten"),
    ("textboxes", "Textfelder"),
    ("header_textboxes", None),
)
_MAX_CHARS = 50_000_000

_FIELD_BEGIN, _FIELD_SEP, _FIELD_END = "\x13", "\x14", "\x15"


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _piece_table(clx: bytes) -> tuple[tuple[int, ...], list[int]] | None:
    """Textpositionen (n+1) und Dateipositionen (n) der Stücke aus einem CLX; None, wenn keine Stückliste da ist."""
    pos = 0
    while pos < len(clx) and clx[pos] == 0x01:  # Prc: Formatierungen überspringen
        pos += 3 + _u16(clx, pos + 1)
    if pos >= len(clx) or clx[pos] != 0x02:
        return None
    plc_len = _u32(clx, pos + 1)
    plc = clx[pos + 5 : pos + 5 + plc_len]
    pieces = (plc_len - 4) // 12  # n+1 Positionen (4 Byte) + n Stücke (8 Byte)
    positions = struct.unpack_from(f"<{pieces + 1}I", plc, 0)
    fcs = [_u32(plc, (pieces + 1) * 4 + index * 8 + 2) for index in range(pieces)]
    return positions, fcs


def _read_pieces(word: bytes, table: bytes) -> tuple[str, list[int]]:
    """Word 97–2003: Gesamttext über die Stückliste und die Längen der Teilbereiche (siehe ``_STORIES``)."""
    csw = _u16(word, 0x20)
    cslw_offset = 0x22 + csw * 2
    cslw = _u16(word, cslw_offset)
    lw_start = cslw_offset + 2
    ccps = [_u32(word, lw_start + (3 + index) * 4) for index in range(len(_STORIES))]
    fc_lcb_offset = lw_start + cslw * 4
    clx_pair = fc_lcb_offset + 2 + 33 * 8  # fcClx/lcbClx: Paar Nr. 33 der FibRgFcLcb97
    fc_clx, lcb_clx = _u32(word, clx_pair), _u32(word, clx_pair + 4)
    table_pieces = _piece_table(table[fc_clx : fc_clx + lcb_clx])
    if table_pieces is None:
        raise UnsupportedFormat(
            "Die Textstruktur der .doc-Datei ist nicht lesbar. Bitte in Word als .docx speichern."
        )
    positions, fcs = table_pieces

    wanted = min(sum(ccps), _MAX_CHARS)
    parts: list[str] = []
    taken = 0
    for index, fc in enumerate(fcs):
        if taken >= wanted:
            break
        length = min(positions[index + 1] - positions[index], wanted - taken)
        if fc & 0x40000000:  # komprimiert: 8 Bit, Windows-1252
            start = (fc & 0x3FFFFFFF) // 2
            parts.append(word[start : start + length].decode("cp1252", errors="replace"))
        else:
            parts.append(word[fc : fc + length * 2].decode("utf-16-le", errors="replace"))
        taken += length
    return "".join(parts), ccps


def _read_word6(word: bytes, codec: str) -> tuple[str, list[int]]:
    """Word 6/95: Text am Stück ab fcMin oder, bei schnell gespeicherten Dateien, über die Stückliste."""
    fc_min = _u32(word, 0x18)
    ccps = [_u32(word, 0x34 + index * 4) for index in range(len(_STORIES))]
    fc_clx, lcb_clx = _u32(word, 0x160), _u32(word, 0x164)
    wanted = min(sum(ccps), _MAX_CHARS)
    pieces = _piece_table(word[fc_clx : fc_clx + lcb_clx]) if lcb_clx else None
    if pieces is None:
        return word[fc_min : fc_min + wanted].decode(codec, errors="replace"), ccps
    positions, fcs = pieces
    parts: list[str] = []
    taken = 0
    for index, fc in enumerate(fcs):
        if taken >= wanted:
            break
        length = min(positions[index + 1] - positions[index], wanted - taken)
        parts.append(word[fc : fc + length].decode(codec, errors="replace"))
        taken += length
    return "".join(parts), ccps


def _ansi_codec(ole) -> str:
    """ANSI-Codepage aus den Dokumenteigenschaften; Konverter tragen dort oft UTF-8 (65001) ein, das gilt nicht."""
    try:
        codepage = ole.get_metadata().codepage
    except Exception:
        codepage = None
    if isinstance(codepage, int) and (874 <= codepage <= 1258):
        try:
            return codecs.lookup(f"cp{codepage}").name
        except LookupError:
            pass
    return "cp1252"


def _strip_fields(text: str) -> str:
    """Feldfunktionen (``\\x13 CODE \\x14 ERGEBNIS \\x15``) auf das Ergebnis reduzieren."""
    if _FIELD_BEGIN not in text:
        return text
    out: list[str] = []
    stack: list[bool] = []  # True: wir sind im Code-Teil (verwerfen), False: im Ergebnis (behalten)
    for char in text:
        if char == _FIELD_BEGIN:
            stack.append(True)
        elif char == _FIELD_SEP and stack:
            stack[-1] = False
        elif char == _FIELD_END:
            if stack:
                stack.pop()
        elif not any(stack):  # nicht innerhalb des Code-Teils eines (auch äußeren) Feldes
            out.append(char)
    return "".join(out)


def _clean(text: str) -> str:
    text = _strip_fields(text)
    text = text.replace("\x07\x07", "\n").replace("\x07", " | ")
    text = text.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n\n")
    text = text.replace("\x1e", "-").replace("\x1f", "")
    text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)
    lines = [re.sub(r"\s*\|\s*$", "", line).rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_doc_text(file_path: str) -> str:
    """Klartext einer .doc-Datei (Absätze als Zeilen, Tabellenzellen mit " | ")."""
    import olefile

    if not olefile.isOleFile(file_path):
        raise UnsupportedFormat(
            "Die Datei ist kein Word-97–2003-Dokument. Bitte in Word als .docx speichern."
        )
    try:
        with olefile.OleFileIO(file_path) as ole:
            if not ole.exists("WordDocument"):
                raise UnsupportedFormat(
                    "Die OLE-Datei enthält kein Word-Dokument. Bitte in Word als .docx speichern."
                )
            word = ole.openstream("WordDocument").read()
            magic = _u16(word, 0) if len(word) >= 2 else 0
            if magic not in (_WORD_MAGIC, _WORD6_MAGIC) or len(word) < 0x1A8:
                raise UnsupportedFormat(
                    "Beschädigte oder unbekannte .doc-Datei. Bitte in Word als .docx speichern."
                )
            n_fib = _u16(word, 2)
            flags = _u16(word, 0x0A)
            if flags & 0x0100:
                raise UnsupportedFormat(
                    "Das Word-Dokument ist passwortgeschützt und kann nicht gelesen werden."
                )
            if (magic == _WORD6_MAGIC) != (n_fib in (0x0065, 0x0068)) or (
                magic == _WORD_MAGIC and n_fib < 0x00C1
            ):
                raise UnsupportedFormat(
                    "Diese Word-Version (.doc) wird nicht unterstützt. Bitte in Word als .docx speichern."
                )
            if magic == _WORD6_MAGIC:
                text, ccps = _read_word6(word, _ansi_codec(ole))
            else:
                table_name = "1Table" if flags & 0x0200 else "0Table"
                if not ole.exists(table_name):
                    raise UnsupportedFormat(
                        "Beschädigte .doc-Datei (Tabellenstrom fehlt). Bitte in Word als .docx speichern."
                    )
                table = ole.openstream(table_name).read()
                text, ccps = _read_pieces(word, table)
    except UnsupportedFormat:
        raise
    except (OSError, struct.error, IndexError) as exc:
        raise UnsupportedFormat(
            f"Die .doc-Datei ließ sich nicht lesen ({type(exc).__name__}). Bitte in Word als .docx speichern."
        ) from exc

    sections: list[str] = []
    start = 0
    for (name, title), length in zip(_STORIES, ccps):
        part = text[start : start + length]
        start += length
        if title is None:
            continue
        cleaned = _clean(part)
        if cleaned:
            sections.append(cleaned if not title else f"{title}\n{cleaned}")
    return "\n\n".join(sections)
