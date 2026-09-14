"""O-150: Varianten von Codeartefakten getrennt persistieren."""

from alembic import op
import sqlalchemy as sa


revision = "0012_evidence_variants"
down_revision = "0011_analysis_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "code_entities",
        sa.Column("variant_key", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.add_column(
        "code_edges",
        sa.Column("variant_key", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.drop_constraint("uq_code_entities_source_qname", "code_entities", type_="unique")
    op.create_unique_constraint(
        "uq_code_entities_source_variant_qname",
        "code_entities",
        ["source_id", "variant_key", "qualified_name"],
    )
    op.create_index("ix_code_entities_variant_key", "code_entities", ["variant_key"])
    op.create_index("ix_code_edges_variant_key", "code_edges", ["variant_key"])


def downgrade() -> None:
    op.drop_index("ix_code_edges_variant_key", table_name="code_edges")
    op.drop_index("ix_code_entities_variant_key", table_name="code_entities")
    op.drop_constraint("uq_code_entities_source_variant_qname", "code_entities", type_="unique")
    op.create_unique_constraint(
        "uq_code_entities_source_qname", "code_entities", ["source_id", "qualified_name"]
    )
    op.drop_column("code_edges", "variant_key")
    op.drop_column("code_entities", "variant_key")
