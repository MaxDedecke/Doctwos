"""Local Java symbol resolution for one parsed source file.

Only declarations in the current ``ParseResult`` are considered here.  Names
that need package/import or cross-file knowledge stay unresolved for T3.3.
"""

from __future__ import annotations

import re

from core.model import Entity, ParsedEdge


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
            item for item in candidates if len(item.meta.get("parameter_types", ())) == argument_count
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

    package = next(
        (item.meta.get("package") for item in entities if item.type == "package"), None
    )
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
