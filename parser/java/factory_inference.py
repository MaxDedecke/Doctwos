"""Infer a var receiver only from the resolved call at its exact initializer."""

import re

from .scope import scope_candidates


def factory_receiver(declaration, result, methods_by_qname, result_by_type, resolve_type):
    meta = declaration.meta or {}
    expression = meta.get("initializer_expression")
    if not expression:
        return [], "local_initializer_type_unknown"
    normalized = re.sub(r"\s+", "", expression)
    calls = [
        edge
        for edge in result.edges
        if edge.type == "CALLS"
        and edge.resolution == "resolved"
        and edge.src_name == declaration.parent_qualified_name
        and edge.src_start_line == meta.get("initializer_line")
        and edge.meta.get("src_start_column") == meta.get("initializer_column")
        and re.sub(
            r"\s+",
            "",
            edge.dst_name + "(" + ",".join(edge.meta.get("argument_expressions", [])) + ")",
        )
        == normalized
    ]
    targets = {edge.meta.get("target_qualified_name") for edge in calls}
    if len(targets) != 1:
        return [], "initializer_call_not_uniquely_resolved"
    methods = scope_candidates(methods_by_qname.get(next(iter(targets)), []), result)
    if len(methods) != 1 or not methods[0].meta.get("return_type"):
        return [], "initializer_return_type_unknown"
    method = methods[0]
    owner = method.parent_qualified_name
    path = calls[0].meta.get("target_file_path")
    owner_result = next(
        (r for r in result_by_type.values() if r.path == path), result_by_type.get(owner, result)
    )
    candidates, reason = resolve_type(method.meta["return_type"], owner_result, owner)
    return candidates, "factory_return_type" if candidates else reason
