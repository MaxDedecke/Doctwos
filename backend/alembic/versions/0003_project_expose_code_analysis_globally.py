"""add projects.expose_code_analysis_globally

Default-deny Opt-in: Code-Analyse-Objekte (CodeEntity, Callgraph) eines Projekts
waren bisher außerhalb des eigenen Projekt-Kontexts sichtbar, sobald der Nutzer
irgendeine Sichtbarkeit auf das Projekt hatte (Team-/Projekt-Mitgliedschaft) —
insbesondere in der "Allgemein"-Suche und im "Allgemein"-Graph-View (kein Projekt
gewählt), wo Analyseergebnisse eigentlich projektspezifisch bleiben sollten (siehe
core/projects.py::assert_project_code_visible_in_context). Dieses Flag macht die
projektübergreifende Sichtbarkeit zu einem expliziten Opt-in, default aus.

Revision ID: 0003_expose_analysis_global
Revises: 0002_source_context_note
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa

# Kurz gehalten (alembic_version.version_num ist varchar(32); "0003_project_expose_code_analysis_globally" wäre zu lang).
revision = "0003_expose_analysis_global"
down_revision = "0002_source_context_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("expose_code_analysis_globally", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("projects", "expose_code_analysis_globally")
