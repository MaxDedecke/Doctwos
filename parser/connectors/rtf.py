"""
parser/connectors/rtf.py
========================
Text aus RTF-Dokumenten ohne Fremdbibliothek.

RTF ist ein Klartextformat aus Gruppen (``{...}``), Steuerwörtern (``\\par``) und Escapes (``\\'e4``, ``\\u8364?``).
Der Parser behält den sichtbaren Text, übersetzt Absatz-, Tabulator- und Tabellenmarken, dekodiert Zeichen nach der
Codepage des Dokuments und überspringt Zielgruppen ohne Fließtext (Schrift-/Farbtabellen, Bilder, Feldanweisungen,
Kopf-/Fußzeilen, Eigenschaften).
"""

import re

# Gruppen, deren Inhalt kein Fließtext ist.
_SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "headerl", "headerr", "headerf",
    "footerl", "footerr", "footerf", "fldinst", "generator", "themedata", "colorschememapping", "latentstyles",
    "datastore", "listtable", "listoverridetable", "rsidtbl", "xmlnstbl", "object", "objdata", "bkmkstart",
    "bkmkend", "revtbl", "pgptbl", "template", "mmathPr", "shpinst", "nonshppict", "wgrffmtfilter", "private",
}

_SYMBOLS = {
    "emdash": "\u2014", "endash": "\u2013", "bullet": "\u2022", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "emspace": " ", "enspace": " ", "tab": "\t",
    "par": "\n", "line": "\n", "row": "\n", "page": "\n\n", "sect": "\n\n", "cell": " | ", "nestcell": " | ",
}

_CONTROL = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?")


def _codec(codepage: int) -> str:
    name = f"cp{codepage}"
    try:
        "x".encode(name)
        return name
    except LookupError:
        return "latin-1"


def extract_rtf_text(path: str) -> str:
    with open(path, "rb") as handle:
        return rtf_to_text(handle.read())


def rtf_to_text(data: bytes) -> str:
    if not data.lstrip().startswith(b"{\\rtf"):
        raise ValueError("keine RTF-Datei")

    out: list[str] = []
    pending = bytearray()
    codepage = 1252
    stack: list[tuple[bool, int]] = []  # (überspringen, Anzahl zu überspringender Ersatzzeichen nach \u)
    skip = False
    uc_skip = 1
    skip_chars = 0  # nach \uN: so viele Ersatzzeichen noch verwerfen
    index, length = 0, len(data)

    def flush() -> None:
        if pending:
            out.append(pending.decode(_codec(codepage), errors="replace"))
            pending.clear()

    def emit(text: str) -> None:
        nonlocal skip_chars
        flush()
        if not skip:
            out.append(text)

    while index < length:
        byte = data[index : index + 1]
        if byte == b"{":
            stack.append((skip, uc_skip))
            index += 1
        elif byte == b"}":
            flush()
            if stack:
                skip, uc_skip = stack.pop()
            index += 1
        elif byte == b"\\":
            nxt = data[index + 1 : index + 2]
            if nxt in (b"\\", b"{", b"}"):
                if skip_chars:
                    skip_chars -= 1
                else:
                    emit(nxt.decode())
                index += 2
            elif nxt == b"'":
                hex_digits = data[index + 2 : index + 4]
                index += 4
                if skip_chars:
                    skip_chars -= 1
                    continue
                if not skip:
                    try:
                        pending.append(int(hex_digits, 16))
                    except ValueError:
                        pass
            elif nxt == b"*":
                # Ignorierbare Zielgruppe: Inhalt überspringen, wenn die Anwendung sie nicht kennt (wir kennen keine).
                skip = True
                index += 2
            elif nxt == b"~":
                emit("\u00a0")
                index += 2
            elif nxt == b"_":
                emit("-")
                index += 2
            elif nxt in (b"-", b":", b"|"):
                index += 2
            elif nxt in (b"\n", b"\r"):
                emit("\n")
                index += 2
            else:
                match = _CONTROL.match(data, index)
                if not match:
                    index += 1
                    continue
                word = match.group(1).decode("ascii")
                param = int(match.group(2)) if match.group(2) else None
                index = match.end()
                flush()
                if word in _SKIP_DESTINATIONS:
                    skip = True
                elif word == "ansicpg" and param:
                    codepage = param
                elif word == "uc" and param is not None:
                    uc_skip = param
                elif word == "u" and param is not None:
                    code = param + 65536 if param < 0 else param
                    emit(chr(code) if 0 < code < 0x110000 else "")
                    skip_chars = uc_skip
                elif word in _SYMBOLS:
                    emit(_SYMBOLS[word])
        elif byte in (b"\r", b"\n"):
            index += 1
        else:
            if skip_chars:
                skip_chars -= 1
            elif not skip:
                flush()
                out.append(byte.decode("latin-1"))
            index += 1
    flush()

    lines = [re.sub(r"[ \t]+$", "", re.sub(r"\s*\|\s*$", "", line)) for line in "".join(out).split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
