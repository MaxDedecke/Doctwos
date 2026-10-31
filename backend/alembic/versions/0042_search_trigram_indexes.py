"""Trigram indexes for the global search, which otherwise scans every row on each request.

Measured on Apache Camel (2.5M entities, 800k chunks): 410 MB in total, about one minute to build,
inserting entities costs 43 µs more per row (under 0.2 % of a full import).
"""

from alembic import op

revision = "0042_search_trigram_indexes"
down_revision = "0041_code_entities_project_index"
branch_labels = None
depends_on = None

# Same expressions and the same type list as services/search.py, or the planner ignores the index.
_TAIL = "regexp_replace({column}, '^.*/', '')"
_ROOT_ENTITY_TYPES = (
    "'program','copybook','compilation_unit','jcl_file','jcl_job','xml_document','xslt_stylesheet',"
    "'html_document','jsp_page','shell_script','properties_file','groovy_file','javascript_file',"
    "'sql_script','maven_project','asciidoc_document'"
)
_INDEXES = {
    "ix_code_entities_name_trgm": "code_entities USING gin (name gin_trgm_ops)",
    "ix_code_entities_qualified_tail_trgm": (
        f"code_entities USING gin (({_TAIL.format(column='qualified_name')}) gin_trgm_ops)"
    ),
    "ix_code_entities_root_file_tail_trgm": (
        f"code_entities USING gin (({_TAIL.format(column='file_path')}) gin_trgm_ops) "
        f"WHERE type IN ({_ROOT_ENTITY_TYPES})"
    ),
    "ix_document_chunks_title_trgm": (
        "document_chunks USING gin ((CAST(metadata_json ->> 'title' AS VARCHAR)) gin_trgm_ops)"
    ),
    "ix_document_chunks_file_tail_trgm": (
        f"document_chunks USING gin (({_TAIL.format(column='file_path')}) gin_trgm_ops)"
    ),
}


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("SET LOCAL maintenance_work_mem = '256MB'")
    for name, definition in _INDEXES.items():
        op.execute(f"CREATE INDEX {name} ON {definition}")


def downgrade():
    for name in _INDEXES:
        op.execute(f"DROP INDEX {name}")
