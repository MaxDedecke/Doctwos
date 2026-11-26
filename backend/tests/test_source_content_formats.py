"""Dokumentansicht: Formate, die nur der Parser liest, zeigen den beim Import extrahierten Text aus dem Index."""

import io

import pytest

import api.knowledge_sources as ks_api
from codena_models.database import DocumentChunk, KnowledgeSource, Project
from services.source_file_text import assemble_chunks

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
INDEXED = ["Titel der Vorlage", "", "Absatz eins mit Umlauten: äöü", "Absatz zwei", "Schluss"]


def _docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# Je Format ein Dateiinhalt, wie er auf dem Server liegt; das Backend liest ihn nicht selbst.
FILE_BYTES = {
    ".doc": OLE_MAGIC + b"\x00" * 504 + "Word-97-Binärdaten".encode("utf-16-le"),
    ".rtf": rb"{\rtf1\ansi\deff0 {\fonttbl{\f0 Arial;}}\f0 Titel der Vorlage\par}",
    ".xlsx": b"PK\x03\x04" + b"\x00" * 64,
    ".pptx": b"PK\x03\x04" + b"\x00" * 64,
    ".odt": b"PK\x03\x04" + b"\x00" * 64,
    ".ods": b"PK\x03\x04" + b"\x00" * 64,
    ".odp": b"PK\x03\x04" + b"\x00" * 64,
    ".csv": "Spalte;Wert\r\nMünchen;1\r\n".encode("cp1252"),
    ".html": b"<html><body><h1>Titel der Vorlage</h1><script>x()</script></body></html>",
    ".htm": b"<html><body><p>Titel der Vorlage</p></body></html>",
}


@pytest.fixture
def make_source(db_session, test_project, tmp_path, monkeypatch):
    team_id = db_session.query(Project).filter(Project.id == test_project).first().team_id
    monkeypatch.setattr(ks_api, "UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(ks_api, "REPOS_ROOT", str(tmp_path / "repos"))
    watched = tmp_path / "watched"
    watched.mkdir()
    monkeypatch.setattr(ks_api, "WATCHED_ROOT", str(watched))
    (tmp_path / "uploads").mkdir()
    created = []

    def make(kind, name, spaces=None):
        source = KnowledgeSource(
            name=name, type=kind, project_id=test_project, team_id=team_id, spaces=spaces or {}
        )
        db_session.add(source)
        db_session.commit()
        created.append(source)
        return source

    make.uploads = tmp_path / "uploads"
    make.watched = watched
    make.repos = tmp_path / "repos"
    yield make
    for source in created:
        db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
        db_session.delete(source)
    db_session.commit()


def _index(db_session, source, key, chunks):
    for content, start, end in chunks:
        db_session.add(
            DocumentChunk(
                project_id=source.project_id,
                source_id=source.id,
                file_path=key,
                content=content,
                start_line=start,
                end_line=end,
                metadata_json={"language": "text", "page": None},
            )
        )
    db_session.commit()


# Überlappende Chunks, wie chunk_file sie für INDEXED erzeugt: der zweite wiederholt Zeile 3.
OVERLAPPING = [("\n".join(INDEXED[:3]), 1, 3), ("\n".join(INDEXED[2:]), 3, 5)]


def _upload(make_source, db_session, ext, payload=None):
    name = f"vorlage{ext}"
    (make_source.uploads / name).write_bytes(payload if payload is not None else FILE_BYTES[ext])
    source = make_source("Local", name, {"path": name})
    return source


@pytest.mark.parametrize("ext", sorted(FILE_BYTES))
def test_an_uploaded_document_shows_the_text_extracted_at_import(
    client, make_source, db_session, ext
):
    source = _upload(make_source, db_session, ext)
    _index(db_session, source, source.name, OVERLAPPING)

    res = client.get(f"/knowledge-sources/{source.id}/content", params={"path": source.name})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"content": "\n".join(INDEXED), "format": "text", "origin": "index"}


def test_a_word_97_document_without_index_reports_the_missing_import_instead_of_a_500(
    client, make_source, db_session
):
    source = _upload(make_source, db_session, ".doc")

    res = client.get(f"/knowledge-sources/{source.id}/content")

    assert res.status_code == 404
    assert "indexierter Text" in res.json()["detail"]


def test_a_docx_is_still_rendered_as_html(client, make_source, db_session):
    source = _upload(make_source, db_session, ".docx", _docx_bytes("Hallo Welt"))

    res = client.get(f"/knowledge-sources/{source.id}/content")

    assert res.status_code == 200
    assert res.json() == {"content": "<p>Hallo Welt</p>", "format": "html"}


def test_a_doc_that_is_really_a_docx_is_rendered_as_html(client, make_source, db_session):
    source = _upload(make_source, db_session, ".doc", _docx_bytes("Umbenannt"))

    res = client.get(f"/knowledge-sources/{source.id}/content")

    assert res.json() == {"content": "<p>Umbenannt</p>", "format": "html"}


def test_a_broken_docx_falls_back_to_the_index(client, make_source, db_session):
    source = _upload(make_source, db_session, ".docx", b"PK\x03\x04kaputt")
    _index(db_session, source, source.name, OVERLAPPING)

    res = client.get(f"/knowledge-sources/{source.id}/content")

    assert res.status_code == 200
    assert res.json()["content"] == "\n".join(INDEXED)


def test_a_folder_document_is_found_under_its_storage_key(client, make_source, db_session):
    file_path = make_source.watched / "ordner" / "bericht.doc"
    file_path.parent.mkdir()
    file_path.write_bytes(FILE_BYTES[".doc"])
    source = make_source("FolderWatch", "ordner", {"folder_path": str(make_source.watched)})
    _index(db_session, source, str(file_path), OVERLAPPING)

    res = client.get(f"/knowledge-sources/{source.id}/content", params={"path": str(file_path)})

    assert res.status_code == 200
    assert res.json()["content"] == "\n".join(INDEXED)


def test_a_csv_in_a_git_repository_stays_raw_source(client, make_source, db_session):
    source = make_source("Git", "repo")
    worktree = make_source.repos / "wt" / f"ks_{source.id}"
    worktree.mkdir(parents=True)
    (worktree / "daten.csv").write_text("a;b\n1;2\n")
    _index(db_session, source, "daten.csv", [("anders", 1, 1)])

    res = client.get(f"/knowledge-sources/{source.id}/content", params={"path": "daten.csv"})

    assert res.json() == {"content": "a;b\n1;2\n", "format": "text"}


def test_pages_are_assembled_separately(client, make_source, db_session):
    source = _upload(make_source, db_session, ".pptx")
    for page, text in ((2, "Folie zwei"), (1, "Folie eins")):
        db_session.add(
            DocumentChunk(
                project_id=source.project_id,
                source_id=source.id,
                file_path=source.name,
                content=text,
                start_line=1,
                end_line=1,
                metadata_json={"page": page},
            )
        )
    db_session.commit()

    res = client.get(f"/knowledge-sources/{source.id}/content")

    assert res.json()["content"] == "Folie eins\n\nFolie zwei"


# ── Zusammensetzen der Chunks ────────────────────────────────────────────────


def test_overlapping_chunks_keep_each_line_once_at_its_number():
    assert assemble_chunks(reversed(OVERLAPPING)) == "\n".join(INDEXED)


def test_an_oversized_line_split_into_pieces_is_joined_again():
    chunks = [
        ("kurz", 1, 1),
        ("Erster Satz einer langen Zeile.", 2, 2),
        ("Zweiter Satz derselben Zeile.", 2, 2),
        ("danach", 3, 3),
    ]

    assert assemble_chunks(chunks) == (
        "kurz\nErster Satz einer langen Zeile. Zweiter Satz derselben Zeile.\ndanach"
    )


def test_merged_small_chunks_lose_their_inner_overlap():
    # _merge_small_chunks hängt [a1, a2] und die Wiederholung [a2] zu einem Chunk über die Zeilen 1–2 zusammen.
    assert assemble_chunks([("a1\na2\na2", 1, 2), ("a2\nb", 2, 3)]) == "a1\na2\nb"


def test_merged_pieces_of_one_line_become_that_line():
    assert assemble_chunks([("Teil eins.\nTeil zwei.", 4, 4)]) == "\n\n\nTeil eins. Teil zwei."


def test_lines_without_chunk_stay_empty_so_numbers_do_not_shift():
    assert assemble_chunks([("eins", 1, 1), ("drei", 3, 3)]) == "eins\n\ndrei"
