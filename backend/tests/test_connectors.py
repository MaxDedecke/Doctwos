from api.connectors import _default_branch_first


def test_default_branch_is_first_without_dropping_provider_order():
    branches = ["develop", "main", "release"]
    assert _default_branch_first(branches, "main") == ["main", "develop", "release"]


def test_default_branch_is_added_when_provider_page_omits_it():
    branches = ["develop", "release"]
    assert _default_branch_first(branches, "main") == ["main", "develop", "release"]


def test_missing_default_branch_is_added_for_paginated_provider_results():
    branches = ["develop", "release"]
    assert _default_branch_first(branches, "trunk") == ["trunk", "develop", "release"]


# --- Verbindungstest Confluence/Jira (On-Prem) -----------------------------------------------

import httpx  # noqa: E402
import pytest  # noqa: E402

from api import connectors  # noqa: E402
from api.schemas import ConnectorTestRequest  # noqa: E402


_REAL_CLIENT = httpx.AsyncClient


def _install_transport(monkeypatch, handler, seen=None):
    real_client = _REAL_CLIENT

    def make_client(*args, **kwargs):
        if seen is not None:
            seen.append(kwargs.get("verify"))
        kwargs.pop("verify", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(connectors.httpx, "AsyncClient", make_client)


@pytest.mark.anyio
async def test_confluence_server_without_wiki_path_and_with_pat_is_accepted(monkeypatch):
    seen_requests = []

    def handler(request):
        seen_requests.append(request)
        if request.url.path == "/confluence/rest/api/space":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    result = await connectors.test_connector(
        ConnectorTestRequest(type="confluence", token="pat-123", url="https://wiki.intern/confluence")
    )
    assert result["success"] is True and "Server/Data Center" in result["message"]
    # Ohne Benutzername: Personal Access Token als Bearer, nicht Basic Auth.
    assert seen_requests[0].headers["Authorization"] == "Bearer pat-123"


@pytest.mark.anyio
async def test_confluence_cloud_is_still_recognised(monkeypatch):
    def handler(request):
        if request.url.path == "/wiki/rest/api/space":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    result = await connectors.test_connector(
        ConnectorTestRequest(type="confluence", username="bot@example.com", token="t", url="https://x.atlassian.net")
    )
    assert result["success"] is True and "Cloud" in result["message"]


@pytest.mark.anyio
async def test_confluence_reports_rejected_credentials_and_unknown_paths_differently(monkeypatch):
    _install_transport(monkeypatch, lambda request: httpx.Response(401))
    denied = await connectors.test_connector(ConnectorTestRequest(type="confluence", token="x", url="https://w"))
    assert denied["success"] is False and "Anmeldung abgelehnt" in denied["message"]

    _install_transport(monkeypatch, lambda request: httpx.Response(404))
    missing = await connectors.test_connector(ConnectorTestRequest(type="confluence", token="x", url="https://w"))
    assert missing["success"] is False and "Kontextpfad" in missing["message"]


@pytest.mark.anyio
async def test_jira_accepts_pat_and_tls_opt_out_is_passed_on(monkeypatch):
    verify_values = []
    _install_transport(monkeypatch, lambda request: httpx.Response(200, json=[]), verify_values)
    result = await connectors.test_connector(
        ConnectorTestRequest(type="jira", token="pat", url="https://jira.intern", verify_ssl=False)
    )
    assert result["success"] is True
    assert verify_values == [False]


@pytest.mark.anyio
async def test_certificate_errors_get_an_actionable_hint(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    _install_transport(monkeypatch, handler)
    result = await connectors.test_connector(ConnectorTestRequest(type="jira", token="t", url="https://jira.intern"))
    assert result["success"] is False and "CUSTOM_CA_BUNDLE" in result["message"]


def test_http_verify_prefers_opt_out_then_ca_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "ca.pem"
    bundle.write_text("x")
    monkeypatch.setenv("CUSTOM_CA_BUNDLE", str(bundle))
    assert connectors._http_verify(False) is False
    assert connectors._http_verify(True) == str(bundle)
    monkeypatch.delenv("CUSTOM_CA_BUNDLE")
    assert connectors._http_verify(True) is True
