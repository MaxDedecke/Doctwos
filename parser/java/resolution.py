"""Local and global Java symbol resolution.

The local pass resolves one ``ParseResult``. The global pass works on several
already parsed Java files and deliberately leaves external or ambiguous names
unresolved.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.model import Entity, ParseResult, ParsedEdge


_TYPE_ENTITY_TYPES = {
    "class",
    "interface",
    "enum",
    "record",
    "annotation_type",
    "local_class",
    "anonymous_class",
}
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
    if receiver == "super" or (receiver and receiver.endswith(".super")):
        meta["resolution_reason"] = "super_dispatch_requires_hierarchy"
        return []
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


def _source_method(edge: ParsedEdge) -> str | None:
    source = (edge.meta or {}).get("source_qualified_name") or edge.src_name
    return source if "#" in source else None


def _entity_type_name(entity: Entity) -> str | None:
    meta = entity.meta or {}
    return (
        meta.get("field_type")
        or meta.get("parameter_type")
        or meta.get("variable_type")
        or meta.get("component_type")
        or meta.get("inferred_type")
    )


def _fields_for_owner(
    owner: str,
    field_name: str,
    field_by_owner_and_name: dict[tuple[str, str], list[Entity]],
    *,
    hierarchy: dict[str, list[str]],
) -> list[Entity]:
    """Find the nearest declarations for a field in a type hierarchy."""
    seen: set[str] = set()
    queue = [owner]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        matches = field_by_owner_and_name.get((current, field_name), [])
        if matches:
            return matches
        queue.extend(hierarchy.get(current, ()))
    return []


def _receiver_declaration(
    receiver: str,
    edge: ParsedEdge,
    *,
    fields_by_owner_and_name: dict[tuple[str, str], list[Entity]],
    variables_by_parent_and_name: dict[tuple[str, str], list[Entity]],
    hierarchy: dict[str, list[str]],
) -> tuple[list[Entity], str | None]:
    """Return a parameter/local/field declaration for a simple receiver."""
    source_owner = _source_owner(edge)
    source_method = _source_method(edge)
    if not source_owner:
        return [], None

    field_name: str | None = None
    if receiver.startswith("this.") or receiver.startswith("super."):
        field_name = receiver.split(".", 1)[1]
    elif "." not in receiver:
        field_name = receiver

    if field_name is None or not field_name or "." in field_name:
        return [], None

    if source_method and not receiver.startswith(("this.", "super.")):
        variables = variables_by_parent_and_name.get((source_method, field_name), [])
        if variables:
            kind = variables[0].type
            return variables if len(variables) == 1 else [], (
                "receiver_parameter" if kind == "parameter" else "receiver_local_variable"
            )

    owners = [source_owner]
    if receiver.startswith("super."):
        owners = hierarchy.get(source_owner, [])
    fields: list[Entity] = []
    for owner in owners:
        fields.extend(
            _fields_for_owner(
                owner,
                field_name,
                fields_by_owner_and_name,
                hierarchy=hierarchy,
            )
        )
        if fields:
            break
    if len(fields) == 1:
        return fields, "receiver_field"
    if len(fields) > 1:
        return [], "ambiguous_receiver"
    return [], None


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
    count = (edge.meta or {}).get("argument_count")
    if count is not None:
        candidates = [item for item in candidates if len(item.meta.get("parameter_types", ())) == count]
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
    if edge.type == "CALLS":
        edge.meta["dispatch_scope"] = "static_declaration_only"


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


def _scope_candidates(candidates: list[Entity], result: ParseResult) -> list[Entity]:
    """Prefer symbols visible from the caller's Maven module/source set.

    Maven does not permit a main source set to use a test-only class.  A test
    source set may use its module's main classes, though.  We deliberately do
    not infer inter-module dependencies from a POM here: when no local module
    candidate exists, the normal import/ambiguity rules still decide whether a
    repository target is safe to use.
    """
    root_meta = next(
        (entity.meta for entity in result.entities if entity.meta.get("is_file_root")),
        {},
    )
    module = root_meta.get("module")
    source_set = root_meta.get("source_set")
    scoped = candidates
    if module is not None:
        local = [item for item in scoped if item.meta.get("module") == module]
        if local:
            scoped = local
    if source_set is None:
        return scoped

    exact = [item for item in scoped if item.meta.get("source_set") == source_set]
    if exact:
        return exact
    # Test-like source sets inherit main; main must never fall through to a
    # test-only declaration.  Untagged legacy paths remain eligible.
    if source_set != "main":
        main = [item for item in scoped if item.meta.get("source_set") == "main"]
        if main:
            return main
    if any(item.meta.get("source_set") is not None for item in scoped):
        return []
    return scoped


def _same_declaration_scope(left: Entity, right: Entity) -> bool:
    """Whether two Java declarations belong to the same build scope."""
    left_meta, right_meta = left.meta or {}, right.meta or {}
    for key in ("module", "source_set"):
        left_value, right_value = left_meta.get(key), right_meta.get(key)
        if left_value is not None and right_value is not None and left_value != right_value:
            return False
    return True


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
        exact = _scope_candidates(exact, result)
        return exact, "qualified_name" if exact else None

    package = _package_for(result)
    candidates = _candidates_at_stage((f"{package}.{name}",) if package else (), types_by_qname)
    if candidates:
        candidates = _scope_candidates(candidates, result)
        return candidates, "current_package"
    if not package:
        # Types in the unnamed package have no package-qualified lookup key.
        # Keep the same ambiguity rule as named packages instead of guessing
        # when several default-package files define the same simple name.
        candidates = types_by_name.get(name, [])
        if candidates:
            candidates = _scope_candidates(candidates, result)
            return candidates, "unnamed_package"

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
        candidates = _scope_candidates(candidates, result)
        return candidates, "explicit_import"

    candidates = _candidates_at_stage((f"java.lang.{name}",), types_by_qname)
    if candidates:
        candidates = _scope_candidates(candidates, result)
        return candidates, "java.lang"

    wildcard_packages = [
        edge.dst_name[:-2]
        for edge in imports
        if not edge.meta.get("static") and edge.meta.get("wildcard")
    ]
    candidates = _candidates_at_stage(
        (f"{wildcard_package}.{name}" for wildcard_package in wildcard_packages),
        types_by_qname,
    )
    if candidates:
        candidates = _scope_candidates(candidates, result)
        return candidates, "wildcard_import"

    if source_owner:
        candidates = _candidates_at_stage((f"{source_owner}.{name}",), types_by_qname)
        if candidates:
            candidates = _scope_candidates(candidates, result)
            return candidates, "owner_type"

    # A simple name from another package is not a valid match without an
    # import. Keep external and missing dependencies unresolved as well.
    return [], None


def _build_hierarchy(
    results: list[ParseResult],
    *,
    types_by_qname: dict[str, list[Entity]],
    types_by_name: dict[str, list[Entity]],
) -> dict[str, list[str]]:
    hierarchy: dict[str, list[str]] = {}
    for result in results:
        for edge in result.edges:
            if edge.type not in {"EXTENDS", "IMPLEMENTS"}:
                continue
            owner = _source_owner(edge)
            target = (edge.meta or {}).get("target_qualified_name")
            if not owner:
                continue
            if not target:
                candidates, _ = _global_type_candidates(
                    edge.dst_name,
                    result=result,
                    source_owner=owner,
                    types_by_qname=types_by_qname,
                    types_by_name=types_by_name,
                )
                if len(candidates) == 1:
                    target = candidates[0].qualified_name
            if target and target in types_by_qname:
                hierarchy.setdefault(owner, [])
                if target not in hierarchy[owner]:
                    hierarchy[owner].append(target)
    return hierarchy


def _receiver_type_candidates(
    edge: ParsedEdge,
    *,
    result: ParseResult,
    types_by_qname: dict[str, list[Entity]],
    types_by_name: dict[str, list[Entity]],
    fields_by_owner_and_name: dict[tuple[str, str], list[Entity]],
    variables_by_parent_and_name: dict[tuple[str, str], list[Entity]],
    hierarchy: dict[str, list[str]],
    result_by_type: dict[str, ParseResult],
) -> tuple[list[Entity], str | None]:
    """Infer a method receiver's declared type from source-backed symbols."""
    receiver = (edge.meta or {}).get("receiver")
    source_owner = _source_owner(edge)
    if receiver in {None, "this"}:
        return (
            _scope_candidates(_candidates_at_stage((source_owner,), types_by_qname), result)
            if source_owner
            else [],
            "owner_type",
        )
    if receiver == "super":
        parents = hierarchy.get(source_owner or "", [])
        return _candidates_at_stage(parents, types_by_qname), "superclass"

    receiver_name = receiver
    new_match = re.fullmatch(r"new([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\(.*\)", receiver_name)
    if new_match:
        return _global_type_candidates(
            new_match.group(1),
            result=result,
            source_owner=source_owner,
            types_by_qname=types_by_qname,
            types_by_name=types_by_name,
        )

    # ``this.field`` and a one-level ``variable.field`` are the only dotted
    # receivers inferred here.  Chained expressions need data-flow/type
    # information that the parser does not have and remain unresolved.
    declaration_receiver = receiver_name
    if "." in receiver_name and not receiver_name.startswith(("this.", "super.")):
        first, remainder = receiver_name.split(".", 1)
        if "." in remainder:
            return [], None
        base_candidates, base_reason = (
            _receiver_type_candidates(
                edge,
                result=result,
                types_by_qname=types_by_qname,
                types_by_name=types_by_name,
                fields_by_owner_and_name=fields_by_owner_and_name,
                variables_by_parent_and_name=variables_by_parent_and_name,
                hierarchy=hierarchy,
                result_by_type=result_by_type,
            )
            if first in {"this", "super"}
            else ([], None)
        )
        if first not in {"this", "super"}:
            synthetic = ParsedEdge(
                type=edge.type,
                src_name=edge.src_name,
                dst_name=first,
                resolution="unresolved",
                src_start_line=edge.src_start_line,
                src_end_line=edge.src_end_line,
                meta={**(edge.meta or {}), "receiver": first},
            )
            base_candidates, base_reason = _receiver_type_candidates(
                synthetic,
                result=result,
                types_by_qname=types_by_qname,
                types_by_name=types_by_name,
                fields_by_owner_and_name=fields_by_owner_and_name,
                variables_by_parent_and_name=variables_by_parent_and_name,
                hierarchy=hierarchy,
                result_by_type=result_by_type,
            )
        if len(base_candidates) != 1:
            return [], base_reason
        base_owner = base_candidates[0].qualified_name
        field_candidates = _fields_for_owner(
            base_owner,
            remainder,
            fields_by_owner_and_name,
            hierarchy=hierarchy,
        )
        if len(field_candidates) != 1:
            return [], "ambiguous_receiver" if field_candidates else None
        edge.meta["receiver_symbol_qualified_name"] = field_candidates[0].qualified_name
        edge.meta["receiver_resolution"] = "receiver_field"
        field_type = _entity_type_name(field_candidates[0])
        if not field_type:
            return [], None
        field_result = result_by_type.get(field_candidates[0].parent_qualified_name or "", result)
        types, type_reason = _global_type_candidates(
            field_type,
            result=field_result,
            source_owner=base_owner,
            types_by_qname=types_by_qname,
            types_by_name=types_by_name,
        )
        return types, "receiver_field" if types else type_reason

    declarations, declaration_reason = _receiver_declaration(
        declaration_receiver,
        edge,
        fields_by_owner_and_name=fields_by_owner_and_name,
        variables_by_parent_and_name=variables_by_parent_and_name,
        hierarchy=hierarchy,
    )
    if declarations:
        declaration = declarations[0]
        edge.meta["receiver_symbol_qualified_name"] = declaration.qualified_name
        edge.meta["receiver_resolution"] = declaration_reason
        declared_type = _entity_type_name(declaration)
        if not declared_type or declared_type == "var":
            declared_type = (declaration.meta or {}).get("inferred_type")
        if not declared_type:
            return [], declaration_reason
        declaration_result = result_by_type.get(declaration.parent_qualified_name or "", result)
        types, type_reason = _global_type_candidates(
            declared_type,
            result=declaration_result,
            source_owner=source_owner,
            types_by_qname=types_by_qname,
            types_by_name=types_by_name,
        )
        return types, declaration_reason if types else type_reason

    # A receiver that is a type name (for example ``Util.check()``) is
    # resolved only through Java's import/package rules.
    return _global_type_candidates(
        receiver_name,
        result=result,
        source_owner=source_owner,
        types_by_qname=types_by_qname,
        types_by_name=types_by_name,
    )


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
            owner = imported if edge.meta.get("wildcard") else (
                imported.rsplit(".", 1)[0] if "." in imported else None
            )
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
    result_by_type: dict[str, ParseResult],
    fields_by_owner_and_name: dict[tuple[str, str], list[Entity]],
    variables_by_parent_and_name: dict[tuple[str, str], list[Entity]],
    hierarchy: dict[str, list[str]],
) -> tuple[list[Entity], str | None]:
    meta = edge.meta or {}
    method_name = meta.get("method_name", edge.dst_name.rsplit(".", 1)[-1])
    receiver = meta.get("receiver")
    source_owner = _source_owner(edge)
    if receiver == "super":
        # ``super.method()`` is different from a virtual call on an inferred
        # receiver: Java fixes it to the nearest superclass declaration.  Walk
        # only explicit EXTENDS edges and keep every missing or ambiguous step
        # unresolved rather than guessing a method by name.
        owner = source_owner
        seen: set[str] = set()
        while owner and owner not in seen:
            seen.add(owner)
            owner_result = result_by_type.get(owner)
            if owner_result is None:
                break
            extends = [
                item
                for item in owner_result.edges
                if item.type == "EXTENDS" and _source_owner(item) == owner
            ]
            if len(extends) != 1:
                break
            parents, parent_reason = _global_type_candidates(
                extends[0].dst_name,
                result=owner_result,
                source_owner=owner,
                types_by_qname=types_by_qname,
                types_by_name=types_by_name,
            )
            if len(parents) != 1 or not parents[0].qualified_name:
                if len(parents) > 1:
                    meta["resolution_reason"] = "ambiguous_superclass"
                break
            parent = parents[0]
            parent_result = result_by_type.get(parent.qualified_name)
            candidates = [
                item
                for item in methods_by_owner_and_name.get(
                    (parent.qualified_name, method_name), []
                )
                if item.meta.get("visibility") in {"public", "protected"}
                or (
                    item.meta.get("visibility", "package") == "package"
                    and parent_result is not None
                    and _package_for(owner_result) == _package_for(parent_result)
                )
            ]
            if candidates:
                return candidates, parent_reason or "superclass_declaration"
            owner = parent.qualified_name
        meta.setdefault("resolution_reason", "super_dispatch_requires_hierarchy")
        return [], None
    if receiver and receiver.endswith(".super"):
        # Default-interface dispatch needs the selected interface and its
        # inheritance graph; neither can be inferred safely from syntax alone.
        meta["resolution_reason"] = "interface_super_dispatch_requires_hierarchy"
        return [], None
    owner_candidates: list[Entity] = []
    owner_reason: str | None = None

    if receiver in {None, "this", "super"}:
        static_owners = _static_import_owners(result, method_name)
        if static_owners:
            owner_candidates = _scope_candidates(
                _candidates_at_stage(static_owners, types_by_qname), result
            )
            owner_reason = "static_import"
        if not owner_candidates and source_owner:
            owner_candidates = _scope_candidates(
                _candidates_at_stage((source_owner,), types_by_qname), result
            )
            owner_reason = "owner_type"
    else:
        owner_candidates, owner_reason = _receiver_type_candidates(
            edge,
            result=result,
            types_by_qname=types_by_qname,
            types_by_name=types_by_name,
            fields_by_owner_and_name=fields_by_owner_and_name,
            variables_by_parent_and_name=variables_by_parent_and_name,
            hierarchy=hierarchy,
            result_by_type=result_by_type,
        )

    if receiver not in {None, "this", "super"} and len(owner_candidates) == 1:
        meta["receiver_type_qualified_name"] = owner_candidates[0].qualified_name

    candidates: list[Entity] = []
    for owner in owner_candidates:
        if owner.qualified_name:
            # Look up declared methods first, then inherited/interface methods.
            # A nearer declaration with the same signature shadows an ancestor;
            # different signatures remain available for overload resolution.
            seen_owners: set[str] = set()
            seen_signatures: set[tuple[str, ...]] = set()
            queue = [owner.qualified_name]
            while queue:
                current = queue.pop(0)
                if current in seen_owners:
                    continue
                seen_owners.add(current)
                for method in methods_by_owner_and_name.get((current, method_name), []):
                    if not _same_declaration_scope(method, owner):
                        continue
                    signature = tuple(method.meta.get("parameter_types", ()))
                    if signature not in seen_signatures:
                        candidates.append(method)
                        seen_signatures.add(signature)
                queue.extend(hierarchy.get(current, ()))
    # Duplicate qualified names can occur in separate build modules.  Do not
    # turn that into a false unique call target.
    unique: dict[str, Entity] = {}
    for candidate in candidates:
        if candidate.qualified_name:
            unique.setdefault(candidate.qualified_name, candidate)
    candidates = list(unique.values()) if len(unique) == len(candidates) else candidates
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
    entity_paths = {
        id(entity): result.path for result in java_results for entity in result.entities
    }

    def mark_global(edge: ParsedEdge, target: Entity, *, reason: str) -> None:
        _mark_resolved(edge, target, reason=reason)
        # A qualified name is deliberately not globally unique in a Maven
        # reactor.  Persist the selected compilation unit so the DB adapter
        # can bind the edge to the same module-local declaration.
        target_path = entity_paths.get(id(target))
        if target_path:
            edge.meta["target_file_path"] = target_path
        edge.meta["resolution_scope"] = "global"
    types = [entity for entity in entities if entity.type in _TYPE_ENTITY_TYPES]
    types_by_qname: dict[str, list[Entity]] = {}
    types_by_name: dict[str, list[Entity]] = {}
    for entity in types:
        if entity.qualified_name:
            types_by_qname.setdefault(entity.qualified_name, []).append(entity)
        types_by_name.setdefault(entity.name, []).append(entity)

    methods_by_owner_and_name: dict[tuple[str, str], list[Entity]] = {}
    fields_by_owner_and_name: dict[tuple[str, str], list[Entity]] = {}
    variables_by_parent_and_name: dict[tuple[str, str], list[Entity]] = {}
    for entity in entities:
        if entity.type == "method" and entity.parent_qualified_name:
            methods_by_owner_and_name.setdefault(
                (entity.parent_qualified_name, entity.name), []
            ).append(entity)
        if entity.type == "field" and entity.parent_qualified_name:
            fields_by_owner_and_name.setdefault(
                (entity.parent_qualified_name, entity.name), []
            ).append(entity)
        if entity.type in {"parameter", "local_variable"} and entity.parent_qualified_name:
            variables_by_parent_and_name.setdefault(
                (entity.parent_qualified_name, entity.name), []
            ).append(entity)
    result_by_type = {
        entity.qualified_name: result
        for result in java_results
        for entity in result.entities
        if entity.type in _TYPE_ENTITY_TYPES and entity.qualified_name
    }
    hierarchy = _build_hierarchy(
        java_results,
        types_by_qname=types_by_qname,
        types_by_name=types_by_name,
    )

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
                        and _same_declaration_scope(entity, target_type)
                        and len(entity.meta.get("parameter_types", ()))
                        == meta.get("argument_count")
                    ]
                    target = _resolve_overload(edge, constructors) if constructors else target_type
                    if target is not None:
                        mark_global(edge, target, reason=reason or "type_in_repository")
                        resolved += 1
                elif len(candidates) == 1:
                    mark_global(edge, candidates[0], reason=reason or "type_in_repository")
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
                    result_by_type=result_by_type,
                    fields_by_owner_and_name=fields_by_owner_and_name,
                    variables_by_parent_and_name=variables_by_parent_and_name,
                    hierarchy=hierarchy,
                )
                target = _resolve_overload(edge, candidates)
                if target is not None:
                    mark_global(edge, target, reason=reason or "method_in_repository")
                    resolved += 1
                elif len(candidates) > 1:
                    meta["resolution_reason"] = "ambiguous_overload"
                else:
                    meta.setdefault("resolution_reason", "receiver_or_classpath_not_resolved")
                meta["dispatch_scope"] = "static_declaration_only"
    return resolved
