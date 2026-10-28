"""Local declarations and exact initializer locations used by type inference."""

import re

from core.model import Entity
from ._antlr.JavaParser import JavaParser


def add_local_declarations(visitor, context):
    if visitor.parent.type not in {"method", "constructor", "lambda", "initializer"}:
        return
    initializer_meta = {}
    if context.VAR() is not None:
        declarations = [(context.identifier(), None)]
        variable_type = "var"
        initializer = context.expression()
        text = initializer.getText() if initializer is not None else ""
        match = re.fullmatch(r"new([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\(.*\)", text)
        inferred_type = match.group(1) if match else None
        if (
            isinstance(
                initializer,
                (
                    JavaParser.MethodCallExpressionContext,
                    JavaParser.MemberReferenceExpressionContext,
                ),
            )
            and initializer.methodCall() is not None
            and len(text) <= 1000
        ):
            initializer_meta = {
                "initializer_expression": text,
                "initializer_line": initializer.methodCall().start.line,
                "initializer_column": initializer.methodCall().start.column,
            }
    else:
        variable_type = context.typeType().getText()
        inferred_type = None
        declarations = [
            (item.variableDeclaratorId().identifier(), item)
            for item in context.variableDeclarators().variableDeclarator()
        ]
    for identifier, declarator in declarations:
        start_line, end_line = visitor._span(declarator or context)
        name = identifier.getText()
        visitor.entities.append(
            Entity(
                type="local_variable",
                name=name,
                start_line=start_line,
                end_line=end_line,
                parent_name=visitor.parent.name,
                parent_qualified_name=visitor.parent.qualified_name,
                qualified_name=f"{visitor.parent.qualified_name}@local:{name}:{start_line}:{identifier.start.column}",
                meta=visitor._java_meta(
                    {
                        "variable_type": variable_type,
                        **visitor._lexical_scope(context),
                        "declaration_line": identifier.start.line,
                        "declaration_column": identifier.stop.column + len(identifier.stop.text),
                        **({"inferred_type": inferred_type} if inferred_type else {}),
                        **initializer_meta,
                    }
                ),
            )
        )
