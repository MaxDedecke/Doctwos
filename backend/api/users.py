from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.db_setup import get_db
from core.teams import require_admin
from models.database import User

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("")
def list_users(db: Session = Depends(get_db)):
    """Nutzerliste. password_hash wird hier bewusst NICHT serialisiert (F-005) —
    ein CI-Job prüft, dass das Feld in keinem Serializer auftaucht."""
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at,
        }
        for u in users
    ]
