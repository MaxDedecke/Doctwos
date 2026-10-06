"""Auflösung der Dokumentations-Kanten (AsciiDoc): `DOCUMENTS` und `INCLUDES`.

Ein Abschnitt nennt im Inline-Code einen Typ, einen voll qualifizierten Namen, einen Property-Schlüssel
oder einen Dateipfad; die Kante wird nur verdrahtet, wenn das Ziel im Projekt EINDEUTIG ist. Mehrdeutige
Namen (z. B. mehrere Klassen `Realm` in verschiedenen Modulen) bleiben unaufgelöst und tragen die Zahl der
Kandidaten in `meta.ambiguous_candidates` — es wird nicht geraten.
"""
from __future__ import annotations

from collections import defaultdict

DOC_EDGE_TYPES = frozenset({"DOCUMENTS", "INCLUDES"})
# Dokumentations-Objekte sind Quelle für Verknüpfungen, selbst aber keine Code-Objekte: Sie werden
# weder im Link-Builder noch im Code-Picker des Link Managers als Code geführt.
DOC_ENTITY_TYPES = frozenset({"asciidoc_document", "doc_section"})
TYPE_ENTITY_TYPES = frozenset({"class", "interface", "enum", "record", "annotation_type"})
# Typen, die der Auflöser als Ziele braucht; der Aufrufer lädt nur diese aus der Datenbank.
RESOLUTION_TARGET_TYPES = TYPE_ENTITY_TYPES | {"property", "asciidoc_document"}
FILE_ROOT_TYPES = frozenset({
    "compilation_unit", "properties_file", "html_document", "xml_document", "groovy_file", "javascript_file",
    "shell_script", "sql_script", "maven_project", "xslt_stylesheet", "jsp_page", "asciidoc_document",
})


def _meta(edge) -> dict:
    return dict(edge.meta_json or {})


def resolve_documentation_edges(entities, edges) -> int:
    """Setzt `dst_entity_id`/`resolution` der Dokumentations-Kanten neu; Rückgabe: neu aufgelöste Kanten."""
    by_simple: dict[tuple, list] = defaultdict(list)
    by_qname: dict[tuple, list] = defaultdict(list)
    by_property: dict[tuple, list] = defaultdict(list)
    docs_by_path: dict[tuple, list] = defaultdict(list)
    roots: list = []
    for entity in entities:
        variant = entity.variant_key
        if entity.type in TYPE_ENTITY_TYPES:
            by_simple[(variant, entity.name)].append(entity)
            if entity.qualified_name:
                by_qname[(variant, entity.qualified_name)].append(entity)
        elif entity.type == "property":
            key = (entity.meta_json or {}).get("property_key")
            if key:
                by_property[(variant, key)].append(entity)
        if entity.type in FILE_ROOT_TYPES:
            roots.append(entity)
        if entity.type == "asciidoc_document":
            docs_by_path[(variant, entity.file_path)].append(entity)

    def candidates_for(edge, meta) -> list:
        variant = edge.variant_key
        if edge.type == "INCLUDES":
            return docs_by_path.get((variant, meta.get("target_file_path") or ""), [])
        kind = meta.get("mention_kind")
        name = edge.dst_name
        if kind == "type_name":
            return by_simple.get((variant, name), [])
        if kind == "qualified_name":
            return by_qname.get((variant, name), [])
        if kind == "property_key":
            return by_property.get((variant, name), [])
        if kind == "file_path":
            return [item for item in roots
                    if item.variant_key == variant and (item.file_path == name or item.file_path.endswith("/" + name))]
        return []

    resolved = 0
    for edge in edges:
        meta = _meta(edge)
        if edge.type not in DOC_EDGE_TYPES or meta.get("language") != "asciidoc":
            continue
        found = candidates_for(edge, meta)
        updated = dict(meta)
        updated.pop("ambiguous_candidates", None)
        if len(found) == 1:
            if edge.resolution != "resolved" or edge.dst_entity_id != found[0].id:
                resolved += 1
            edge.dst_entity_id = found[0].id
            edge.resolution = "resolved"
            updated["resolution_scope"] = "documentation"
        else:
            if edge.resolution != "dynamic":
                edge.resolution = "unresolved"
            edge.dst_entity_id = None
            updated.pop("resolution_scope", None)
            if len(found) > 1:
                updated["ambiguous_candidates"] = len(found)
        if updated != meta:
            edge.meta_json = updated or None
    return resolved
