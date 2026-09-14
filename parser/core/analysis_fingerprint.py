"""Stabile Analyse-Fingerprints für inkrementelle Strukturparses (O-122).

Ein Git-Blob allein sagt nur, ob sich der Quelltext geändert hat. Seine
Strukturanalyse kann sich aber ebenso durch ein anderes effektives Buildprofil,
eine Parser-/Grammatikänderung oder einen aktualisierten Copybook-Bestand
ändern. Der Fingerprint hält genau diese Eingaben pro Datei fest. Er ist
bewusst eine reine Funktion: dieselben Analyse-Eingaben ergeben überall
denselben SHA-256-Wert und können daher sicher als Resume-Schlüssel dienen.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

# Änderungen an handgeschriebenen Scanner-/Persistenzregeln sind nicht aus
# einer Grammatikdatei ableitbar. Dieser Wert ist deshalb ein absichtlicher,
# bei semantischen Parseränderungen zu erhöhender Vertrag.
COBOL_PARSER_VERSION = "3"


def grammar_fingerprint() -> str:
    """Hash der tatsächlich eingecheckten ANTLR-Quellen, nicht der generierten
    Python-Dateien. Damit invalidiert eine Grammatikänderung vorhandene
    Ergebnisse auch dann, wenn sich weder Git-Blob noch Profil ändern."""
    grammar_dir = Path(__file__).resolve().parents[1] / "cobol" / "grammar"
    digest = hashlib.sha256()
    for grammar in sorted(grammar_dir.glob("*.g4")):
        digest.update(grammar.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(grammar.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def profile_payload(profile: object | None) -> dict[str, object]:
    """JSON-stabile Repräsentation des *effektiven* Profils.

    Nicht die Eingabe-Fragmente, sondern ihr aufgelöstes Ergebnis gehört in
    den Schlüssel: Zwei unterschiedliche Konfigurationen mit identischem
    Parse-Verhalten dürfen inkrementell bleiben. ``resolved_from`` bleibt
    enthalten, weil diese Herkunft als O-121-Diagnose Teil des Ergebnisses
    ist.
    """
    # Keine Import-Abhängigkeit von ``cobol``: der Fingerprint ist der
    # gemeinsame Resume-Mechanismus aller Strukturparser. Ein künftiges
    # Sprachprofil muss nur dieselben benannten Felder anbieten.
    return {
        "compiler_family": getattr(profile, "compiler_family", None),
        "compiler_version": getattr(profile, "compiler_version", None),
        "source_format": getattr(profile, "source_format", None),
        "source_columns": {
            "sequence_end": getattr(getattr(profile, "source_columns", None), "sequence_end", None),
            "indicator_column": getattr(
                getattr(profile, "source_columns", None), "indicator_column", None
            ),
            "area_a_start": getattr(getattr(profile, "source_columns", None), "area_a_start", None),
            "area_b_start": getattr(getattr(profile, "source_columns", None), "area_b_start", None),
            "code_end": getattr(getattr(profile, "source_columns", None), "code_end", None),
        }
        if getattr(profile, "source_columns", None) is not None
        else None,
        "encoding": getattr(profile, "encoding", None),
        "debug_mode": getattr(profile, "debug_mode", False),
        "literal_delimiter": getattr(profile, "literal_delimiter", "both"),
        "defines": dict(sorted(getattr(profile, "defines", {}).items())),
        "copy_search_order": list(getattr(profile, "copy_search_order", ())),
        "resolved_from": dict(sorted(getattr(profile, "resolved_from", {}).items())),
    }


def analysis_fingerprint(
    *,
    source_revision: str,
    profile: object | None = None,
    parser_version: str = COBOL_PARSER_VERSION,
    grammar_version: str | None = None,
    libraries: Mapping[str, str] | None = None,
) -> str:
    """Bildet alle parse-relevanten Eingaben auf einen SHA-256-Wert ab.

    ``libraries`` ist Pfad -> Git-Blob-SHA der für die Quelle verfügbaren
    Copybooks. Sortierung und kompaktes JSON vermeiden maschinen- oder
    Einfügereihenfolge-abhängige Ergebnisse.
    """
    payload = {
        "source_revision": source_revision,
        "profile": profile_payload(profile),
        "parser_version": parser_version,
        "grammar_version": grammar_version or grammar_fingerprint(),
        "libraries": dict(sorted((libraries or {}).items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
