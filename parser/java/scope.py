"""Build visibility shared by Java and framework resolution."""

from core.model import Entity, ParseResult


def scope_candidates(
    candidates: list[Entity], result: ParseResult, *, runtime=False
) -> list[Entity]:
    root_meta = next((e.meta for e in result.entities if e.meta.get("is_file_root")), {})
    module = root_meta.get("module")
    source_set = root_meta.get("source_set")
    visibility = root_meta.get("maven_visibility")
    if runtime:
        visibility = root_meta.get("maven_runtime_visibility", visibility)
    scoped = candidates
    if visibility is not None:
        scoped = [e for e in scoped if e.meta.get("module") in visibility]
        scoped = [
            e
            for e in scoped
            if e.meta.get("module") == module or e.meta.get("source_set") in {None, "main"}
        ]
    if module is not None:
        local = [e for e in scoped if e.meta.get("module") == module]
        if local:
            scoped = local
    if source_set is None:
        return scoped
    exact = [e for e in scoped if e.meta.get("source_set") == source_set]
    if exact:
        return exact
    if source_set != "main":
        main = [e for e in scoped if e.meta.get("source_set") == "main"]
        if main:
            return main
    if any(e.meta.get("source_set") is not None for e in scoped):
        return []
    return scoped


def same_declaration_scope(left: Entity, right: Entity) -> bool:
    for key in ("module", "source_set"):
        a, b = (left.meta or {}).get(key), (right.meta or {}).get(key)
        if a is not None and b is not None and a != b:
            return False
    return True
