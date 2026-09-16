"""Local and global Java symbol resolution.

The local pass resolves one ``ParseResult``. The global pass works on several
already parsed Java files and deliberately leaves external or ambiguous names
unresolved.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.model import Entity, ParseResult, ParsedEdge


_TYPE_ENTITY_TYPES = {"class", "interface", "enum", "record", "annotation_type"}
_LOCAL_EDGE_TYPES = {
    "EXTENDS",
    "IMPLEMENTS",
    "USES_TYPE",
    "CALLS",
    "INSTANTIATES",
    "READS",
    "WRITES",
}


def _base_type(value: str) -> str:
    """Remove annotations, generic arguments and array/vararg suffixes."""
    value = re.sub(r"@[A-Za-z_$][\w$]*(?:\([^)]*\))?", "", value)
    value = value.replace("...", "[]").replace(" ", "")
    value = value.split("<", 1)[0]
    return value.rstrip("[]")


def _simple_type(value: str) -> str:
    return _base_type(value).rsplit(".", 1)[-1]


def _type_candidates(
    destination: str,
    *,
    owner_type: str | None,
    package_name: str | None,
    types_by_qname: dict[str, Entity],
    types_by_name: dict[str, list[Entity]],
) -> list[Entity]:
    name = _base_type(destination)
    if not name:
        return []
    exact_names = [name]
    if owner_type and "." not in name:
        exact_names.append(f"{owner_type}.{name}")
    if package_name and "." not in name:
        exact_names.append(f"{package_name}.{name}")
    exact = [types_by_qname[item] for item in dict.fromkeys(exact_names) if item in types_by_qname]
    if exact:
        return exact
    if "." in name:
        return []
    return types_by_name.get(name, [])


def _method_candidates(
    edge: ParsedEdge,
    *,
    methods_by_owner_and_name: dict[tuple[str, str], list[Entity]],
    types_by_name: dict[str, list[Entity]],
) -> list[Entity]:
    meta = edge.meta or {}
    receiver = meta.get("receiver")
    owner_type = meta.get("owner_type")
    if receiver and receiver not in {"this", "super"}:
        owner_simple = owner_type.rsplit(".", 1)[-1] if owner_type else None
        if receiver != owner_simple:
            receiver_types = types_by_name.get(receiver, [])
            owner_type = receiver_types[0].qualified_name if len(receiver_types) == 1 else None
    if not owner_type:
        return []
    candidates = list(
        methods_by_owner_and_name.get((owner_type, meta.get("method_name", edge.dst_name)), [])
    )
    argument_count = meta.get("argument_count")
    if argument_count is not None:
        candidates = [
            item
            for item in candidates
            if len(item.meta.get("parameter_types", ())) == argument_count
        ]
    return candidates


def _argument_matches(parameter: str, argument: str) -> bool:
    parameter_base = _simple_type(parameter)
    argument_base = _simple_type(argument)
    if parameter_base == argument_base:
        return True
    primitive_wrappers = {
        "byte": "Byte",
        "short": "Short",
        "int": "Integer",
        "long": "Long",
        "float": "Float",
        "double": "Double",
        "boolean": "Boolean",
        "char": "Character",
    }
    return primitive_wrappers.get(parameter_base) == argument_base


def _resolve_overload(edge: ParsedEdge, candidates: list[Entity]) -> Entity | None:
    if len(candidates) == 1:
        return candidates[0]
    argument_types = (edge.meta or {}).get("argument_types")
    if not argument_types or any(item is None for item in argument_types):
        return None
    exact = [
        candidate
        for candidate in candidates
        if len(candidate.meta.get("parameter_types", ())) == len(argument_types)
        and all(
            _simple_type(parameter) == _simple_type(argument)
            for parameter, argument in zip(candidate.meta["parameter_types"], argument_types)
        )
    ]
    if len(exact) == 1:
        return exact[0]
    matching = [
        candidate
        for candidate in candidates
        if len(candidate.meta.get("parameter_types", ())) == len(argument_types)
        and all(
            _argument_matches(parameter, argument)
            for parameter, argument in zip(candidate.meta["parameter_types"], argument_types)
        )
    ]
    return matching[0] if len(matching) == 1 else None


def _mark_resolved(edge: ParsedEdge, target: Entity, *, reason: str) -> None:
    edge.resolution = "resolved"
    edge.meta["target_qualified_name"] = target.qualified_name
    edge.meta["resolution_scope"] = "local"
    edge.meta["resolution_reason"] = reason


def resolve_local_edges(edges: list[ParsedEdge], entities: list[Entity]) -> None:
    """Resolve unambiguous targets contained in the current Java file."""
    types = [item for item in entities if item.type in _TYPE_ENTITY_TYPES]
    types_by_qname = {item.qualified_name: item for item in types if item.qualified_name}
    types_by_name: dict[str, list[Entity]] = {}
    for item in types:
        types_by_name.setdefault(item.name, []).append(item)

    package = next((item.meta.get("package") for item in entities if item.type == "package"), None)
    fields_by_qname = {
        item.qualified_name: item
        for item in entities
        if item.type == "field" and item.qualified_name
    }
    methods_by_owner_and_name: dict[tuple[str, str], list[Entity]] = {}
    for item in entities:
        if item.type == "method" and item.parent_qualified_name:
            methods_by_owner_and_name.setdefault(
                (item.parent_qualified_name, item.name), []
            ).append(item)

    for edge in edges:
        if edge.resolution != "unresolved" or edge.type not in _LOCAL_EDGE_TYPES:
            continue

        meta = edge.meta or {}
        if edge.type in {"READS", "WRITES"}:
            target_qname = meta.get("target_qualified_name")
            target = fields_by_qname.get(target_qname)
            if target is not None:
                _mark_resolved(edge, target, reason="field_in_current_file")
            continue

        if edge.type in {"EXTENDS", "IMPLEMENTS", "USES_TYPE"}:
            owner_type = meta.get("owner_type") or meta.get("source_qualified_name")
            candidates = _type_candidates(
                edge.dst_name,
                owner_type=owner_type,
                package_name=package,
                types_by_qname=types_by_qname,
                types_by_name=types_by_name,
            )
            if len(candidates) == 1:
                _mark_resolved(edge, candidates[0], reason="type_in_current_file")
            elif len(candidates) > 1:
                meta["resolution_reason"] = "ambiguous_type"
            continue

        if edge.type == "CALLS":
            candidates = _method_candidates(
                edge,
                methods_by_owner_and_name=methods_by_owner_and_name,
                types_by_name=types_by_name,
            )
            target = _resolve_overload(edge, candidates)
            if target is not None:
                _mark_resolved(edge, target, reason="method_in_current_type")
            elif len(candidates) > 1:
                meta["resolution_reason"] = "ambiguous_overload"
            continue

        if edge.type == "INSTANTIATES":
            owner_type = meta.get("owner_type")
            candidates = _type_candidates(
                edge.dst_name,
                owner_type=owner_type,
                package_name=package,
                types_by_qname=types_by_qname,
                types_by_name=types_by_name,
            )
            if len(candidates) != 1:
                if len(candidates) > 1:
                    meta["resolution_reason"] = "ambiguous_type"
                continue
            target_type = candidates[0]
            constructors = [
                item
                for item in entities
                if item.type == "constructor"
                and item.parent_qualified_name == target_type.qualified_name
                and len(item.meta.get("parameter_types", ())) == meta.get("argument_count")
            ]
            target = _resolve_overload(edge, constructors) if constructors else target_type
            if target is not None:
                _mark_resolved(edge, target, reason="constructor_in_current_file")


def _package_for(result: ParseResult) -> str | None:
    return next(
        (item.meta.get("package") for item in result.entities if item.type == "package"),
        None,
    )


def _imports_for(result: ParseResult) -> list[ParsedEdge]:
    return [edge for edge in result.edges if edge.type == "IMPORTS"]


def _candidates_at_stage(
    qnames: Iterable[str], entities_by_qname: dict[str, list[Entity]]
) -> list[Entity]:
    candidates: list[Entity] = []
    for qname in dict.fromkeys(qnames):
        candidates.extend(entities_by_qname.get(qname, []))
    return candidates


def _global_type_candidates(
    destination: str,
    *,
    result: ParseResult,
    source_owner: str | None,
    types_by_qname: dict[str, list[Entity]],
    types_by_name: dict[str, list[Entity]],
) -> tuple[list[Entity], str | None]:
    name = _base_type(destination)
    if not name:
        return [], None
    if "." in name:
        exact = _candidates_at_stage((name,), types_by_qname)
        return exact, "qualified_name" if exact else None

    package = _package_for(result)
    candidates = _candidates_at_stage((f"{package}.{name}",) if package else (), types_by_qname)
    if candidates:
        return candidates, "current_package"

    imports = _imports_for(result)
    explicit = [
        edge.dst_name
        for edge in imports
        if not edge.meta.get("static")
        and not edge.meta.get("wildcard")
        and edge.dst_name.rsplit(".", 1)[-1] == name
    ]
    candidates = _candidates_at_stage(explicit, types_by_qname)
    if candidates:
        return candidates, "explicit_import"

    candidates = _candidates_at_stage((f"java.lang.{name}",), types_by_qname)
    if candidates:
        return candidates, "java.lang"

    wildcard_packages = [
        edge.dst_name[:-2]
        for edge in imports
        if not edge.meta.get("static") and edge.meta.get("wildcard")
    ]
    candidates = _candidates_at_stage(
        (f"{package_name}.{name}" for package_name in wildcard_packages),
        types_by_qname,
    )
    if candidates:
        return candidates, "wildcard_import"

    if source_owner:
        candidates = _candidates_at_stage((f"{source_owner}.{name}",), types_by_qname)
        if candidates:
            return candidates, "owner_type"

    # A simple name from another package is not a valid match without an
    # import. Keep external and missing dependencies unresolved as well.
    return [], None


def _source_owner(edge: ParsedEdge) -> str | None:
    owner = (edge.meta or {}).get("owner_type")
    if owner:
        return owner
    source = (edge.meta or {}).get("source_qualified_name")
    return source.split("#", 1)[0] if source and "#" in source else source


def _static_import_owners(result: ParseResult, method_name: str) -> list[str]:
    owners: list[str] = []
    for edge in _imports_for(result):
        if not edge.meta.get("static"):
            continue
        imported = edge.dst_name[:-2] if edge.meta.get("wildcard") else edge.dst_name
        if edge.meta.get("wildcard") or imported.rsplit(".", 1)[-1] == method_name:
            owner = imported.rsplit(".", 1)[0] if "." in imported else None
            if owner:
                owners.append(owner)
    return owners


def _global_method_candidates(
    edge: ParsedEdge,
    *,
    result: ParseResult,
    types_by_qname: dict[str, list[Entity]],
    types_by_name: dict[str, list[Entity]],
    methods_by_owner_and_name: dict[tuple[str, str], list[Entity]],
) -> tuple[list[Entity], str | None]:
    meta = edge.meta or {}
    method_name = meta.get("method_name", edge.dst_name.rsplit(".", 1)[-1])
    receiver = meta.get("receiver")
    source_owner = _source_owner(edge)
    owner_candidates: list[Entity] = []
    owner_reason: str | None = None

    if receiver in {None, "this", "super"}:
        static_owners = _static_import_owners(result, method_name)
        if static_owners:
            owner_candidates = _candidates_at_stage(static_owners, types_by_qname)
            owner_reason = "static_import"
        if not owner_candidates and source_owner:
            owner_candidates = _candidates_at_stage((source_owner,), types_by_qname)
            owner_reason = "owner_type"
    else:
        receiver_name = receiver
        new_match = re.fullmatch(
            r"new([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\(.*\)", receiver_name
        )
        if new_match:
            receiver_name = new_match.group(1)
        owner_candidates, owner_reason = _global_type_candidates(
            receiver_name,
            result=result,
            source_owner=source_owner,
            types_by_qname=types_by_qname,
            types_by_name=types_by_name,
        )

    candidates: list[Entity] = []
    for owner in owner_candidates:
        if owner.qualified_name:
            candidates.extend(
                methods_by_owner_and_name.get((owner.qualified_name, method_name), [])
            )
    return candidates, owner_reason


def resolve_global_edges(results: Iterable[ParseResult]) -> int:
    """Resolve Java edges across a collection of parsed Java files.

    Resolution is performed per import/name-priority stage. A stage with more
    than one candidate is ambiguous and is never narrowed by a later stage.
    The function mutates the supplied ``ParsedEdge`` objects and returns the
    number of newly resolved edges.
    """
    java_results = list(results)
    entities = [entity for result in java_results for entity in result.entities]
    types = [entity for entity in entities if entity.type in _TYPE_ENTITY_TYPES]
    types_by_qname: dict[str, list[Entity]] = {}
    types_by_name: dict[str, list[Entity]] = {}
    for entity in types:
        if entity.qualified_name:
            types_by_qname.setdefault(entity.qualified_name, []).append(entity)
        types_by_name.setdefault(entity.name, []).append(entity)

    methods_by_owner_and_name: dict[tuple[str, str], list[Entity]] = {}
    for entity in entities:
        if entity.type == "method" and entity.parent_qualified_name:
            methods_by_owner_and_name.setdefault(
                (entity.parent_qualified_name, entity.name), []
            ).append(entity)

    resolved = 0
    for result in java_results:
        for edge in result.edges:
            if edge.resolution != "unresolved" or edge.type not in _LOCAL_EDGE_TYPES:
                continue
            meta = edge.meta or {}
            if edge.type in {"READS", "WRITES"}:
                # Cross-file field access needs receiver type information that
                # the syntax-only MVP does not claim to infer.
                continue
            if edge.type in {"EXTENDS", "IMPLEMENTS", "USES_TYPE", "INSTANTIATES"}:
                candidates, reason = _global_type_candidates(
                    edge.dst_name,
                    result=result,
                    source_owner=_source_owner(edge),
                    types_by_qname=types_by_qname,
                    types_by_name=types_by_name,
                )
                if edge.type == "INSTANTIATES" and len(candidates) == 1:
                    target_type = candidates[0]
                    constructors = [
                        entity
                        for entity in entities
                        if entity.type == "constructor"
                        and entity.parent_qualified_name == target_type.qualified_name
                        and len(entity.meta.get("parameter_types", ()))
                        == meta.get("argument_count")
                    ]
                    target = _resolve_overload(edge, constructors) if constructors else target_type
                    if target is not None:
                        _mark_resolved(edge, target, reason=reason or "type_in_repository")
                        edge.meta["resolution_scope"] = "global"
                        resolved += 1
                elif len(candidates) == 1:
                    _mark_resolved(edge, candidates[0], reason=reason or "type_in_repository")
                    edge.meta["resolution_scope"] = "global"
                    resolved += 1
                elif len(candidates) > 1:
                    meta["resolution_reason"] = "ambiguous_type"
                continue
            if edge.type == "CALLS":
                candidates, reason = _global_method_candidates(
                    edge,
                    result=result,
                    types_by_qname=types_by_qname,
                    types_by_name=types_by_name,
                    methods_by_owner_and_name=methods_by_owner_and_name,
                )
                target = _resolve_overload(edge, candidates)
                if target is not None:
                    _mark_resolved(edge, target, reason=reason or "method_in_repository")
                    edge.meta["resolution_scope"] = "global"
                    resolved += 1
                elif len(candidates) > 1:
                    meta["resolution_reason"] = "ambiguous_overload"
    return resolved
