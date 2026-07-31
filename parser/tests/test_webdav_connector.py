import pytest
from sqlalchemy import text
from unittest.mock import patch, MagicMock, AsyncMock
from db import SessionLocal
from models.database import KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.webdav import WebdavConnector, _parse_webdav_xml


class _MockStream:
    """Async-Context-Manager, der client.stream() nachbildet (gestreamter Download)."""
    def __init__(self, content: bytes):
        self._content = content
        self.raise_for_status = MagicMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self, chunk_size=None):
        yield self._content


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_source(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "webdav-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "webdav-test-project", "team_id": team_id},
    ).scalar_one()
    
    # We create a WebDAV knowledge source
    source = KnowledgeSource(
        name="Test WebDAV",
        type="WebDAV",
        url="https://example.com/dav/",
        token='{"username": "testuser", "password": "testpassword"}',
        project_id=project_id,
        team_id=team_id
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    yield source

    # Cleanup
    db_session.query(SourceScanFile).filter(SourceScanFile.source_id == source.id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def test_parse_webdav_xml():
    xml_data = b"""<?xml version="1.0" encoding="utf-8" ?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/user/folder/file.txt</d:href>
    <d:propstat>
      <d:prop>
        <d:getcontentlength>500</d:getcontentlength>
        <d:getlastmodified>Thu, 28 Nov 2024 10:20:00 GMT</d:getlastmodified>
        <d:resourcetype/>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/user/folder/subfolder/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""
    res = _parse_webdav_xml(xml_data)
    assert len(res) == 2
    
    file_item = next(item for item in res if not item["is_dir"])
    assert file_item["href"] == "/remote.php/dav/files/user/folder/file.txt"
    assert file_item["size"] == 500
    assert file_item["last_modified"] == "Thu, 28 Nov 2024 10:20:00 GMT"

    dir_item = next(item for item in res if item["is_dir"])
    assert dir_item["href"] == "/remote.php/dav/files/user/folder/subfolder/"


@pytest.mark.anyio
async def test_webdav_connector_sync_flow(db_session, test_source):
    connector = WebdavConnector(test_source.id)
    
    # Mock files on the WebDAV server
    # 1. A text file
    propfind_xml = b"""<?xml version="1.0" encoding="utf-8" ?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/dav/file1.txt</d:href>
    <d:propstat>
      <d:prop>
        <d:getcontentlength>100</d:getcontentlength>
        <d:getlastmodified>Fri, 29 Nov 2024 12:00:00 GMT</d:getlastmodified>
        <d:resourcetype/>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""

    # We mock httpx request calls
    async def mock_request(method, url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if method == "PROPFIND":
            resp.content = propfind_xml
        elif method == "GET":
            resp.content = b"Hello from WebDAV file content!"
        return resp

    # Downloads laufen über client.stream() (chunked auf Platte) — als async
    # Context-Manager mit aiter_bytes() mocken.
    def mock_stream(method, url, **kwargs):
        return _MockStream(b"Hello from WebDAV file content!")

    # Setup database with an existing scan file record (that was deleted/orphaned on the server)
    old_record = SourceScanFile(
        source_id=test_source.id,
        file_path="https://example.com/dav/deleted_file.txt",
        content_hash="oldhash"
    )
    db_session.add(old_record)
    db_session.commit()

    connector.source = test_source

    mock_get_embedding = AsyncMock(return_value=[0.1] * 1024)

    with patch("httpx.AsyncClient.request", side_effect=mock_request), \
         patch("httpx.AsyncClient.stream", side_effect=mock_stream), \
         patch("connectors.base.get_embedding", mock_get_embedding):
        
        # Run fetch_documents to trigger scanning and yielding
        docs = []
        async for doc in connector.fetch_documents():
            docs.append(doc)
        
        # Run sync to clean up orphans and save scan records
        await connector.sync()

    # Assertions
    assert len(docs) == 1
    assert docs[0]["title"] == "file1.txt"
    assert docs[0]["content"] == "Hello from WebDAV file content!"
    assert docs[0]["source_type"] == "WebDAV"

    # Verify that SourceScanFile now has the new record and the old deleted record is removed (orphan cleanup)
    records = db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).all()
    assert len(records) == 1
    assert records[0].file_path == "https://example.com/dav/file1.txt"
    
    # Clean up of chunks
    deleted_chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "https://example.com/dav/deleted_file.txt"
    ).all()
    assert len(deleted_chunks) == 0
