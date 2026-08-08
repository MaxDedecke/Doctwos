"""add knowledge_sources.context_note

Kurze, vom Nutzer gepflegte Freitext-Notiz pro Wissensquelle (Markdown erlaubt),
die dem LLM Fachbegriffe/Kontext zu genau dieser Quelle erklärt (z.B. "diese
Confluence-Seiten heißen bei der DRV 'Schlüsselbeschreibungen' und bedeuten
...")

Wird bei Chat-Anfragen serverseitig in den System-Prompt eingehängt (siehe
backend/services/source_context.py) statt ins RAG-Retrieval einzugehen — die
Notiz selbst wird nicht eingebettet/durchsucht, sondern immer dann komplett
mitgeschickt, wenn ihre Quelle im aktuellen Chat-Scope liegt.

Revision ID: 0002_source_context_note
Revises: 0001_doctus_baseline
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_source_context_note"
down_revision = "0001_doctus_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("context_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_sources", "context_note")
