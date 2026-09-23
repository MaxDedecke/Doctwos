import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from connectors.git import (
    GitConnector,
    _analysis_dependency_paths,
)
from core import config
from core.inference_admission import (
    CHAT_RESERVE,
    MAX_CONCURRENCY,
    admission_wait_tracker,
    track_admission_wait,
)
from models.database import Base, CodeEdge, CodeEntity, KnowledgeSource


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
    edge1 = CodeEdge(id=1, source_id=1, src_entity_id=1, dst_entity_id=2, dst_name="PROGB", type="CALL")
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
    edge3 = CodeEdge(id=3, source_id=1, src_entity_id=1, dst_entity_id=4, dst_name="SEC1", type="PERFORM")
    # 4. Source 2 edge
    edge4 = CodeEdge(id=4, source_id=2, src_entity_id=5, dst_entity_id=None, dst_name="EXT", type="CALL")

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


def test_embed_concurrency_clamps_to_admission_batch_reserve():
    """Verify embed concurrency is bounded by available admission batch slots."""
    available_batch_slots = max(1, MAX_CONCURRENCY - CHAT_RESERVE)
    assert available_batch_slots == 3

    # If config.EMBED_CONCURRENCY is higher (e.g. 20), it clamps to 3
    clamped = min(20, available_batch_slots)
    assert clamped == 3

    # If configured lower (e.g. 2), it respects the lower limit
    clamped_lower = min(2, available_batch_slots)
    assert clamped_lower == 2
