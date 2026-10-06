"""
parser/connectors/textio.py
===========================
Textdateien robust einlesen. Kundenablagen enthalten neben UTF-8 oft Windows-Exporte (cp1252) oder
Latin-1; ``open(..., errors="ignore")`` ließ dort Umlaute stillschweigend verschwinden.
"""

import codecs


def decode_text(data: bytes) -> str:
    """Dekodiert Bytes als UTF-8 (mit/ohne BOM) oder UTF-16 mit BOM, sonst cp1252, zuletzt Latin-1.

    Latin-1 ordnet jedes Byte zu und schlägt nie fehl; cp1252 kommt vorher dran, weil es im Bereich
    0x80-0x9F die in Windows-Dokumenten üblichen Zeichen (€, „ “, –) kennt.
    """
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def read_text_file(file_path: str) -> str:
    with open(file_path, "rb") as handle:
        return decode_text(handle.read())
