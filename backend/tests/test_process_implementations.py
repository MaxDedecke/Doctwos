"""Ablauf-View: Eine Routine ohne eigenen Ablauf führt zu dem, was sie umsetzt."""

import uuid

import pytest

from api.process import (
    _add_implementations,
    _argument_count,
    _projection,
    _requested_kinds,
)
from doctus_models.database import CodeEdge, CodeEntity, Project, Team


@pytest.fixture
def code(db_session):
    team = Team(name=f"process-{uuid.uuid4().hex[:8]}")
    db_session.add(team)
    db_session.flush()
    project = Project(name="process", team_id=team.id)
    db_session.add(project)
    db_session.flush()

    def entity(name, qualified, path, kind="method", parent=None, line=1):
        row = CodeEntity(
            project_id=project.id,
            name=name,
            type=kind,
            file_path=path,
            qualified_name=qualified,
            parent_id=parent.id if parent else None,
            start_line=line,
            end_line=line + 2,
        )
        db_session.add(row)
        db_session.flush()
        return row

    def edge(source, target, kind):
        db_session.add(
            CodeEdge(
                project_id=project.id,
                src_entity_id=source.id,
                dst_entity_id=target.id,
                dst_name=target.name,
                type=kind,
                resolution="resolved",
                src_start_line=1,
                src_end_line=1,
            )
        )
        db_session.flush()

    entity.edge = edge
    return entity


def _flow(db_session, root):
    projection = _projection(db_session, root, "outgoing", 1, 200, 400, _requested_kinds(None))
    _add_implementations(db_session, root, projection, 200)
    return projection


def test_interface_method_leads_to_its_implementations_as_possible(db_session, code):
    api = code("Api", "p.Api", "src/Api.java", "interface")
    method = code("run", "p.Api#run(Map<A,B>,C)", "src/Api.java", parent=api, line=5)
    code("run", "p.Api#run()", "src/Api.java", parent=api, line=8)
    first = code("First", "p.First", "src/First.java", "class")
    exact = code("run", "p.First#run(Map<A,B>,C)", "src/First.java", parent=first, line=10)
    code("run", "p.First#run()", "src/First.java", parent=first, line=20)
    middle = code("Middle", "p.Middle", "src/Middle.java", "class")
    second = code("Second", "p.Second", "src/Second.java", "class")
    # Andere Typparameter: Nur die Zahl der Parameter entscheidet noch.
    renamed = code("run", "p.Second#run(Map<X,Y>,Z)", "src/Second.java", parent=second, line=3)
    code("run", "p.Second#run(X)", "src/Second.java", parent=second, line=9)
    in_test = code("Fake", "p.Fake", "src/test/Fake.java", "class")
    code("run", "p.Fake#run(Map<A,B>,C)", "src/test/Fake.java", parent=in_test)
    code.edge(first, api, "IMPLEMENTS")
    code.edge(middle, api, "IMPLEMENTS")
    code.edge(second, middle, "EXTENDS")
    code.edge(in_test, api, "IMPLEMENTS")
    db_session.commit()

    projection = _flow(db_session, method)

    targets = {t.target: t for t in projection.transitions if (t.meta or {}).get("implementation")}
    assert set(targets) == {f"entity:{exact.id}", f"entity:{renamed.id}"}
    assert all(t.certainty == "possible" and t.kind == "call" for t in targets.values())
    labels = {node.entity_id: node.label for node in projection.nodes}
    assert labels[exact.id] == "First" and labels[renamed.id] == "Second"


def test_routine_with_own_flow_stays_as_it_is(db_session, code):
    base = code("Base", "p.Base", "src/Base.java", "class")
    method = code("run", "p.Base#run()", "src/Base.java", parent=base)
    helper = code("help", "p.Base#help()", "src/Base.java", parent=base, line=7)
    child = code("Child", "p.Child", "src/Child.java", "class")
    code("run", "p.Child#run()", "src/Child.java", parent=child)
    code.edge(child, base, "EXTENDS")
    code.edge(method, helper, "CALLS")
    db_session.commit()

    projection = _flow(db_session, method)

    assert not [t for t in projection.transitions if (t.meta or {}).get("implementation")]


def test_language_without_realization_gets_nothing(db_session, code):
    program = code("PROG", "PROG", "src/PROG.cbl", "program")
    paragraph = code("EMPTY-PARA", "PROG.EMPTY-PARA", "src/PROG.cbl", "paragraph", parent=program)
    db_session.commit()

    assert _flow(db_session, paragraph).transitions == []


def test_argument_count_ignores_commas_in_type_arguments():
    assert _argument_count("#f()") == 0
    assert _argument_count("#f(A)") == 1
    assert _argument_count("#f(Map<A,List<B,C>>,D)") == 2
    assert _argument_count("#field") == 0
