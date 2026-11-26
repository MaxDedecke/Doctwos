"""Kundenbranding: Prüfung der Eingaben und Lesen/Schreiben der einen Konfigurationszeile.

Erlaubt ist nur, was an festen Plätzen erscheint (Name, zwei Logos, eine Akzentfarbe,
Login-Hinweis und drei Links). Die abgeleiteten Farbtöne mit garantiertem Kontrast
berechnet das Frontend (`frontend/lib/branding.ts`); hier wird nur das Format geprüft.
"""

import re
import struct
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from codena_models.database import CorporateBranding

BRANDING_ID = 1
LOGO_VARIANTS = ("light", "dark")
MAX_LOGO_BYTES = 256 * 1024
MAX_LOGO_EDGE = 2048
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class BrandingError(ValueError):
    pass


def get_branding(db: Session) -> Optional[CorporateBranding]:
    return db.get(CorporateBranding, BRANDING_ID)


def _get_or_create(db: Session) -> CorporateBranding:
    row = get_branding(db)
    if row is None:
        row = CorporateBranding(id=BRANDING_ID, revision=1)
        db.add(row)
        db.flush()
    return row


def _clean_text(
    value: Optional[str], max_len: int, field: str, multiline: bool = False
) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    check = text.replace("\n", "") if multiline else text
    if _CONTROL_CHARS.search(check):
        raise BrandingError(f"{field}: Steuerzeichen sind nicht erlaubt.")
    if len(text) > max_len:
        raise BrandingError(f"{field}: höchstens {max_len} Zeichen.")
    return text


def clean_color(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    color = value.strip()
    if not _HEX_COLOR.match(color):
        raise BrandingError("Akzentfarbe: bitte als Hexwert #RRGGBB angeben.")
    return color.lower()


def clean_url(value: Optional[str], field: str, allow_mailto: bool = False) -> Optional[str]:
    url = _clean_text(value, 500, field)
    if url is None:
        return None
    if any(ch.isspace() for ch in url):
        raise BrandingError(f"{field}: Leerzeichen sind in Adressen nicht erlaubt.")
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url
    if allow_mailto and parsed.scheme == "mailto" and "@" in parsed.path:
        return url
    allowed = "https://, http://" + (" oder mailto:" if allow_mailto else "")
    raise BrandingError(f"{field}: nur Adressen mit {allowed} sind erlaubt.")


def validate_png(data: bytes) -> None:
    """Nur echte PNGs in begrenzter Größe: Bilder werden ungeprüft öffentlich ausgeliefert."""
    if len(data) > MAX_LOGO_BYTES:
        raise BrandingError(f"Logo: höchstens {MAX_LOGO_BYTES // 1024} KB.")
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise BrandingError("Logo: nur PNG-Dateien sind erlaubt.")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= MAX_LOGO_EDGE and 0 < height <= MAX_LOGO_EDGE):
        raise BrandingError(f"Logo: höchstens {MAX_LOGO_EDGE} × {MAX_LOGO_EDGE} Pixel.")


def update_settings(db: Session, payload: dict, user_id: Optional[int]) -> CorporateBranding:
    values = {
        "customer_name": _clean_text(payload.get("customer_name"), 60, "Name"),
        "accent_color": clean_color(payload.get("accent_color")),
        "login_notice": _clean_text(
            payload.get("login_notice"), 280, "Hinweistext", multiline=True
        ),
        "imprint_url": clean_url(payload.get("imprint_url"), "Impressum"),
        "privacy_url": clean_url(payload.get("privacy_url"), "Datenschutz"),
        "support_url": clean_url(payload.get("support_url"), "Support", allow_mailto=True),
    }
    row = _get_or_create(db)
    for key, value in values.items():
        setattr(row, key, value)
    row.revision = (row.revision or 0) + 1
    row.updated_by_user_id = user_id
    db.commit()
    db.refresh(row)
    return row


def set_logo(
    db: Session, variant: str, data: Optional[bytes], user_id: Optional[int]
) -> CorporateBranding:
    if variant not in LOGO_VARIANTS:
        raise BrandingError("Unbekannte Logo-Variante.")
    if data is not None:
        validate_png(data)
    row = _get_or_create(db)
    setattr(row, f"logo_{variant}", data)
    row.revision = (row.revision or 0) + 1
    row.updated_by_user_id = user_id
    db.commit()
    db.refresh(row)
    return row


def reset(db: Session) -> None:
    row = get_branding(db)
    if row is not None:
        db.delete(row)
        db.commit()


def to_public(row: Optional[CorporateBranding]) -> dict:
    if row is None:
        return {
            "customer_name": None,
            "accent_color": None,
            "login_notice": None,
            "imprint_url": None,
            "privacy_url": None,
            "support_url": None,
            "logo_light_url": None,
            "logo_dark_url": None,
            "revision": 0,
        }

    def logo(variant: str) -> Optional[str]:
        if not getattr(row, f"logo_{variant}"):
            return None
        return f"/config/branding/logo/{variant}?r={row.revision}"

    return {
        "customer_name": row.customer_name,
        "accent_color": row.accent_color,
        "login_notice": row.login_notice,
        "imprint_url": row.imprint_url,
        "privacy_url": row.privacy_url,
        "support_url": row.support_url,
        "logo_light_url": logo("light"),
        "logo_dark_url": logo("dark"),
        "revision": row.revision,
    }
