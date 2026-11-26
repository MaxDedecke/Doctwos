"""Kundenbranding: öffentliches Lesen, Admin-Pflege, Prüfung von Farbe, Links und Logos."""

import struct
import zlib

import pytest

from codena_models.database import CorporateBranding


def _png(width: int = 4, height: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture(autouse=True)
def _clean_branding(db_session):
    db_session.query(CorporateBranding).delete()
    db_session.commit()
    yield
    db_session.rollback()
    db_session.query(CorporateBranding).delete()
    db_session.commit()


def test_public_read_without_login_returns_defaults(unauthenticated_client):
    res = unauthenticated_client.get("/config/branding")
    assert res.status_code == 200
    data = res.json()
    assert data["customer_name"] is None
    assert data["logo_light_url"] is None
    assert data["revision"] == 0


def test_changes_require_login(unauthenticated_client):
    assert (
        unauthenticated_client.put("/config/branding", json={"customer_name": "X"}).status_code
        == 401
    )
    assert unauthenticated_client.delete("/config/branding").status_code == 401


def test_changes_require_admin(member_client):
    assert member_client.put("/config/branding", json={"customer_name": "X"}).status_code == 403
    assert (
        member_client.put(
            "/config/branding/logo/light", files={"file": ("l.png", _png(), "image/png")}
        ).status_code
        == 403
    )
    assert member_client.delete("/config/branding").status_code == 403


def test_admin_saves_settings_and_public_read_sees_them(client, unauthenticated_client):
    res = client.put(
        "/config/branding",
        json={
            "customer_name": "  Beispielkunde  ",
            "accent_color": "#E4002B",
            "login_notice": "Nur für Mitarbeitende.\nZugang über den IT-Service.",
            "imprint_url": "https://intranet.example/impressum",
            "privacy_url": "",
            "support_url": "mailto:it@example.org",
        },
    )
    assert res.status_code == 200, res.text
    public = unauthenticated_client.get("/config/branding").json()
    assert public["customer_name"] == "Beispielkunde"
    assert public["accent_color"] == "#e4002b"
    assert public["privacy_url"] is None
    assert public["support_url"] == "mailto:it@example.org"
    assert public["revision"] >= 2


@pytest.mark.parametrize(
    "payload",
    [
        {"accent_color": "red"},
        {"accent_color": "#12345"},
        {"imprint_url": "javascript:alert(1)"},
        {"privacy_url": "mailto:dpo@example.org"},
        {"support_url": "ftp://example.org"},
        {"customer_name": "x" * 61},
        {"login_notice": "x" * 281},
        {"customer_name": "a\x07b"},
    ],
)
def test_invalid_values_are_rejected(client, payload):
    assert client.put("/config/branding", json=payload).status_code == 422


def test_logo_upload_serve_and_delete(client, unauthenticated_client):
    png = _png()
    res = client.put("/config/branding/logo/dark", files={"file": ("logo.png", png, "image/png")})
    assert res.status_code == 200, res.text
    url = res.json()["logo_dark_url"]
    assert url.startswith("/config/branding/logo/dark?r=")
    assert res.json()["logo_light_url"] is None

    served = unauthenticated_client.get(url)
    assert served.status_code == 200
    assert served.content == png
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    assert client.delete("/config/branding/logo/dark").json()["logo_dark_url"] is None
    assert unauthenticated_client.get("/config/branding/logo/dark").status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"GIF89a" + b"\x00" * 40,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * (256 * 1024),
    ],
)
def test_only_small_pngs_are_accepted(client, data):
    res = client.put("/config/branding/logo/light", files={"file": ("x.png", data, "image/png")})
    assert res.status_code == 422


def test_oversized_png_dimensions_are_rejected(client):
    res = client.put(
        "/config/branding/logo/light", files={"file": ("x.png", _png(4096, 1), "image/png")}
    )
    assert res.status_code == 422


def test_unknown_variant_is_404(client):
    res = client.put("/config/branding/logo/blue", files={"file": ("x.png", _png(), "image/png")})
    assert res.status_code == 404


def test_reset_restores_defaults(client, unauthenticated_client):
    client.put("/config/branding", json={"customer_name": "Beispielkunde"})
    assert client.delete("/config/branding").status_code == 200
    assert unauthenticated_client.get("/config/branding").json()["customer_name"] is None
