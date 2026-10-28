"""Conservative specialization of declared Java receiver types."""

import re


def type_arguments(value):
    if "<" not in value or not value.endswith(">"):
        return []
    text = value[value.index("<") + 1 : -1]
    result, depth, start = [], 0, 0
    for index, char in enumerate(text):
        depth += char == "<"
        depth -= char == ">"
        if char == "," and depth == 0:
            result.append(text[start:index].strip())
            start = index + 1
    result.append(text[start:].strip())
    return result


def specialize_return(return_type, method, calls, owners):
    if method.meta.get("type_parameters"):
        return return_type, False
    parameters = {tuple(owner.meta.get("type_parameters", [])) for owner in owners}
    declarations = {call.meta.get("receiver_declared_type", "") for call in calls}
    if len(parameters) != 1 or len(declarations) != 1:
        return return_type, False
    parameters = next(iter(parameters))
    arguments = type_arguments(next(iter(declarations)))
    if (
        not parameters
        or len(parameters) != len(arguments)
        or any("?" in argument for argument in arguments)
    ):
        return return_type, False
    mapping = dict(zip(parameters, arguments))
    exact = return_type in mapping
    return re.sub(
        r"\b(?:" + "|".join(map(re.escape, parameters)) + r")\b",
        lambda match: mapping[match.group()],
        return_type,
    ), exact


def array_receiver(receiver, edge, lookup, resolve, declaration_context):
    match = re.fullmatch(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)((?:\[[^\[\]]+\])+)", receiver)
    if not match:
        return None
    declarations, _ = lookup(match.group(1))
    if len(declarations) != 1:
        return [], "array_receiver_not_uniquely_declared"
    declaration = declarations[0]
    meta = declaration.meta
    name = meta.get("parameter_type") or meta.get("variable_type") or meta.get("field_type") or ""
    for _ in range(match.group(2).count("[")):
        if not name.endswith("[]"):
            return [], "array_dimensions_not_proven"
        name = name[:-2]
    if name.endswith("[]"):
        return [], "array_element_is_still_array"
    context = declaration_context(declaration)
    candidates, reason = resolve(name, context, declaration.parent_qualified_name.split("#", 1)[0])
    if candidates:
        edge.meta["receiver_symbol_qualified_name"] = declaration.qualified_name
        edge.meta["receiver_resolution"] = "array_element_type"
        if "<" in name:
            edge.meta["receiver_declared_type"] = name
    return candidates, "array_element_type" if candidates else reason
