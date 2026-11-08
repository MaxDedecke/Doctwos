"""Bounded linked-document records for language-model contexts."""

from xml.sax.saxutils import escape


def compact_linked_records(records, count: int, include_text: bool = False) -> list[dict]:
    if not isinstance(records, list):
        return []
    compacted = []
    for record in records[:count]:
        if not isinstance(record, dict):
            continue
        item = {
            name: record.get(name)
            for name in (
                "entity_id",
                "source_type",
                "issue_key",
                "classification",
                "classification_basis",
                "classification_keyword",
                "record_type",
                "bug_candidate",
                "url",
                "relationship_path_entity_id",
                "relationship_path_available",
            )
            if name in record
        }
        if isinstance(record.get("title"), str):
            item["title"] = f"<untrusted_source>{escape(record['title'][:120])}</untrusted_source>"
        evidence = record.get("evidence")
        if isinstance(evidence, dict):
            item["evidence"] = {
                name: evidence.get(name)
                for name in (
                    "link_id",
                    "status",
                    "link_type",
                    "direction",
                    "score",
                    "reviewed_at",
                    "chunk_id",
                    "start_line",
                    "end_line",
                )
                if name in evidence
            }
            if include_text:
                for name in ("context", "excerpt"):
                    value = evidence.get(name)
                    if isinstance(value, str) and value.strip():
                        item["evidence"][name] = (
                            f"<untrusted_source>{escape(value[:120])}</untrusted_source>"
                        )
        compacted.append(item)
    return compacted
