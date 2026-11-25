"""Projektüberblick im Belegpaket: derselbe Baustein für COBOL/JCL und Java, nur aus Rollen und Dateikanten."""

import json
import pytest

from codena_models.database import CodeEdge, CodeEntity, CodeFileEdge, DocumentChunk, User
from services import answer_context
from services.chat_sources import extract_tool_sources
from services.evidence_overview import OVERVIEW_INTENT, project_overview
from tests.conftest import TEST_USERNAME


def _entity(db, project_id, name, kind, path, start=1, end=40):
    entity = CodeEntity(
        project_id=project_id,
        name=name,
        type=kind,
        file_path=path,
        qualified_name=name,
        start_line=start,
        end_line=end,
    )
    db.add(entity)
    db.flush()
    return entity


def _file_edge(db, project_id, src, dst, types, *, count=1, total_pairs=None):
    db.add(
        CodeFileEdge(
            project_id=project_id,
            src_project_id=project_id,
            dst_project_id=project_id,
            src_file_path=src,
            dst_file_path=dst,
            edge_count=count,
            edge_types=types,
            sample_edge_ids=[],
            priority=3,
            src_degree=1,
            dst_degree=1,
            total_pairs=total_pairs or 0,
        )
    )


def _finish(db, project_id, total_pairs=None):
    db.flush()
    stored = db.query(CodeFileEdge).filter(CodeFileEdge.project_id == project_id).count()
    db.query(CodeFileEdge).filter(CodeFileEdge.project_id == project_id).update(
        {"total_pairs": total_pairs or stored}
    )
    db.commit()


@pytest.fixture
def cobol_project(db_session, test_project):
    db = db_session
    _entity(db, test_project, "NIGHTLY", "jcl_job", "jcl/NIGHTLY.jcl", 1, 30)
    _entity(db, test_project, "CBACT04C", "program", "cbl/CBACT04C.cbl", 5, 400)
    _entity(db, test_project, "CBTRN02C", "program", "cbl/CBTRN02C.cbl", 3, 300)
    _entity(db, test_project, "DATEUTIL", "program", "cbl/util/DATEUTIL.cbl", 1, 90)
    _entity(db, test_project, "1000-MAIN", "paragraph", "cbl/CBACT04C.cbl", 120, 160)
    _entity(db, test_project, "WS-RATE", "data_item", "cbl/CBACT04C.cbl", 40, 40)
    _file_edge(db, test_project, "jcl/NIGHTLY.jcl", "cbl/CBACT04C.cbl", ["EXECUTES"])
    _file_edge(db, test_project, "jcl/NIGHTLY.jcl", "cbl/CBTRN02C.cbl", ["EXECUTES"])
    _file_edge(db, test_project, "cbl/CBACT04C.cbl", "cbl/util/DATEUTIL.cbl", ["CALL", "READS"])
    _file_edge(db, test_project, "cbl/CBTRN02C.cbl", "cbl/util/DATEUTIL.cbl", ["CALL"])
    # Einbindung ohne Kontrollfluss: macht ein Copybook weder zum Einstieg noch zur meistgenutzten Einheit.
    _file_edge(
        db, test_project, "cbl/CBACT04C.cbl", "cpy/CVACT01Y.cpy", ["COPY", "READS"], count=300
    )
    db.add(
        DocumentChunk(
            project_id=test_project,
            file_path="README.md",
            content="# Kartenverwaltung\nBatch und Online für Kreditkartenkonten.",
            start_line=1,
            end_line=2,
        )
    )
    _finish(db, test_project)
    yield test_project
    _cleanup(db, test_project)


@pytest.fixture
def java_project(db_session, test_project):
    db = db_session
    base = "src/main/java/org/demo"
    _entity(db, test_project, "Application", "class", f"{base}/Application.java", 10, 30)
    _entity(
        db, test_project, "OrderController", "class", f"{base}/web/OrderController.java", 12, 80
    )
    _entity(
        db, test_project, "OrderService", "interface", f"{base}/service/OrderService.java", 8, 20
    )
    _entity(
        db, test_project, "OrderRepository", "class", f"{base}/data/OrderRepository.java", 9, 60
    )
    _entity(db, test_project, "create", "method", f"{base}/web/OrderController.java", 30, 44)
    _entity(db, test_project, "total", "field", f"{base}/data/OrderRepository.java", 12, 12)
    _file_edge(
        db, test_project, f"{base}/Application.java", f"{base}/web/OrderController.java", ["CALLS"]
    )
    _file_edge(
        db,
        test_project,
        f"{base}/web/OrderController.java",
        f"{base}/service/OrderService.java",
        ["CALLS", "IMPORTS"],
    )
    _file_edge(
        db,
        test_project,
        f"{base}/service/OrderService.java",
        f"{base}/data/OrderRepository.java",
        ["DISPATCHES_TO"],
    )
    _file_edge(
        db,
        test_project,
        f"{base}/web/OrderController.java",
        f"{base}/data/OrderRepository.java",
        ["CALLS"],
    )
    _file_edge(
        db, test_project, f"{base}/web/OrderController.java", f"{base}/data/Order.java", ["IMPORTS"]
    )
    _finish(db, test_project)
    yield test_project
    _cleanup(db, test_project)


def _cleanup(db, project_id):
    for model in (CodeEdge, CodeFileEdge, CodeEntity, DocumentChunk):
        db.query(model).filter(model.project_id == project_id).delete()
    db.commit()


def test_cobol_overview_names_documentation_inventory_entry_job_and_most_used_program(
    db_session, cobol_project
):
    overview = project_overview(db_session, cobol_project)

    assert overview["documentation"][0]["cite"] == "README.md:1"
    assert "Kreditkartenkonten" in overview["documentation"][0]["excerpt"]
    by_language = {row["language"]: row for row in overview["inventory"]}
    assert by_language["cobol"] == {
        "language": "cobol",
        "containers": {"program": 3},
        "routines": 1,
        "data": 1,
    }
    assert by_language["jcl"]["containers"] == {"jcl_job": 1}
    assert {"directory": "cbl", "units": 2} in overview["areas"]
    assert [(e["unit"], e["cite"], e["starts"]) for e in overview["entry_points"]] == [
        ("NIGHTLY", "jcl/NIGHTLY.jcl:1", ["CBACT04C", "CBTRN02C"])
    ]
    most_used = overview["most_used"][0]
    assert (most_used["unit"], most_used["cite"], most_used["used_by_files"]) == (
        "DATEUTIL",
        "cbl/util/DATEUTIL.cbl:1",
        2,
    )
    assert "CVACT01Y" not in json.dumps(overview)
    assert overview["gaps"] == []


def test_java_overview_uses_the_same_block_with_java_roles(db_session, java_project):
    overview = project_overview(db_session, java_project)

    assert overview["inventory"] == [
        {"language": "java", "containers": {"class": 3, "interface": 1}, "routines": 1, "data": 1}
    ]
    assert [e["unit"] for e in overview["entry_points"]] == ["Application"]
    assert overview["entry_points"][0]["starts"] == ["OrderController"]
    assert overview["most_used"][0]["unit"] == "OrderRepository"
    assert overview["most_used"][0]["cite"] == "src/main/java/org/demo/data/OrderRepository.java:9"
    # Ein reiner Import ist kein Kontrollfluss.
    assert "Order.java" not in json.dumps(overview)
    assert overview["gaps"] == ["no README at the repository root is indexed"]


def test_backbone_only_projects_check_entry_candidates_against_single_edges(
    db_session, java_project
):
    """Bei großen Projekten ist nur das Grundgerüst gespeichert; eine fehlende Dateikante belegt dort nichts."""
    db = db_session
    base = "src/main/java/org/demo"
    caller = _entity(db, java_project, "run", "method", f"{base}/Launcher.java", 5, 9)
    application = (
        db.query(CodeEntity)
        .filter(CodeEntity.project_id == java_project, CodeEntity.name == "Application")
        .one()
    )
    db.add(
        CodeEdge(
            project_id=java_project,
            src_entity_id=caller.id,
            dst_entity_id=application.id,
            dst_name="Application",
            type="CALLS",
        )
    )
    _finish(db, java_project, total_pairs=5000)

    overview = project_overview(db, java_project)

    assert overview["entry_points"] == []
    assert any("lower bounds" in gap for gap in overview["gaps"])


def test_overview_is_cut_to_its_budget_documents_first_then_the_longest_lists():
    from services.evidence_overview import _fit

    unit = {
        "unit": "PROGRAM1",
        "type": "program",
        "file": "cbl/PROGRAM1.cbl",
        "cite": "cbl/PROGRAM1.cbl:1",
    }
    overview = {
        "documentation": [{"file": "README.md", "cite": "README.md:1", "excerpt": "x" * 1400}],
        "inventory": [
            {"language": "cobol", "containers": {"program": 40}, "routines": 900, "data": 11000}
        ],
        "areas": [{"directory": f"dir{i}", "units": i} for i in range(8)],
        "entry_points": [dict(unit, starts=["A", "B"]) for _ in range(12)],
        "most_used": [dict(unit, used_by_files=3) for _ in range(12)],
        "gaps": [],
        "notice": "n",
    }

    _fit(overview, 2500)

    assert len(json.dumps(overview, ensure_ascii=False)) <= 2500
    assert len(overview["documentation"][0]["excerpt"]) == 500
    assert overview["truncated"] is True and len(overview["entry_points"]) >= 3


def test_project_without_index_has_no_overview(db_session, test_project):
    assert project_overview(db_session, test_project) is None


@pytest.mark.parametrize(
    "question",
    [
        "Was ist das für ein projekt ?",
        "Explore die codebase und sage mir was das projekt genau macht",
        "Gib mir eine tour",
        "Welche prozesse passieren hier ?",
        "Give me an overview of the architecture",
    ],
)
def test_overview_intent_matches_questions_about_the_project_as_a_whole(question):
    assert OVERVIEW_INTENT.search(question)


@pytest.mark.parametrize(
    "question", ["Wie berechnet CBACT04C die Zinsen?", "Wer ruft UserServiceImpl.create auf?"]
)
def test_overview_intent_ignores_questions_about_named_code(question):
    assert not OVERVIEW_INTENT.search(question)


def test_answer_context_adds_the_overview_only_for_overview_questions(
    db_session, cobol_project, monkeypatch
):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).one()
    monkeypatch.setattr(answer_context, "stale_sources", lambda *_a, **_k: [])

    asked = answer_context.build_answer_context(
        db_session,
        user,
        cobol_project,
        question="Was ist das für ein Projekt?",
        use_embeddings=False,
    )
    other = answer_context.build_answer_context(
        db_session, user, cobol_project, question="Wo steht die Zinsformel?", use_embeddings=False
    )
    forced = answer_context.build_answer_context(
        db_session,
        user,
        cobol_project,
        question="Wo steht die Zinsformel?",
        use_embeddings=False,
        overview=True,
    )

    assert asked["overview"]["entry_points"][0]["unit"] == "NIGHTLY"
    assert "overview" not in other
    assert forced["overview"]["most_used"][0]["unit"] == "DATEUTIL"


def test_overview_cites_become_clickable_sources(db_session, cobol_project):
    result = {"resolved": [], "overview": project_overview(db_session, cobol_project)}
    sources: list[dict] = []

    event = {"type": "tool_result", "name": "answer_context", "result": json.dumps(result)}
    extract_tool_sources(event, sources, None)

    located = {(s["file"], tuple(s["lines"])) for s in sources}
    assert ("README.md", (1, 2)) in located
    assert ("jcl/NIGHTLY.jcl", (1, 30)) in located
    assert ("cbl/util/DATEUTIL.cbl", (1, 90)) in located
