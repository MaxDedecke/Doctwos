from types import SimpleNamespace

import pytest

from tasks import cross_link_builder


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _RunQuery:
    def __init__(self, run):
        self.run = run

    def filter(self, *_conditions):
        return self

    def first(self):
        return self.run


class _Session:
    def __init__(self, run):
        self.run = run
        self.closed = False
        self.commits = 0

    def query(self, _model):
        return _RunQuery(self.run)

    def close(self):
        self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["cancelled", "failed", "completed", "running"])
async def test_non_pending_knowledge_link_runs_are_not_started(monkeypatch, status):
    run = SimpleNamespace(id=71, status=status, scope_json=None)
    session = _Session(run)
    monkeypatch.setattr(cross_link_builder, "SessionLocal", lambda: session)

    await cross_link_builder.compute_knowledge_links_async(run.id)

    assert run.status == status
    assert session.commits == 0
    assert session.closed
