"""Gemeinsames Datenmodell von Backend und Parser (SQLAlchemy-ORM und Spaltentypen).

Beide Dienste installieren dieses Paket in ihr Image, statt eine eigene Kopie
zu führen. Schemaänderungen brauchen weiterhin eine Alembic-Migration in
backend/alembic/; die Paketversion wird bei jeder Modelländerung erhöht.
"""

__version__ = "1.1.0"
