"""O-375: Ziele derselben Datei (EXEC-Operation, SQL INCLUDE, EXEC-Ressource)
müssen beim Persistieren aufgelöst werden; nur Copybook-Kreuzverweise warten auf Pass 2."""

from core.model import ParsedEdge
from models.database import CodeEntity
from structure_persist import _build_edge

PGM = "COSGN00C"
BLOCK = f"{PGM}.EXEC-CICS-BLOCK@98"
OPERATION = f"{BLOCK}.RETURN@98"


def _entity(entity_id: int, name: str, entity_type: str, qualified_name: str) -> CodeEntity:
    return CodeEntity(
        id=entity_id, name=name, type=entity_type, qualified_name=qualified_name,
        file_path="app/cbl/COSGN00C.cbl", variant_key="default",
    )


def _index():
    rows = [
        _entity(1, "EXEC-CICS-BLOCK@98", "exec_block", BLOCK),
        _entity(2, "RETURN", "exec_operation", OPERATION),
    ]
    by_qname = {r.qualified_name: r for r in rows}
    by_name: dict[str, list[CodeEntity]] = {}
    for r in rows:
        by_name.setdefault(r.name.upper(), []).append(r)
    return by_qname, by_name


def _edge(meta: dict, dst_name: str = "RETURN") -> ParsedEdge:
    return ParsedEdge(
        type="EXECUTES", src_name=BLOCK, dst_name=dst_name, resolution="resolved",
        src_start_line=98, src_end_line=102, scope=PGM,
        meta={"program": PGM, "dialect": "CICS", "language": "cobol", **meta},
    )


def test_exec_operation_in_the_same_file_is_resolved_when_persisted():
    by_qname, by_name = _index()
    row = _build_edge(1, 7, "default", _edge({"target_qualified_name": OPERATION}), by_qname, by_name)
    assert row.resolution == "resolved"
    assert row.dst_entity_id == 2


def test_copybook_cross_reference_still_waits_for_pass_two():
    by_qname, by_name = _index()
    meta = {"target_qualified_name": "OTHER.FIELD", "copybook_path": "cpy/OTHER.cpy"}
    row = _build_edge(1, 7, "default", _edge(meta), by_qname, by_name)
    assert row.resolution == "unresolved"
    assert row.dst_entity_id is None


def test_missing_local_target_stays_unresolved():
    by_qname, by_name = _index()
    row = _build_edge(1, 7, "default", _edge({"target_qualified_name": f"{BLOCK}.SEND@98"}, "SEND"), by_qname, by_name)
    assert row.resolution == "unresolved"
