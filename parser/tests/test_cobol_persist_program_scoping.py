"""
O-138: cobol_persist.py darf einen PERFORM/GOTO/USES niemals auf einen
gleichnamigen Paragraphen/ein gleichnamiges Feld eines ANDEREN Programms
derselben Datei auflösen, nur weil er zufällig der einzige (oder erste)
Namenstreffer ist - Abnahme "gleiche Paragraph-/Feldnamen bleiben
programmlokal". Reine In-Memory-Unit-Tests gegen die internen Helfer, ohne
DB-Verbindung (anders als test_ap4_persistence.py) - `CodeEntity`/`CodeEdge`
sind plain SQLAlchemy-Objekte und brauchen für reine Attributzugriffe keine
Session.
"""

from cobol.model import ParsedEdge
from cobol_persist import _belongs_to_program, _find_src, _parent_id, _resolve_local_target
from models.database import CodeEntity


def _entity(id_: int, name: str, type_: str, qualified_name: str) -> CodeEntity:
    return CodeEntity(id=id_, name=name, type=type_, qualified_name=qualified_name)


def test_resolve_local_target_never_crosses_into_a_different_program():
    # Zwei Programme derselben Datei, beide mit einem Paragraphen PARA-X -
    # PROGA hat KEIN PARA-X. Ein PERFORM aus PROGA muss deshalb unresolved
    # bleiben, nicht auf PROGB.PARA-X zeigen.
    by_qname = {
        "PROGA": _entity(1, "PROGA", "program", "PROGA"),
        "PROGB": _entity(2, "PROGB", "program", "PROGB"),
        "PROGB.PARA-X": _entity(3, "PARA-X", "paragraph", "PROGB.PARA-X"),
    }
    by_name: dict = {}
    for row in by_qname.values():
        by_name.setdefault(row.name.upper(), []).append(row)

    edge = ParsedEdge(
        type="PERFORM",
        src_name="",
        dst_name="PARA-X",
        resolution="resolved",
        src_start_line=1,
        src_end_line=1,
        scope="PROGA",
        meta={"program": "PROGA"},
    )

    assert _resolve_local_target(edge, by_qname, by_name) is None


def test_resolve_local_target_finds_the_same_named_paragraph_in_the_right_program():
    by_qname = {
        "PROGA": _entity(1, "PROGA", "program", "PROGA"),
        "PROGA.PARA-X": _entity(2, "PARA-X", "paragraph", "PROGA.PARA-X"),
        "PROGB": _entity(3, "PROGB", "program", "PROGB"),
        "PROGB.PARA-X": _entity(4, "PARA-X", "paragraph", "PROGB.PARA-X"),
    }
    by_name: dict = {}
    for row in by_qname.values():
        by_name.setdefault(row.name.upper(), []).append(row)

    edge = ParsedEdge(
        type="PERFORM",
        src_name="",
        dst_name="PARA-X",
        resolution="resolved",
        src_start_line=1,
        src_end_line=1,
        scope="PROGB",
        meta={"program": "PROGB"},
    )

    target = _resolve_local_target(edge, by_qname, by_name)
    assert target is not None and target.id == 4


def test_resolve_local_target_without_program_hint_keeps_old_ambiguous_behaviour():
    # Kanten ohne meta["program"] (z.B. handgebaute ParsedEdge in älteren
    # Tests) duerfen sich nicht plötzlich anders verhalten als vor O-138.
    by_qname = {
        "PROGA.PARA-X": _entity(1, "PARA-X", "paragraph", "PROGA.PARA-X"),
    }
    by_name = {"PARA-X": [by_qname["PROGA.PARA-X"]]}

    edge = ParsedEdge(
        type="PERFORM",
        src_name="",
        dst_name="PARA-X",
        resolution="resolved",
        src_start_line=1,
        src_end_line=1,
        scope="PROGA",
    )

    target = _resolve_local_target(edge, by_qname, by_name)
    assert target is not None and target.id == 1


def test_find_src_with_empty_src_name_picks_the_hinted_program_not_the_first_one():
    by_qname = {
        "PROGA": _entity(1, "PROGA", "program", "PROGA"),
        "PROGB": _entity(2, "PROGB", "program", "PROGB"),
    }
    by_name = {"PROGA": [by_qname["PROGA"]], "PROGB": [by_qname["PROGB"]]}

    edge = ParsedEdge(
        type="CALL",
        src_name="",
        dst_name="SOMEWHERE",
        resolution="unresolved",
        src_start_line=1,
        src_end_line=1,
        scope=None,
        meta={"program": "PROGB"},
    )

    src = _find_src(edge, by_qname, by_name)
    assert src is not None and src.id == 2


def test_belongs_to_program_checks_only_the_root_segment():
    row = _entity(1, "PARA-X", "paragraph", "PROGA.SOME-SECTION.PARA-X")
    assert _belongs_to_program(row, "PROGA") is True
    assert _belongs_to_program(row, "PROGB") is False
    assert _belongs_to_program(row, "proga") is True  # case-insensitiv


def test_parent_id_uses_explicit_parent_qname_for_names_with_dots():
    parent = _entity(10, "PaymentService", "class", "com.acme.PaymentService")
    child = _entity(
        11,
        "book(java.lang.String)",
        "method",
        "com.acme.PaymentService#book(java.lang.String)",
    )

    assert (
        _parent_id(
            child.qualified_name,
            {parent.qualified_name: parent},
            {},
            parent_qualified_name=parent.qualified_name,
        )
        == parent.id
    )


def test_parent_id_keeps_legacy_split_for_results_without_parent_qname():
    parent = _entity(10, "PROGA", "program", "PROGA")
    child = _entity(11, "PARA-X", "paragraph", "PROGA.PARA-X")

    assert (
        _parent_id(
            child.qualified_name,
            {parent.qualified_name: parent},
            {},
            legacy_parent_name="PROGA",
        )
        == parent.id
    )


def test_dotted_root_qname_does_not_get_an_inferred_parent():
    root = _entity(11, "Example.java", "compilation_unit", "com.acme.Example.java")

    assert _parent_id(root.qualified_name, {}, {}, legacy_parent_name=None) is None
