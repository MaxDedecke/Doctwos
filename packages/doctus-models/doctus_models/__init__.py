"""Gemeinsames Datenmodell von Backend und Parser (SQLAlchemy-ORM und Spaltentypen,
Rollen der Beziehungsarten, abgeleitete Dateikanten der Graph-Übersicht) sowie Laufzeitbausteine,
die beide Dienste gleich verhalten lassen müssen (Quelltext-Dekodierung, Inferenz-Zulassung).

Beide Dienste installieren dieses Paket in ihr Image, statt eine eigene Kopie
zu führen. Schemaänderungen brauchen weiterhin eine Alembic-Migration in
backend/alembic/; die Paketversion wird bei jeder Modelländerung erhöht.
"""

__version__ = "1.7.1"
