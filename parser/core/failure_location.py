"""Kurzbeschreibung einer Parser-Ausnahme mit Fehlerstelle für `parse_error`."""

import os
import re
import traceback

_REMOTE_FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')


def describe_failure(exc: BaseException) -> str:
    """`Typ: Meldung (datei.py:zeile in funktion)` für die innerste Frame der Ausnahme.

    Läuft das Parsen in einem Prozess-Pool, zeigt der lokale Traceback nur auf
    `concurrent.futures`; die echte Stelle steht im `tb`-Text der `__cause__`
    (`_RemoteTraceback`)."""
    text = f"{type(exc).__name__}: {exc}"
    remote = getattr(exc.__cause__, "tb", None)
    if isinstance(remote, str):
        frames = _REMOTE_FRAME.findall(remote)
        if frames:
            filename, lineno, name = frames[-1]
            return f"{text} ({os.path.basename(filename)}:{lineno} in {name})"
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return text
    frame = frames[-1]
    return f"{text} ({os.path.basename(frame.filename)}:{frame.lineno} in {frame.name})"
