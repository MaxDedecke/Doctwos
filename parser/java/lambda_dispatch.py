"""Dispatch from an unchanged local lambda initializer to its source body."""

from core.model import ParsedEdge
from collections import Counter, defaultdict


def derive_lambda_dispatch(results):
    entities = [entity for result in results for entity in result.entities]
    methods = {entity.qualified_name: entity for entity in entities if entity.type == "method"}
    interfaces = {entity.qualified_name for entity in entities if entity.type == "interface"}
    abstract_by_owner = defaultdict(list)
    for method in methods.values():
        if not set(method.meta.get("modifiers", [])) & {"static", "default", "private"}:
            abstract_by_owner[method.parent_qualified_name].append(method)
    inherited = {
        edge.src_name for result in results for edge in result.edges if edge.type == "EXTENDS"
    }
    for result in results:
        local = {entity.qualified_name: entity for entity in result.entities}
        parameter_counts = Counter(
            entity.parent_qualified_name for entity in result.entities if entity.type == "parameter"
        )
        existing = {
            (edge.src_name, edge.dst_name, edge.src_start_line, edge.meta.get("src_start_column"))
            for edge in result.edges
            if edge.meta.get("derivation") == "lambda_binding"
        }
        for call in list(result.edges):
            if call.type != "CALLS" or call.resolution != "resolved":
                continue
            variable = local.get(call.meta.get("receiver_symbol_qualified_name"))
            if variable is None or variable.type != "local_variable":
                continue
            target = local.get(variable.meta.get("lambda_initializer"))
            holder = local.get(variable.parent_qualified_name)
            if (
                target is None
                or target.type != "lambda"
                or holder is None
                or holder.meta.get("data_flow_truncated")
            ):
                continue
            writes = [
                row
                for row in holder.meta.get("data_flow", [])
                if row.get("target", {}).get("qualified_name") == variable.qualified_name
                and row.get("operation") != "init"
                and row.get("line", 0) <= call.src_start_line
            ]
            if writes:
                continue
            method = methods.get(call.meta.get("target_qualified_name"))
            if method is None or method.parent_qualified_name not in interfaces:
                continue
            # Inherited SAM contracts need their own complete interface resolution.
            if (
                method.parent_qualified_name in inherited
                or len(abstract_by_owner[method.parent_qualified_name]) != 1
                or parameter_counts[target.qualified_name]
                != len(method.meta.get("parameter_types", []))
            ):
                continue
            key = (
                call.src_name,
                target.qualified_name,
                call.src_start_line,
                call.meta.get("src_start_column"),
            )
            if key in existing:
                continue
            existing.add(key)
            yield (
                result,
                ParsedEdge(
                    type="DISPATCHES_TO",
                    src_name=call.src_name,
                    dst_name=target.qualified_name,
                    resolution="resolved",
                    src_start_line=call.src_start_line,
                    src_end_line=call.src_end_line,
                    meta={
                        **call.meta,
                        "derivation": "lambda_binding",
                        "target_qualified_name": target.qualified_name,
                        "target_file_path": result.path,
                        "resolution_reason": "local_lambda_initializer",
                        "dispatch_scope": "local_initializer",
                        "binding_qualified_name": variable.qualified_name,
                        "invocation_kind": "lambda",
                    },
                ),
            )
