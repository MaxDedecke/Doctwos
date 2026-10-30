import asyncio
import os
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from connectors.git import (
    GitConnector,
    _analysis_dependency_paths,
)
from core.inference_admission import (
    admission_wait_tracker,
    track_admission_wait,
)
from doctus_models.database import Base, CodeEdge, CodeEntity


def test_analysis_dependency_paths_targeted_sql_join():
    """Verify _analysis_dependency_paths returns correct dependencies using SQL join."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Source 1 entities
    e1 = CodeEntity(id=1, source_id=1, file_path="src/PROGA.cbl", name="PROGA", type="program")
    e2 = CodeEntity(id=2, source_id=1, file_path="src/PROGB.cbl", name="PROGB", type="program")
    e3 = CodeEntity(id=3, source_id=1, file_path="src/PROGC.cbl", name="PROGC", type="program")
    e4 = CodeEntity(id=4, source_id=1, file_path="src/PROGA.cbl", name="SEC1", type="section")

    # Source 2 entity (should be isolated)
    e5 = CodeEntity(id=5, source_id=2, file_path="src/OTHER.cbl", name="OTHER", type="program")

    # Edges:
    # 1. PROGA -> PROGB via dst_entity_id
    edge1 = CodeEdge(
        id=1, source_id=1, src_entity_id=1, dst_entity_id=2, dst_name="PROGB", type="CALL"
    )
    # 2. PROGA -> PROGC via meta_json target_file_path
    edge2 = CodeEdge(
        id=2,
        source_id=1,
        src_entity_id=4,
        dst_entity_id=None,
        dst_name="PROGC",
        type="CALL",
        meta_json={"target_file_path": "src/PROGC.cbl"},
    )
    # 3. PROGA -> PROGA (internal paragraph perform in same file, should be filtered)
    edge3 = CodeEdge(
        id=3, source_id=1, src_entity_id=1, dst_entity_id=4, dst_name="SEC1", type="PERFORM"
    )
    # 4. Source 2 edge
    edge4 = CodeEdge(
        id=4, source_id=2, src_entity_id=5, dst_entity_id=None, dst_name="EXT", type="CALL"
    )

    db.add_all([e1, e2, e3, e4, e5, edge1, edge2, edge3, edge4])
    db.commit()

    deps = _analysis_dependency_paths(db, source_id=1)
    assert deps == {"src/PROGA.cbl": {"src/PROGB.cbl", "src/PROGC.cbl"}}

    deps2 = _analysis_dependency_paths(db, source_id=2)
    assert deps2 == {}


def test_track_admission_wait_context_manager():
    """Verify track_admission_wait collects wait times across requests."""
    with track_admission_wait() as wait_times:
        tracker = admission_wait_tracker.get()
        assert tracker is not None
        tracker.append(42)
        tracker.append(18)

    assert wait_times == [42, 18]
    assert sum(wait_times) == 60
    assert admission_wait_tracker.get() is None


@pytest.mark.anyio
async def test_embed_document_fair_batching_and_metrics():
    """Verify large artifact chunks are split into bounded fair batches and metrics are tracked."""
    connector = GitConnector(source_id=-1)
    batch_calls: list[list[str]] = []

    async def mock_get_embeddings_batch(texts, model=None):
        batch_calls.append(texts)
        # simulate some admission wait
        tracker = admission_wait_tracker.get()
        if tracker is not None:
            tracker.append(15)
        return [[0.1] * 1024 for _ in texts]

    # Create a document that produces 50 chunks (approx 1000 chars per chunk)
    large_content = "\n\n".join([f"paragraph {i}: " + ("x" * 800) for i in range(50)])
    doc = {
        "title": "large_data.txt",
        "content": large_content,
        "url": "file:///large_data.txt",
        "source_type": "Git",
        "storage_key": "large_data.txt",
        "extra_meta": {"language": "text"},
    }

    with (
        patch("connectors.git.get_embeddings_batch", side_effect=mock_get_embeddings_batch),
        patch.dict(os.environ, {"EMBED_FAIR_BATCH_SIZE": "20"}),
    ):
        doc_out, chunks, parse_result = await connector._embed_document(doc, asyncio.Semaphore(1))

    assert len(chunks) > 20
    total_chunks = len(chunks)

    # Check fair batching: each call should be at most 20 chunks
    assert len(batch_calls) > 1
    for call in batch_calls:
        assert len(call) <= 20
    assert sum(len(call) for call in batch_calls) == total_chunks

    # Check metrics
    metrics = doc_out["extra_meta"]["metrics"]
    assert metrics["chunk_count"] == total_chunks
    assert metrics["embed_batch_size"] == total_chunks
    assert metrics["parse_duration_ms"] >= 0
    assert metrics["admission_wait_ms"] == 15 * len(batch_calls)


_LONG_LINE = "x" * 20000
_LONG_LINE_SOURCES = {
    "java": (
        "Generated.java",
        "package demo;\n\npublic class Generated {\n"
        f'    String blob = "{_LONG_LINE}";\n'
        "    void run() {}\n}\n",
        4,
    ),
    "cobol": (
        "GENERATED.cbl",
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. GENERATED.\n"
        f"      *{_LONG_LINE}\n"
        "       PROCEDURE DIVISION.\n"
        "           STOP RUN.\n",
        3,
    ),
    "text": ("notes.txt", f"erste Zeile\n{_LONG_LINE}\nletzte Zeile\n", 2),
}


@pytest.mark.anyio
@pytest.mark.parametrize("lang", sorted(_LONG_LINE_SOURCES))
async def test_embed_document_splits_a_line_longer_than_the_embedding_budget(lang):
    """Eine überlange Zeile (generierter Code, Base64) ließ die ganze Datei aus dem Index fallen."""
    name, source, long_line = _LONG_LINE_SOURCES[lang]
    connector = GitConnector(source_id=-1)
    doc = {
        "title": name,
        "content": source,
        "url": f"file:///{name}",
        "source_type": "Git",
        "storage_key": name,
        "extra_meta": {"language": lang},
    }

    async def embeddings(texts, model=None):
        return [[0.1] * 1024 for _ in texts]

    with (
        patch("connectors.git.get_embeddings_batch", side_effect=embeddings),
        patch("connectors.git.get_embedding_input_budget", return_value=8100),
    ):
        _, chunks, _ = await connector._embed_document(doc, asyncio.Semaphore(1))

    assert all(len(chunk["content"].encode("utf-8")) <= 8100 for chunk in chunks)
    assert all("embedding" in chunk for chunk in chunks)
    pieces = [chunk for chunk in chunks if "xxxx" in chunk["content"]]
    assert len(pieces) >= 3
    assert sum(chunk["content"].count("x") for chunk in pieces) >= len(_LONG_LINE)
    # Zeilennummern bleiben physisch: Reine Stücke der langen Zeile zeigen genau auf sie.
    assert all(chunk["start_line"] <= long_line <= chunk["end_line"] for chunk in pieces)


def test_embed_concurrency_clamps_to_admission_batch_reserve(monkeypatch):
    """Embedding concurrency never exceeds the admission slots left after the chat reserve.

    Uses fixed slot numbers: the deployment's INFERENCE_MAX_CONCURRENCY must not
    decide whether this rule holds."""
    import connectors.base as base

    async def gpu(_model):
        return True

    monkeypatch.setattr(base, "MAX_CONCURRENCY", 4)
    monkeypatch.setattr(base, "CHAT_RESERVE", 1)
    monkeypatch.setattr(base, "is_gpu_accelerated", gpu)
    monkeypatch.setattr(base.config, "DOC_CONCURRENCY", 0)
    connector = SimpleNamespace(embedding_model="bge-m3")

    monkeypatch.setattr(base.config, "EMBED_CONCURRENCY", 20)
    assert asyncio.run(base.BaseConnector._doc_concurrency(connector)) == 3

    monkeypatch.setattr(base.config, "EMBED_CONCURRENCY", 2)
    assert asyncio.run(base.BaseConnector._doc_concurrency(connector)) == 2
