"""
backend/core/passwords.py
=========================
Passwort-Hashing (F-005). Genau eine Stelle im Code, an der ein Passwort in einen
Hash übergeht — damit die CI-Prüfung "Passwort taucht nirgends im Klartext auf"
einen einzigen Prüfpunkt hat.

Argon2id (argon2-cffi, MIT) mit den Bibliotheks-Defaults. Bewusst KEIN
EncryptedString: Verschlüsselung wäre reversibel, gefordert ist ein gesalzener,
nicht umkehrbarer Hash.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

_hasher = PasswordHasher()

# Mindestlänge für jedes selbst gesetzte Passwort. Eine Zahl, nicht mehrere:
# /auth/change-password und die Nutzerverwaltung müssen dieselbe Grenze ziehen.
MIN_PASSWORD_LENGTH = 12


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, stored_hash: str) -> bool:
    """False statt Exception bei jedem Misserfolg — der Aufrufer soll nicht
    zwischen 'falsches Passwort' und 'kaputter Hash' unterscheiden müssen."""
    try:
        return _hasher.verify(stored_hash, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def generate_password() -> str:
    """Startpasswort für neu angelegte oder zurückgesetzte Konten. Wird dem
    Administrator genau einmal angezeigt und nirgends gespeichert; der Nutzer muss
    es beim ersten Login wechseln (must_change_password)."""
    return secrets.token_urlsafe(18)
