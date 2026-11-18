"""Flow-scoped pattern declarations; unknown boolean flows never widen visibility."""

from ._antlr.JavaParser import JavaParser


def span(node):
    return {
        "start_line": node.start.line,
        "start_column": node.start.column,
        "end_line": node.stop.line,
        "end_column": node.stop.column + len(node.stop.text),
    }


def _exits(node):
    if node is None:
        return False
    if isinstance(node, JavaParser.StatementContext):
        if node.start.text in {"return", "throw"}:
            return True
        if node.start.text == "if":
            branches = node.statement()
            return len(branches) == 2 and all(_exits(branch) for branch in branches)
        return _exits(node.block())
    if isinstance(node, JavaParser.BlockContext):
        statements = node.blockStatement()
        return bool(statements) and _exits(statements[-1])
    if isinstance(node, JavaParser.BlockStatementContext):
        return _exits(node.statement())
    return False


def _after_if(node):
    parent = node.parentCtx
    if not isinstance(parent, JavaParser.BlockStatementContext):
        return None
    block = parent.parentCtx
    if not isinstance(block, JavaParser.BlockContext):
        return None
    return {
        "start_line": node.stop.line,
        "start_column": node.stop.column + len(node.stop.text),
        "end_line": block.stop.line,
        "end_column": block.stop.column,
    }


def visibility_ranges(pattern):
    ranges = []
    child, current = pattern, pattern.parentCtx
    matches_when = True
    while current is not None:
        if isinstance(current, JavaParser.SwitchLabeledRuleContext):
            if current.guard() is not None:
                ranges.append(span(current.guard()))
            ranges.append(span(current.switchRuleOutcome()))
            break
        if isinstance(current, JavaParser.UnaryOperatorExpressionContext):
            if current.prefix.text == "!":
                matches_when = not matches_when if matches_when is not None else None
            else:
                matches_when = None
        elif isinstance(current, JavaParser.BinaryOperatorExpressionContext):
            operator = current.bop.text if current.bop is not None else None
            required = True if operator == "&&" else False if operator == "||" else None
            if required is None or matches_when is not required:
                matches_when = None
            elif child is current.expression(0):
                ranges.append(span(current.expression(1)))
        elif isinstance(current, JavaParser.TernaryExpressionContext):
            if child is current.expression(0) and matches_when is not None:
                ranges.append(span(current.expression(1 if matches_when else 2)))
            break
        elif isinstance(
            current,
            (
                JavaParser.MethodCallContext,
                JavaParser.ArgumentsContext,
                JavaParser.ExpressionListContext,
                JavaParser.CastExpressionContext,
            ),
        ):
            matches_when = None
        elif isinstance(current, JavaParser.StatementContext):
            keyword = current.start.text
            if matches_when is not None and keyword in {"if", "while", "for"}:
                branches = current.statement()
                if not isinstance(branches, list):
                    branches = [branches] if branches is not None else []
                matching = 0 if matches_when else 1
                if matching < len(branches) and (keyword == "if" or matches_when):
                    ranges.append(span(branches[matching]))
                if keyword == "if":
                    opposite = 1 if matches_when else 0
                    if opposite < len(branches) and _exits(branches[opposite]):
                        after = _after_if(current)
                        if after:
                            ranges.append(after)
            break
        child, current = current, current.parentCtx
    return ranges


def _record_component(context):
    """Return the enclosing record pattern type and component index of a binding."""
    component = context.parentCtx
    if not isinstance(component, JavaParser.ComponentPatternContext):
        return None
    record = component.parentCtx.parentCtx
    if not isinstance(record, JavaParser.PatternContext) or record.typeType() is None:
        return None
    siblings = component.parentCtx.componentPattern()
    index = next(i for i, sibling in enumerate(siblings) if sibling is component)
    return record.typeType().getText(), index


def add_pattern_declarations(visitor, context):
    if visitor.parent.type not in {
        "method",
        "constructor",
        "lambda",
        "initializer",
    }:
        return
    record_meta = {}
    if context.VAR() is not None:
        identifiers = [context.identifier()]
        variable_type = "var"
        record = _record_component(context)
        if record is not None:
            record_meta = {"record_pattern_type": record[0], "record_component_index": record[1]}
    else:
        declarations = context.variableDeclarators()
        if declarations is None:
            return
        identifiers = [
            item.variableDeclaratorId().identifier() for item in declarations.variableDeclarator()
        ]
        variable_type = context.typeType().getText()
    from core.model import Entity

    for identifier in identifiers:
        name = identifier.getText()
        visitor.entities.append(
            Entity(
                type="local_variable",
                name=name,
                start_line=identifier.start.line,
                end_line=identifier.stop.line,
                parent_name=visitor.parent.name,
                parent_qualified_name=visitor.parent.qualified_name,
                qualified_name=f"{visitor.parent.qualified_name}@pattern:{name}:{identifier.start.line}:{identifier.start.column}",
                meta=visitor._java_meta(
                    {
                        "variable_type": variable_type,
                        "pattern_binding": True,
                        **record_meta,
                        **visitor._lexical_scope(context),
                        "declaration_line": identifier.stop.line,
                        "declaration_column": identifier.stop.column + len(identifier.stop.text),
                        "visibility_ranges": visibility_ranges(context),
                    }
                ),
            )
        )
