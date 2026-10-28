"""Dispatch from an unchanged local lambda initializer to its source body."""

from core.model import ParsedEdge


def derive_lambda_dispatch(results):
    entities = [entity for result in results for entity in result.entities]
    methods = {entity.qualified_name: entity for entity in entities if entity.type == "method"}
    interfaces = {entity.qualified_name for entity in entities if entity.type == "interface"}
    for result in results:
        local = {entity.qualified_name: entity for entity in result.entities}
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
            abstract = [
                entity
                for entity in methods.values()
                if entity.parent_qualified_name == method.parent_qualified_name
                and not set(entity.meta.get("modifiers", [])) & {"static", "default", "private"}
            ]
            # Inherited SAM contracts need their own complete interface resolution.
            inherits = any(
                edge.type == "EXTENDS" and edge.src_name == method.parent_qualified_name
                for item in results
                for edge in item.edges
            )
            parameters = [
                entity
                for entity in result.entities
                if entity.type == "parameter"
                and entity.parent_qualified_name == target.qualified_name
            ]
            if (
                inherits
                or len(abstract) != 1
                or len(parameters) != len(method.meta.get("parameter_types", []))
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
