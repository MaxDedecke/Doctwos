"""Keep equal Java qualified names from separate modules distinct."""

from alembic import op


revision = "0023_module_scoped_code_entities"
down_revision = "0022_scan_coverage_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_code_entities_source_variant_qname", "code_entities", type_="unique")
    op.create_unique_constraint(
        "uq_code_entities_source_variant_file_qname",
        "code_entities",
        ["source_id", "variant_key", "file_path", "qualified_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_code_entities_source_variant_file_qname", "code_entities", type_="unique")
    op.create_unique_constraint(
        "uq_code_entities_source_variant_qname",
        "code_entities",
        ["source_id", "variant_key", "qualified_name"],
    )
