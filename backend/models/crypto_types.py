"""
backend/models/crypto_types.py
================================
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
backend/api/chat.py (_hybrid_chunk_search) und
parser/tasks/link_builder.py (_pass_keyword).

Schlüssel kommt aus MASTER_ENCRYPTION_KEY (Fernet-Key, 32 Byte urlsafe-base64).
Rotation des Schlüssels erfordert ein Neu-Verschlüsseln aller bestehenden
Werte — das ist hier bewusst nicht automatisiert, siehe docs/DEPLOYMENT.md.
Bestehende Klartextdaten in den content-Spalten werden beim Upgrade auf diese
Version per Alembic-Migration nachträglich verschlüsselt (siehe
alembic/versions/d4e5f6a7b8c9_encrypt_content_at_rest.py).
"""

import os

from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


def _get_fernet() -> Fernet:
    key = os.getenv("MASTER_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "MASTER_ENCRYPTION_KEY ist nicht gesetzt. "
            "Generieren mit: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
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
