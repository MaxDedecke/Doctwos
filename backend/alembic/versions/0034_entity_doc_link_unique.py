"""One entity/chunk pair can have only one entity-document link (O-184)."""

from alembic import op


revision = "0034_entity_doc_link_unique"
down_revision = "0033_llm_profile_serving_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep one row per pair: a reviewed decision wins over a pending suggestion, then the newest row.
    op.execute(
        """
        DELETE FROM entity_doc_links
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY entity_id, chunk_id
                    ORDER BY (status IN ('approved', 'rejected')) DESC, id DESC
                ) AS rank
                FROM entity_doc_links
                WHERE chunk_id IS NOT NULL
            ) ranked
            WHERE rank > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_entity_doc_links_entity_chunk", "entity_doc_links", ["entity_id", "chunk_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_entity_doc_links_entity_chunk", "entity_doc_links", type_="unique")
