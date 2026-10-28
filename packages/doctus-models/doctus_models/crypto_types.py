"""
doctus_models/crypto_types.py
=============================
Transparente At-Rest-Verschlüsselung für Spalten mit Zugangsdaten
(KnowledgeSource.token) UND für Dokumentinhalte (DocumentChunk.content,
ChatMessage.content). Deckt alle über die Connectoren eingelesenen Inhalte ab:
Git, Confluence, Jira, WebDAV, FolderWatch und hochgeladene Dokumente laufen
alle durch DocumentChunk.content.

NICHT für Passwörter: Das Passwortfeld der users-Tabelle ist ein gesalzener Argon2id-Hash
(core/passwords.py), keine reversible Verschlüsselung (F-005).

EncryptedString verschlüsselt beim Schreiben und entschlüsselt beim Lesen über
den SQLAlchemy TypeDecorator-Mechanismus — bestehender Code, der diese Spalten
als Klartext liest/schreibt (Parser-Tasks, Connectoren, mcp_client.py, Chat-
Endpunkte), muss nicht angepasst werden. Nur die Rohdaten auf der Platte sind
Chiffretext. Achtung: SQL-seitige Textsuche (ILIKE/LIKE) auf einer
EncryptedString-Spalte funktioniert nicht mehr (Fernet-Chiffretext ist pro
Verschlüsselung zufällig) — Aufrufer filtern stattdessen nach dem Entschlüsseln
in Python, siehe backend/api/projects.py (_refs_for_document/_refs_for_file),
backend/services/chat_service.py (hybrid_chunk_search) und
parser/tasks/link_builder.py (_pass_keyword).

Schlüssel kommt aus MASTER_ENCRYPTION_KEY (Fernet-Key, 32 Byte urlsafe-base64).
Rotation des Schlüssels erfordert ein Neu-Verschlüsseln aller bestehenden
Werte — das ist hier bewusst nicht automatisiert, siehe docs/DEPLOYMENT.md.
Bestehende Klartextdaten in den content-Spalten werden beim Upgrade auf diese
Version per Alembic-Migration nachträglich verschlüsselt (siehe
backend/alembic/versions/d4e5f6a7b8c9_encrypt_content_at_rest.py).
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    key = os.getenv("MASTER_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "MASTER_ENCRYPTION_KEY ist nicht gesetzt. "
            'Generieren mit: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return _get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return _get_fernet().decrypt(value.encode()).decode()


class EncryptedCredential(EncryptedString):
    """Zugangsdaten (Token, API-Keys): ein mit anderem Schlüssel verschlüsselter Altwert
    wird als „nicht gesetzt“ gelesen, statt jede Abfrage der Zeile mit InvalidToken zu
    kippen. Für Inhaltsspalten gilt das bewusst nicht — dort wäre ein stilles None Datenverlust."""

    cache_ok = True

    def process_result_value(self, value, dialect):
        try:
            return super().process_result_value(value, dialect)
        except InvalidToken:
            logger.error(
                "Zugangsdaten nicht entschlüsselbar (MASTER_ENCRYPTION_KEY passt nicht); "
                "Wert wird als nicht gesetzt behandelt."
            )
            return None
