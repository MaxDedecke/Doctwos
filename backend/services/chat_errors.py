"""Fachliche Fehler der Chat-Dienste; api/chat.py übersetzt sie in HTTP-Status."""


class ChatNotFound(LookupError):
    """Nicht vorhanden oder für den Nutzer nicht sichtbar (404)."""


class ChatForbidden(PermissionError):
    """Sichtbar, aber die Aktion ist dem Nutzer nicht erlaubt (403)."""


class ChatInvalid(ValueError):
    """Ungültige Eingabe (400)."""
