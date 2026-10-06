"""Das Prüfskript scripts/check_confluence.py gegen eine simulierte Confluence-Antwort."""

import importlib.util
import pathlib
import sys

import httpx

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_confluence.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_confluence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_confluence"] = module  # @dataclass sucht das Modul hier
    spec.loader.exec_module(module)
    return module


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_server_instance_passes_every_check():
    module = _load()

    def handler(request):
        path = request.url.path
        if path.startswith("/wiki/"):
            return httpx.Response(404)
        if path.endswith("/space"):
            return httpx.Response(200, json={"results": [{"key": "DOCS"}]})
        if path.endswith("/content"):
            if request.url.params.get("type") == "blogpost":
                return httpx.Response(200, json={"results": []})
            page = {"id": "1", "ancestors": [{"id": "0"}], "body": {"view": {"value": "<p>x</p>"}},
                    "restrictions": {"read": {"restrictions": {"user": {"results": [{"u": 1}]}, "group": {"results": []}}}}}
            return httpx.Response(200, json={"results": [page]})
        return httpx.Response(200, json={"results": []})

    results = module.run_checks(_client(handler), "https://wiki.intern/confluence", "DOCS", None, {})
    assert all(r.ok for r in results), [(r.name, r.detail) for r in results if not r.ok]
    by_name = {r.name: r.detail for r in results}
    assert "Server/Data Center" in by_name["REST-Wurzel"] and "1 mit Elternseiten" in by_name["Seiten"]
    assert by_name["Leseeinschraenkungen"].startswith("1 eingeschraenkte")


def test_wrong_url_reports_the_probed_paths():
    module = _load()
    results = module.run_checks(_client(lambda request: httpx.Response(404)), "https://x", None, None, {})
    assert len(results) == 1 and not results[0].ok and "/rest/api: HTTP 404" in results[0].detail
