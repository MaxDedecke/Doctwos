"""Persist project ownership for knowledge links and topics."""

from alembic import op
import sqlalchemy as sa

revision = "0037_link_manager_projects"
down_revision = "0036_scan_file_stat"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("knowledge_links", "topics"):
        op.add_column(table, sa.Column("project_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_project_id", table, "projects", ["project_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
    # Do not guess ownership from titles, URLs or stale client metadata.
    op.execute("""
        WITH origins AS (
            SELECT l.id,
                CASE WHEN l.source_a_type = 'entity' AND l.source_a_entity_id IS NOT NULL
                    THEN coalesce(ea.project_id, sea.project_id)
                    ELSE coalesce(ca.project_id, sca.project_id) END AS a,
                CASE WHEN l.source_b_type = 'entity' AND l.source_b_entity_id IS NOT NULL
                    THEN coalesce(eb.project_id, seb.project_id)
                    ELSE coalesce(cb.project_id, scb.project_id) END AS b
            FROM knowledge_links l
            LEFT JOIN code_entities ea ON ea.id = l.source_a_entity_id
            LEFT JOIN knowledge_sources sea ON sea.id = ea.source_id
            LEFT JOIN code_entities eb ON eb.id = l.source_b_entity_id
            LEFT JOIN knowledge_sources seb ON seb.id = eb.source_id
            LEFT JOIN document_chunks ca ON ca.id = l.source_a_chunk_id
            LEFT JOIN knowledge_sources sca ON sca.id = ca.source_id
            LEFT JOIN document_chunks cb ON cb.id = l.source_b_chunk_id
            LEFT JOIN knowledge_sources scb ON scb.id = cb.source_id
        )
        UPDATE knowledge_links l SET project_id = o.a
        FROM origins o WHERE l.id = o.id AND o.a = o.b
    """)
    op.execute("""
        WITH origins AS (
            SELECT n.topic_id, CASE
                WHEN n.node_type IN ('project', 'repository') THEN p.id
                WHEN n.node_type = 'entity' THEN coalesce(e.project_id, es.project_id)
                WHEN n.node_type = 'document' THEN coalesce(c.project_id, cs.project_id)
                WHEN n.node_type = 'knowledge_source' THEN s.project_id
                END AS project_id
            FROM topic_nodes n
            LEFT JOIN projects p ON p.id = n.node_id
            LEFT JOIN code_entities e ON e.id = n.node_id
            LEFT JOIN knowledge_sources es ON es.id = e.source_id
            LEFT JOIN document_chunks c ON c.id = n.node_id
            LEFT JOIN knowledge_sources cs ON cs.id = c.source_id
            LEFT JOIN knowledge_sources s ON s.id = n.node_id
        ), owners AS (
            SELECT topic_id, min(project_id) AS project_id FROM origins
            GROUP BY topic_id HAVING min(project_id) = max(project_id)
                AND count(project_id) = count(*)
        )
        UPDATE topics t SET project_id = o.project_id FROM owners o WHERE t.id = o.topic_id
    """)


def downgrade():
    for table in ("topics", "knowledge_links"):
        op.drop_index(f"ix_{table}_project_id", table)
        op.drop_constraint(f"fk_{table}_project_id", table, type_="foreignkey")
        op.drop_column(table, "project_id")
