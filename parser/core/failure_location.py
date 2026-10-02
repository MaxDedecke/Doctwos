"""Kurzbeschreibung einer Parser-Ausnahme mit Fehlerstelle für `parse_error`."""

import os
import traceback


def describe_failure(exc: BaseException) -> str:
    """`Typ: Meldung (datei.py:zeile in funktion)` für die innerste Frame der Ausnahme."""
    text = f"{type(exc).__name__}: {exc}"
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return text
    frame = frames[-1]
    return f"{text} ({os.path.basename(frame.filename)}:{frame.lineno} in {frame.name})"
