"""Hilfen für Connector-Tests: HTTP-Aufrufe der Connectoren (get und request) auf einen Handler umleiten."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch


@contextmanager
def patch_http(handler):
    """``handler(url, **kwargs)`` beantwortet GET-Aufrufe; ohne gesetzten Status gilt HTTP 200."""

    async def answer(url, **kwargs):
        response = await handler(url, **kwargs)
        if isinstance(getattr(response, "status_code", None), MagicMock):
            response.status_code = 200
        return response

    async def mock_request(method, url, **kwargs):
        return await answer(url, **kwargs)

    with patch("httpx.AsyncClient.get", side_effect=answer), patch(
        "httpx.AsyncClient.request", side_effect=mock_request
    ):
        yield
