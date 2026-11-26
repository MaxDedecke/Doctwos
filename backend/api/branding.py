"""
Kundenbranding (Tab „Corporate“ im Konfigurationsdialog).

GET /config/branding und die Logos sind öffentlich, weil die Anmeldeseite sie vor dem
Login zeigt. Ändern dürfen nur Administratoren.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db_setup import get_db
from core.teams import require_admin
from codena_models.database import User
from services import branding

router = APIRouter(prefix="/config/branding", tags=["config"])


class BrandingSettings(BaseModel):
    customer_name: Optional[str] = None
    accent_color: Optional[str] = None
    login_notice: Optional[str] = None
    imprint_url: Optional[str] = None
    privacy_url: Optional[str] = None
    support_url: Optional[str] = None


def _variant(variant: str) -> str:
    if variant not in branding.LOGO_VARIANTS:
        raise HTTPException(status_code=404, detail="Unbekannte Logo-Variante")
    return variant


@router.get("")
def get_branding(db: Session = Depends(get_db)):
    return branding.to_public(branding.get_branding(db))


@router.get("/logo/{variant}")
def get_logo(variant: str, db: Session = Depends(get_db)):
    row = branding.get_branding(db)
    data = getattr(row, f"logo_{_variant(variant)}", None) if row else None
    if not data:
        raise HTTPException(status_code=404, detail="Kein Logo hinterlegt")
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.put("")
def put_branding(
    body: BrandingSettings,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        row = branding.update_settings(db, body.model_dump(), user.id)
    except branding.BrandingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return branding.to_public(row)


@router.put("/logo/{variant}")
async def put_logo(
    variant: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    data = await file.read(branding.MAX_LOGO_BYTES + 1)
    try:
        row = branding.set_logo(db, _variant(variant), data, user.id)
    except branding.BrandingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return branding.to_public(row)


@router.delete("/logo/{variant}")
def delete_logo(
    variant: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    row = branding.set_logo(db, _variant(variant), None, user.id)
    return branding.to_public(row)


@router.delete("")
def reset_branding(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    branding.reset(db)
    return branding.to_public(None)
