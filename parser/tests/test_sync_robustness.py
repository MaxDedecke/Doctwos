"""Absturzfestigkeit der Syncs: Sperre mit Herzschlag, Wiederherstellung, Zeitlimits, gepuffertes Sync-Log."""

import asyncio
import time

import pytest
from sqlalchemy import text

import parse_pool
import worker
from connectors.base import BaseConnector
from core import sync_lock
from db import SessionLocal
from doctus_models.database import KnowledgeSource
from tasks import recovery


@pytest.fixture
def source_ids():
    db = SessionLocal()
    team = db.execute(
        text("INSERT INTO teams (name, created_at) VALUES ('robust', now()) RETURNING id")
    ).scalar_one()
    created = []

    def make(status: str) -> int:
        source = KnowledgeSource(
            name=f"robust-{status}", type="git", team_id=team, sync_status=status
        )
        db.add(source)
        db.commit()
        created.append(source.id)
        return source.id

    yield make
    for source_id in created:
        sync_lock._client.delete(sync_lock.lock_key(source_id))
    db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(created)).delete()
    db.execute(text("DELETE FROM teams WHERE id = :t"), {"t": team})
    db.commit()
    db.close()


def _status(source_id: int) -> tuple[str, str | None]:
    db = SessionLocal()
    try:
        source = db.get(KnowledgeSource, source_id)
        return source.sync_status, source.last_error
    finally:
        db.close()


def test_the_lock_admits_one_owner_and_its_heartbeat_keeps_it_alive(source_ids, monkeypatch):
    source_id = source_ids("completed")
    monkeypatch.setattr(sync_lock, "LEASE_SECONDS", 2)
    monkeypatch.setattr(sync_lock, "HEARTBEAT_SECONDS", 0.3)
    first, second = sync_lock.SyncLock(source_id), sync_lock.SyncLock(source_id)

    assert first.acquire()
    assert not second.acquire()
    time.sleep(3)  # länger als die Lease: nur der Herzschlag hält die Sperre
    assert sync_lock.is_held(source_id)

    second.release()  # fremder Besitzer gibt nichts frei
    assert sync_lock.is_held(source_id)
    sync_lock.release_all()
    assert not sync_lock.is_held(source_id)


def test_a_sync_without_its_lock_is_ended_with_a_message_and_a_running_one_is_left_alone(
    source_ids,
):
    interrupted, running = source_ids("syncing"), source_ids("syncing")
    lock = sync_lock.SyncLock(running)
    assert lock.acquire()
    try:
        assert interrupted in recovery.recover_interrupted_syncs()
        assert _status(interrupted) == ("error", recovery.INTERRUPTED_MESSAGE)
        assert _status(running) == ("syncing", None)
    finally:
        lock.release()


def test_a_sync_over_its_time_limit_ends_with_an_error_and_frees_its_lock(source_ids):
    source_id = source_ids("syncing")

    async def hanging_sync():
        lock = sync_lock.SyncLock(source_id)
        assert lock.acquire()
        await asyncio.sleep(30)

    with pytest.raises(TimeoutError):
        worker._run_source_task(source_id, hanging_sync(), 1)

    status, message = _status(source_id)
    assert status == "error" and "Zeitlimit" in message
    assert not sync_lock.is_held(source_id)


class _Connector(BaseConnector):
    async def fetch_documents(self):
        return
        yield


def test_the_sync_log_is_written_in_batches_and_keeps_its_newest_lines(source_ids, monkeypatch):
    source_id = source_ids("syncing")
    monkeypatch.setattr("connectors.base.SYNC_LOG_MAX_CHARS", 200)
    connector = _Connector(source_id)
    connector.source = connector.db.get(KnowledgeSource, source_id)
    try:
        connector._log("erste Zeile")
        connector._log("zweite Zeile")
        assert _status(source_id)[0] == "syncing"
        db = SessionLocal()
        assert "zweite Zeile" not in (db.get(KnowledgeSource, source_id).sync_log or "")
        db.close()

        for index in range(20):
            connector._log(f"Zeile {index:02d}")
        connector._flush_log(final=True)

        db = SessionLocal()
        log = db.get(KnowledgeSource, source_id).sync_log
        db.close()
        assert log.startswith("[… ältere Zeilen gekürzt …]")
        assert "Zeile 19" in log and "erste Zeile" not in log
        assert len(log) <= 200 + len("[… ältere Zeilen gekürzt …]\n")
    finally:
        connector.db.close()


def _alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/status") as status:
            return "zombie" not in status.read()
    except FileNotFoundError:
        return False


def test_a_hanging_file_gets_a_time_limit_and_its_pool_is_ended(monkeypatch):
    monkeypatch.setattr(parse_pool, "PARSE_FILE_TIMEOUT", 1.0)
    pool = parse_pool.create_pool(1, {})
    try:
        asyncio.run(parse_pool.run_with_timeout(pool, parse_pool._ping))  # Pool läuft
        pids = list(pool._processes)
        with pytest.raises(parse_pool.ParseTimeout):
            asyncio.run(parse_pool.run_with_timeout(pool, time.sleep, 30))
        # Den beendeten Prozess sammelt der Verwaltungs-Thread des Pools ein; geprüft wird daher die PID.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
            time.sleep(0.1)
        assert not any(_alive(pid) for pid in pids)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
