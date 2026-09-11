"""
O-165: Der Link-Manager lud seine Vorschlagslisten so, dass die Ansicht bei
vierstelliger Vorschlagszahl spürbar einbrach. Backend-seitig lagen dafür zwei
Ursachen vor:

* die Tab-Zähler entstanden im Frontend aus drei kompletten Statuslisten --
  dafür gibt es jetzt `GET /knowledge-links/counts`;
* `list_knowledge_links` prüfte die Sichtbarkeit pro Link-Seite mit eigenen
  DB-Abfragen (>5000 Queries bei 1072 Links) -- das erledigt jetzt gebündelt
  `LinkVisibilityIndex`.

Geprüft werden hier beides: dass die Zähler stimmen, dass die Sichtbarkeit über
Projektgrenzen unverändert greift, und dass die Query-Anzahl nicht mehr mit der
Anzahl der Links wächst.
"""

import pytest
from sqlalchemy import event

from core.db_setup import engine
from models.database import (
    DocumentChunk,
    KnowledgeLink,
    Project,
    ProjectMembership,
    KnowledgeSource,
    Team,
    User,
)
from tests.conftest import TEST_MEMBER_USERNAME


@pytest.fixture
def linked_chunks(db_session, test_project):
    """Zwei Chunks im sichtbaren Testprojekt plus Links in allen drei Status.

    Die Tests laufen gegen die konfigurierte Entwicklungs-DB (siehe conftest),
    in der schon Links liegen können -- deshalb liefert die Fixture die vorher
    gezählten Bestände mit, und die Tests prüfen die Differenz."""
    baseline = {
        status: db_session.query(KnowledgeLink).filter(KnowledgeLink.status == status).count()
        for status in ("pending", "approved", "rejected")
    }
    baseline_high_score = (
        db_session.query(KnowledgeLink)
        .filter(KnowledgeLink.status == "pending", KnowledgeLink.score >= 0.95)
        .count()
    )
    chunks = [
        DocumentChunk(
            project_id=test_project, file_path=f"doc{i}.md", content="x", start_line=1, end_line=2
        )
        for i in range(2)
    ]
    db_session.add_all(chunks)
    db_session.commit()

    links = []
    # 3x pending, 2x approved, 1x rejected -- ungleiche Zahlen, damit ein
    # vertauschter Zähler auffällt.
    for status, count in (("pending", 3), ("approved", 2), ("rejected", 1)):
        for _ in range(count):
            links.append(
                KnowledgeLink(
                    source_a_type="document",
                    source_a_chunk_id=chunks[0].id,
                    source_a_title="A",
                    source_b_type="document",
                    source_b_chunk_id=chunks[1].id,
                    source_b_title="B",
                    score=0.9,
                    status=status,
                )
            )
    db_session.add_all(links)
    db_session.commit()

    yield {"baseline": baseline, "baseline_high_score": baseline_high_score}

    db_session.query(KnowledgeLink).filter(
        KnowledgeLink.id.in_([link.id for link in links])
    ).delete(synchronize_session=False)
    db_session.query(DocumentChunk).filter(DocumentChunk.id.in_([c.id for c in chunks])).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_counts_endpoint_liefert_zahlen_je_status(client, linked_chunks):
    res = client.get("/knowledge-links/counts")
    assert res.status_code == 200
    counts = res.json()
    baseline = linked_chunks["baseline"]
    assert counts["pending"] == baseline["pending"] + 3
    assert counts["approved"] == baseline["approved"] + 2
    assert counts["rejected"] == baseline["rejected"] + 1


def test_counts_endpoint_beachtet_min_score(client, linked_chunks):
    # Die Testlinks liegen bei 0.9 -- eine höhere Schwelle muss sie herausfiltern,
    # genau wie der Score-Filter der Liste es tut.
    high = client.get("/knowledge-links/counts?min_score=0.95").json()
    low = client.get("/knowledge-links/counts?min_score=0.5").json()
    assert high["pending"] == linked_chunks["baseline_high_score"]
    assert low["pending"] == linked_chunks["baseline"]["pending"] + 3


def test_counts_endpoint_braucht_anmeldung(unauthenticated_client):
    assert unauthenticated_client.get("/knowledge-links/counts").status_code == 401


def test_fremdes_projekt_bleibt_unsichtbar(member_client, db_session):
    """Regressionsschutz für die gebündelte Sichtbarkeitsprüfung: ein Link auf
    Chunks eines Projekts ohne Mitgliedschaft darf weder gelistet noch gezählt
    werden."""
    team = Team(name="O-165 Fremdteam")
    db_session.add(team)
    db_session.commit()
    foreign = Project(name="O-165 Fremdprojekt", team_id=team.id)
    db_session.add(foreign)
    db_session.commit()

    chunks = [
        DocumentChunk(
            project_id=foreign.id, file_path=f"f{i}.md", content="x", start_line=1, end_line=2
        )
        for i in range(2)
    ]
    db_session.add_all(chunks)
    db_session.commit()
    link = KnowledgeLink(
        source_a_type="document",
        source_a_chunk_id=chunks[0].id,
        source_a_title="Fremd A",
        source_b_type="document",
        source_b_chunk_id=chunks[1].id,
        source_b_title="Fremd B",
        score=0.9,
        status="pending",
    )
    db_session.add(link)
    db_session.commit()

    try:
        titles = [
            item["source_a"]["title"] for item in member_client.get("/knowledge-links").json()
        ]
        assert "Fremd A" not in titles
        # Der Zähler darf den unsichtbaren Link ebenso wenig mitzählen wie die Liste.
        counts_before = member_client.get("/knowledge-links/counts").json()

        # Mit Team- und Projektmitgliedschaft wird derselbe Link sichtbar --
        # sonst würde der Test auch bei kaputter Prüfung „grün durch nichts".
        db_session.add(
            ProjectMembership(project_id=foreign.id, user_id=_member_id(db_session), role="member")
        )
        from models.database import TeamMembership

        db_session.add(TeamMembership(user_id=_member_id(db_session), team_id=team.id))
        db_session.commit()

        titles = [
            item["source_a"]["title"] for item in member_client.get("/knowledge-links").json()
        ]
        assert "Fremd A" in titles
        counts_after = member_client.get("/knowledge-links/counts").json()
        assert counts_after["pending"] == counts_before["pending"] + 1
    finally:
        from models.database import TeamMembership

        db_session.query(TeamMembership).filter(TeamMembership.team_id == team.id).delete()
        db_session.query(ProjectMembership).filter(
            ProjectMembership.project_id == foreign.id
        ).delete()
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.query(DocumentChunk).filter(DocumentChunk.id.in_([c.id for c in chunks])).delete(
            synchronize_session=False
        )
        db_session.query(Project).filter(Project.id == foreign.id).delete()
        db_session.query(Team).filter(Team.id == team.id).delete()
        db_session.commit()


def _member_id(db_session) -> int:
    return db_session.query(User).filter(User.username == TEST_MEMBER_USERNAME).first().id


def test_liste_skaliert_ohne_query_pro_link(member_client, db_session, test_project):
    """Die Query-Anzahl der Liste darf nicht mit der Anzahl der Links wachsen.

    Vorher machte jede Link-Seite eigene Abfragen; bei 1072 Vorschlägen waren
    das über 5000 Queries und ~1,4 s allein im Backend."""
    source = KnowledgeSource(
        name="O-165 Quelle",
        type="Local",
        team_id=db_session.query(Project).filter(Project.id == test_project).first().team_id,
        project_id=test_project,
    )
    db_session.add(source)
    db_session.commit()

    chunks = [
        DocumentChunk(
            project_id=test_project,
            source_id=source.id,
            file_path=f"s{i}.md",
            content="x",
            start_line=1,
            end_line=2,
        )
        for i in range(40)
    ]
    db_session.add_all(chunks)
    db_session.commit()

    links = [
        KnowledgeLink(
            source_a_type="document",
            source_a_chunk_id=chunks[i].id,
            source_a_title=f"A{i}",
            source_b_type="document",
            source_b_chunk_id=chunks[(i + 1) % len(chunks)].id,
            source_b_title=f"B{i}",
            score=0.7,
            status="pending",
        )
        for i in range(len(chunks))
    ]
    db_session.add_all(links)
    db_session.commit()

    queries = []

    def _record(conn, cursor, statement, *args):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        res = member_client.get("/knowledge-links?status=pending")
        assert res.status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _record)
        db_session.query(KnowledgeLink).filter(
            KnowledgeLink.id.in_([link.id for link in links])
        ).delete(synchronize_session=False)
        db_session.query(DocumentChunk).filter(DocumentChunk.id.in_([c.id for c in chunks])).delete(
            synchronize_session=False
        )
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()

    # Konstante Obergrenze: Auth, Link-Query und die gebündelten Nachschlage-
    # Abfragen. Ohne den Index wären es allein >80 (zwei pro Link-Seite).
    assert len(queries) < 20, f"{len(queries)} Queries für 40 Links:\n" + "\n".join(queries)
