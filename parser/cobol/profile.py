"""
parser/cobol/profile.py
=========================
O-121: Buildprofile als expliziter Parser-Eingabewert statt impliziter
Heuristik. Ein Profil beschreibt Compilerfamilie/-version, Quellformat,
Encoding, Defines und COPY-Suchreihenfolge für eine COBOL-Quelle — heute
nur als Datenstruktur plus Resolver; DB-Persistenz und eine
Einrichtungsoberfläche pro Kundenquelle sind O-151s Aufgabe
(Profilimport/-export, manuelle Overrides), nicht diese.

Drei Vererbungsebenen, jede optional (`ProfileFragment`, jedes Feld `None`
heißt "diese Ebene äußert sich nicht dazu"):

    Quelle (z.B. ganzes Git-Repo)
      -> Pfad/Member (z.B. ein Unterverzeichnis/Bibliothekselement)
        -> Buildvariante (z.B. explizite Übersteuerung für einen Lauf)

`resolve_profile()` verschmilzt sie zu einem `BuildProfile`: die
spezifischste Ebene gewinnt je Feld.

Nur `source_format` wirkt heute tatsächlich auf `parse.py` (Profil-Wert
überschreibt `source_format.detect_format()`; fehlt er, bleibt die
Heuristik aktiv, erzeugt aber eine `ParseDiagnostic`, die sie als Vermutung
statt Tatsache kennzeichnet — O-121-Abnahme "keine automatische
Dialekterkennung als Gewissheit ausgeben"). `compiler_version`, `encoding`
(O-127), `defines` (O-124: `>>IF`/`>>DEFINE`-Auswertung) und
`copy_search_order` (O-135: COPY-Suchreihenfolge) sind bewusst schon als
Felder vorhanden, weil die jeweiligen Ticket-Texte sie selbst als
Profilfelder nennen — aber noch von niemandem gelesen. Kein Vorbau auf
Vorrat, sondern vorbereitete Erweiterungspunkte für Tickets, die explizit
auf O-121 aufbauen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import ParseDiagnostic, SourceFormat

# MAINFRAME_KOMPATIBILITAET.md nennt diese Namen als Beispiele für die
# Kundenprofil-Aufnahme (O-117) - keine abschließende Liste, nur die
# Grundlage für eine "kennen wir"/"kennen wir nicht"-Diagnose. Eine
# unbekannte Familie blockiert nichts (derselbe generische ANTLR-COBOL85-
# Parser läuft für alle Quellen unverändert) - macht die Unsicherheit aber
# sichtbar statt sie zu verschweigen.
KNOWN_COMPILER_FAMILIES = frozenset(
    {
        "IBM_ENTERPRISE_COBOL",
        "FUJITSU_COBOL2000",
        "MICRO_FOCUS",
        "GNUCOBOL",
    }
)

_LAYER_NAMES: tuple[str, ...] = ("source", "path", "variant")
_SCALAR_FIELDS: tuple[str, ...] = ("compiler_family", "compiler_version", "source_format", "encoding")


@dataclass(frozen=True)
class ProfileFragment:
    """Eine einzelne Vererbungsebene. Ein `None`-Feld heißt "keine Aussage
    dieser Ebene" - resolve_profile() unterscheidet das bewusst nicht von
    "explizit leer" (ein COBOL-Buildprofil kennt kein sinnvolles "bewusst
    leeres" Encoding o.ä.)."""

    compiler_family: str | None = None
    compiler_version: str | None = None
    source_format: SourceFormat | None = None
    encoding: str | None = None
    defines: dict[str, str] | None = None
    copy_search_order: tuple[str, ...] | None = None


@dataclass(frozen=True)
class BuildProfile:
    """Das aufgelöste, effektive Profil (O-121-Abnahme "effektives Profil
    reproduzierbar"). `resolved_from` hält je gesetztem Skalarfeld fest,
    welche Ebene es geliefert hat - Nachvollziehbarkeit, ohne die drei
    ursprünglichen Fragmente erneut mitführen zu müssen."""

    compiler_family: str | None = None
    compiler_version: str | None = None
    source_format: SourceFormat | None = None
    encoding: str | None = None
    defines: dict[str, str] = field(default_factory=dict)
    copy_search_order: tuple[str, ...] = ()
    resolved_from: dict[str, str] = field(default_factory=dict)


def resolve_profile(
    source: ProfileFragment | None = None,
    path: ProfileFragment | None = None,
    variant: ProfileFragment | None = None,
) -> tuple[BuildProfile, list[ParseDiagnostic]]:
    """Verschmilzt bis zu drei Vererbungsebenen zu einem `BuildProfile` -
    reine Funktion, dieselben drei Fragmente ergeben immer dasselbe Profil
    (O-121-Abnahme "reproduzierbar"). Spezifischste Ebene gewinnt je Feld
    (variant > path > source).

    Setzen mehrere Ebenen DASSELBE Feld auf unterschiedliche, jeweils
    explizite Werte, ist das kein Fehler - die spezifischste Ebene gewinnt
    wie in jeder Override-Kette -, aber eine stille Übersteuerung wäre
    genau die Art Unsicherheit, die O-121 sichtbar machen soll ("Konflikte
    sichtbar"): dafür gibt es je Fall eine `severity="info"`-Diagnose.
    Stimmen mehrere Ebenen im Wert überein, gilt das nicht als Konflikt."""
    layers = {"source": source, "path": path, "variant": variant}
    diagnostics: list[ParseDiagnostic] = []

    resolved: dict[str, object] = {}
    resolved_from: dict[str, str] = {}
    for field_name in _SCALAR_FIELDS:
        setters = [
            (layer_name, getattr(layers[layer_name], field_name))
            for layer_name in _LAYER_NAMES
            if layers[layer_name] is not None
            and getattr(layers[layer_name], field_name) is not None
        ]
        if not setters:
            continue
        winning_layer, value = setters[-1]
        resolved[field_name] = value
        resolved_from[field_name] = winning_layer
        if len({v for _, v in setters}) > 1:
            named = ", ".join(f"{layer}={value!r}" for layer, value in setters)
            diagnostics.append(
                ParseDiagnostic(
                    code="PROFILE_FIELD_OVERRIDDEN",
                    severity="info",
                    phase="profile",
                    message=(
                        f"Profilfeld '{field_name}' ist auf mehreren Ebenen "
                        f"gesetzt ({named}); '{winning_layer}' gewinnt."
                    ),
                    line=0,
                    column=0,
                )
            )

    merged_defines: dict[str, str] = {}
    for layer_name in _LAYER_NAMES:
        frag = layers[layer_name]
        if frag is not None and frag.defines:
            merged_defines.update(frag.defines)

    merged_copy_order: tuple[str, ...] = ()
    for layer_name in _LAYER_NAMES:
        frag = layers[layer_name]
        if frag is not None and frag.copy_search_order:
            merged_copy_order = frag.copy_search_order

    family = resolved.get("compiler_family")
    if family is not None and family not in KNOWN_COMPILER_FAMILIES:
        diagnostics.append(
            ParseDiagnostic(
                code="PROFILE_UNKNOWN_COMPILER_FAMILY",
                severity="warning",
                phase="profile",
                message=(
                    f"Unbekannte compiler_family '{family}' - wird wie jede "
                    "andere Quelle mit der generischen ANTLR-COBOL85-"
                    "Grammatik analysiert, keine dialektspezifische Anpassung."
                ),
                line=0,
                column=0,
            )
        )

    profile = BuildProfile(
        compiler_family=resolved.get("compiler_family"),
        compiler_version=resolved.get("compiler_version"),
        source_format=resolved.get("source_format"),
        encoding=resolved.get("encoding"),
        defines=merged_defines,
        copy_search_order=merged_copy_order,
        resolved_from=resolved_from,
    )
    return profile, diagnostics
