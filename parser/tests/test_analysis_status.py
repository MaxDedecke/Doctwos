"""
O-120: `classify_completeness()` darf `errors == []` nicht mehr als "ok"
missverstehen -- sie muss die strukturierten O-119-Diagnosen mit einbeziehen
und den F-029-Textfallback von echten Teilerfolgen unterscheiden.
"""

from core.model import Chunk, ParseDiagnostic, ParseResult, classify_completeness


def _result(**kwargs) -> ParseResult:
    defaults = dict(program_name="TESTPGM", path="test.cbl", source_format="fixed")
    defaults.update(kwargs)
    return ParseResult(**defaults)


def _chunk(fallback: bool = False) -> Chunk:
    meta = {"program": "TESTPGM", "format": "fixed"}
    if fallback:
        meta["fallback"] = True
    else:
        meta["section"] = "MAIN-SECTION"
        meta["paragraph"] = "MAIN-PARA"
    return Chunk(content="x", start_line=1, end_line=1, meta=meta)


def _diag(severity: str, message: str = "etwas ist unsicher") -> ParseDiagnostic:
    return ParseDiagnostic(
        code="TEST_DIAG", severity=severity, phase="parser", message=message, line=1, column=0
    )


def test_clean_parse_without_errors_or_diagnostics_is_complete():
    result = _result(chunks=[_chunk()])
    status, reasons = classify_completeness(result)
    assert status == "complete"
    assert reasons == []


def test_legacy_errors_alone_already_meant_incomplete():
    result = _result(chunks=[_chunk()], errors=["PROGRAM-ID nicht gefunden"])
    status, reasons = classify_completeness(result)
    assert status == "partial"
    assert reasons == ["PROGRAM-ID nicht gefunden"]


def test_error_severity_diagnostic_with_empty_errors_is_no_longer_reported_as_complete():
    # Das ist genau die O-120-Ausgangslücke: errors == [] wurde bisher als "ok"
    # interpretiert, obwohl O-119 eine strukturierte Fehlerdiagnose meldet.
    result = _result(chunks=[_chunk()], diagnostics=[_diag("error", "mismatched input")])
    status, reasons = classify_completeness(result)
    assert status == "partial"
    assert reasons == ["mismatched input"]


def test_warning_severity_diagnostic_also_downgrades_from_complete():
    # z.B. O-121s PROFILE_UNKNOWN_COMPILER_FAMILY -- ein ungeklärter Dialekt
    # darf nicht als uneingeschränkt analysiert erscheinen (O-120-Abnahme).
    result = _result(
        chunks=[_chunk()], diagnostics=[_diag("warning", "unbekannte compiler_family")]
    )
    status, reasons = classify_completeness(result)
    assert status == "partial"
    assert reasons == ["unbekannte compiler_family"]


def test_info_severity_diagnostic_alone_stays_complete():
    # O-121s SOURCE_FORMAT_HEURISTIC-Notiz fällt heute für praktisch jede
    # Datei an, solange niemand ein Buildprofil übergibt -- das allein darf
    # keine ansonsten saubere Datei zu "partial" degradieren.
    result = _result(chunks=[_chunk()], diagnostics=[_diag("info", "Format per Heuristik erkannt")])
    status, reasons = classify_completeness(result)
    assert status == "complete"
    assert reasons == []


def test_fallback_chunk_is_text_fallback_even_without_errors():
    result = _result(chunks=[_chunk(fallback=True)])
    status, reasons = classify_completeness(result)
    assert status == "text_fallback"
    assert reasons  # generische Begründung, da errors/diagnostics leer sind


def test_fallback_chunk_keeps_its_real_reasons_when_present():
    result = _result(
        chunks=[_chunk(fallback=True)],
        errors=["Keine PROCEDURE DIVISION gefunden"],
    )
    status, reasons = classify_completeness(result)
    assert status == "text_fallback"
    assert reasons == ["Keine PROCEDURE DIVISION gefunden"]


def test_copybook_chunk_without_fallback_marker_is_not_text_fallback():
    # Copybooks haben planmäßig keine PROCEDURE DIVISION -- ihr Chunk trägt
    # deshalb kein "fallback"-Meta (siehe Chunk-Docstring), das ist erwartetes
    # Verhalten und kein Analyse-Ausfall.
    chunk = Chunk(content="x", start_line=1, end_line=1, meta={"program": "CPY1", "copybook": True})
    result = _result(chunks=[chunk])
    status, reasons = classify_completeness(result)
    assert status == "complete"
    assert reasons == []
