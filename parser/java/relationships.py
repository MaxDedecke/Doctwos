"""Extract Java relationships from the recovered ANTLR syntax tree.

This pass intentionally does not resolve symbols across files. It records the
source spelling and enough context for the local resolver and later global
resolver to make that decision without guessing.
"""

from __future__ import annotations

import re

from antlr4 import ParserRuleContext

from core.model import Entity, ParsedEdge

from ._antlr.JavaParser import JavaParser
from ._antlr.JavaParserVisitor import JavaParserVisitor


_TYPE_ENTITY_TYPES = {"class", "interface", "enum", "record", "annotation_type"}
_ASSIGNMENT_OPERATORS = {
    "=",
    "+=",
    "-=",
    "*=",
    "/=",
    "&=",
    "|=",
    "^=",
    ">>=",
    ">>>=",
    "<<=",
    "%=",
}


class JavaRelationshipVisitor(JavaParserVisitor):
    """Collect source-backed Java edges while walking declarations and bodies."""

    def __init__(self, root: Entity, entities: list[Entity]) -> None:
        super().__init__()
        self.edges: list[ParsedEdge] = []
        self._scopes = [root]
        self._types: list[Entity] = []
        self._package_name: str | None = None
        self._entities = entities
        self._header_type_contexts: set[int] = set()
        self._fields_by_type: dict[str, set[str]] = {}
        for entity in entities:
            if entity.type == "field" and entity.parent_qualified_name:
                self._fields_by_type.setdefault(entity.parent_qualified_name, set()).add(
                    entity.name
                )

    @property
    def scope(self) -> Entity:
        return self._scopes[-1]

    @property
    def current_type(self) -> Entity | None:
        return self._types[-1] if self._types else None

    def _span(self, context: ParserRuleContext) -> tuple[int, int]:
        start = context.start.line if context.start is not None else 1
        stop = context.stop.line if context.stop is not None else start
        return start, max(start, stop)

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _edge(
        self,
        edge_type: str,
        destination: str,
        context: ParserRuleContext,
        *,
        meta: dict | None = None,
        source: Entity | None = None,
    ) -> None:
        if not destination:
            return
        start, end = self._span(context)
        source = source or self.scope
        self.edges.append(
            ParsedEdge(
                type=edge_type,
                src_name=source.qualified_name or source.name,
                dst_name=destination,
                resolution="unresolved",
                src_start_line=start,
                src_end_line=end,
                meta={
                    "language": "java",
                    "source_qualified_name": source.qualified_name,
                    **(meta or {}),
                },
            )
        )

    def _entity_for_type(self, name: str) -> Entity | None:
        parent = self.current_type.qualified_name if self.current_type else self._package_name
        candidates = [
            entity
            for entity in self._entities
            if entity.type in _TYPE_ENTITY_TYPES
            and entity.name == name
            and entity.parent_qualified_name == parent
        ]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _parameter_types(context: ParserRuleContext | None) -> tuple[str, ...]:
        if context is None:
            return ()
        result: list[str] = []

        def walk(node: ParserRuleContext) -> None:
            if node.getRuleIndex() == JavaParser.RULE_formalParameter:
                parameter_type = node.typeType().getText()
                if "..." in node.getText():
                    parameter_type += "[]"
                result.append(parameter_type)
                return
            for child in getattr(node, "children", ()) or ():
                if isinstance(child, ParserRuleContext):
                    walk(child)

        walk(context)
        return tuple(result)

    def _entity_for_method(
        self,
        name: str,
        parameter_context: ParserRuleContext | None,
        *,
        constructor: bool = False,
        compact: bool = False,
    ) -> Entity | None:
        owner = self.current_type
        if owner is None:
            return None
        parameter_types = self._parameter_types(parameter_context)
        candidates = [
            entity
            for entity in self._entities
            if entity.parent_qualified_name == owner.qualified_name
            and entity.type == ("constructor" if constructor else "method")
            and entity.name == name
            and tuple(entity.meta.get("parameter_types", ())) == parameter_types
        ]
        if compact:
            candidates = [entity for entity in candidates if entity.meta.get("compact")]
        return candidates[0] if len(candidates) == 1 else None

    def _type_targets(self, context: ParserRuleContext) -> list[tuple[str, ParserRuleContext]]:
        """Return inheritance targets with their exact type contexts."""
        rule = JavaParser.ruleNames[context.getRuleIndex()]
        targets: list[tuple[str, ParserRuleContext]] = []
        if rule == "classDeclaration":
            if context.EXTENDS() is not None:
                targets.extend(("extends", item) for item in self._as_list(context.typeType()))
            if context.IMPLEMENTS() is not None:
                for type_list in self._as_list(context.typeList()):
                    targets.extend(("implements", item) for item in type_list.typeType())
        elif rule == "interfaceDeclaration":
            for type_list in self._as_list(context.typeList()):
                targets.extend(("extends", item) for item in type_list.typeType())
        elif rule in {"enumDeclaration", "recordDeclaration"}:
            for type_list in self._as_list(context.typeList()):
                targets.extend(("implements", item) for item in type_list.typeType())
        return targets

    def _visit_type(self, context: ParserRuleContext, body_context: ParserRuleContext):
        name = context.identifier().getText()
        entity = self._entity_for_type(name)
        if entity is None:
            return self.visitChildren(context)
        targets = self._type_targets(context)
        for relation, type_context in targets:
            self._header_type_contexts.add(id(type_context))
            self._edge(
                "EXTENDS" if relation == "extends" else "IMPLEMENTS",
                type_context.getText(),
                type_context,
                meta={
                    "relation": relation,
                    "owner_type": entity.qualified_name,
                    "target_type": type_context.getText(),
                },
                source=entity,
            )
        self._types.append(entity)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()
            self._types.pop()

    def visitCompilationUnit(self, context):
        package = context.packageDeclaration()
        if package is not None:
            self._package_name = package.qualifiedName().getText()
        return self.visitChildren(context)

    def visitImportDeclaration(self, context):
        destination = context.qualifiedName().getText()
        wildcard = context.MUL() is not None
        if wildcard:
            destination += ".*"
        self._edge(
            "IMPORTS",
            destination,
            context,
            meta={
                "static": context.STATIC() is not None,
                "wildcard": wildcard,
                "target_package": context.qualifiedName().getText(),
            },
            source=self._scopes[0],
        )
        return None

    def visitClassDeclaration(self, context):
        return self._visit_type(context, context.classBody())

    def visitInterfaceDeclaration(self, context):
        return self._visit_type(context, context.interfaceBody())

    def visitEnumDeclaration(self, context):
        return self._visit_type(context, context)

    def visitRecordDeclaration(self, context):
        return self._visit_type(context, context.recordBody())

    def visitAnnotationTypeDeclaration(self, context):
        return self._visit_type(context, context.annotationTypeBody())

    def visitMethodDeclaration(self, context):
        entity = self._entity_for_method(context.identifier().getText(), context.formalParameters())
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitInterfaceCommonBodyDeclaration(self, context):
        entity = self._entity_for_method(context.identifier().getText(), context.formalParameters())
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitConstructorDeclaration(self, context):
        entity = self._entity_for_method(
            context.identifier().getText(), context.formalParameters(), constructor=True
        )
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitCompactConstructorDeclaration(self, context):
        entity = self._entity_for_method(
            context.identifier().getText(), None, constructor=True, compact=True
        )
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitClassBodyDeclaration(self, context):
        block = context.block()
        if block is None or self.current_type is None:
            return self.visitChildren(context)
        name = "<clinit>" if context.STATIC() is not None else "<init-block>"
        start, _ = self._span(context)
        candidates = [
            entity
            for entity in self._entities
            if entity.type == "initializer"
            and entity.parent_qualified_name == self.current_type.qualified_name
            and entity.name == name
            and entity.start_line == start
        ]
        entity = candidates[0] if len(candidates) == 1 else None
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitTypeType(self, context):
        if id(context) not in self._header_type_contexts:
            class_type = context.classOrInterfaceType()
            if class_type is not None:
                self._edge(
                    "USES_TYPE",
                    class_type.getText(),
                    context,
                    meta={"usage": "type", "target_type": class_type.getText()},
                )
        return self.visitChildren(context)

    def _argument_count(self, context: ParserRuleContext) -> int:
        expression_list = context.expressionList()
        return len(expression_list.expression()) if expression_list is not None else 0

    @staticmethod
    def _argument_types(context: ParserRuleContext) -> list[str | None]:
        expression_list = context.expressionList()
        if expression_list is None:
            return []
        result: list[str | None] = []
        for expression in expression_list.expression():
            text = expression.getText()
            if re.fullmatch(r"\d+[lL]?", text):
                result.append("long" if text[-1:] in {"l", "L"} else "int")
            elif re.fullmatch(r"\d+\.\d+[fFdD]?", text):
                result.append("float" if text[-1:] in {"f", "F"} else "double")
            elif text in {"true", "false"}:
                result.append("boolean")
            elif len(text) >= 3 and text[0] == '"' and text[-1] == '"':
                result.append("String")
            elif len(text) >= 3 and text[0] == "'" and text[-1] == "'":
                result.append("char")
            else:
                match = re.fullmatch(r"new([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\(.*\)", text)
                result.append(match.group(1) if match else None)
        return result

    def visitMethodCall(self, context):
        identifier = context.identifier()
        name = identifier.getText() if identifier is not None else context.getText().rstrip("()")
        receiver = None
        parent = context.parentCtx
        if (
            parent is not None
            and JavaParser.ruleNames[parent.getRuleIndex()] == "expression"
            and getattr(parent, "bop", None) is not None
            and parent.bop.text == "."
        ):
            children = getattr(parent, "children", ()) or ()
            if len(children) >= 3:
                receiver = children[0].getText()
        destination = f"{receiver}.{name}" if receiver else name
        invocation_kind = "special" if receiver in {"super", "this"} else "virtual"
        self._edge(
            "CALLS",
            destination,
            context,
            meta={
                "method_name": name,
                "receiver": receiver,
                "argument_count": self._argument_count(context.arguments()),
                "argument_types": self._argument_types(context.arguments()),
                "invocation_kind": invocation_kind,
                "owner_type": self.current_type.qualified_name if self.current_type else None,
            },
        )
        return self.visitChildren(context)

    def visitExplicitGenericInvocation(self, context):
        suffix = context.explicitGenericInvocationSuffix()
        identifier = suffix.identifier() if suffix is not None else None
        if identifier is None:
            return self.visitChildren(context)
        receiver = None
        parent = context.parentCtx
        if (
            parent is not None
            and JavaParser.ruleNames[parent.getRuleIndex()] == "expression"
            and getattr(parent, "bop", None) is not None
            and parent.bop.text == "."
        ):
            children = getattr(parent, "children", ()) or ()
            if len(children) >= 3:
                receiver = children[0].getText()
        name = identifier.getText()
        destination = f"{receiver}.{name}" if receiver else name
        arguments = suffix.arguments()
        self._edge(
            "CALLS",
            destination,
            context,
            meta={
                "method_name": name,
                "receiver": receiver,
                "argument_count": self._argument_count(arguments),
                "argument_types": self._argument_types(arguments),
                "invocation_kind": "virtual" if receiver not in {"super", "this"} else "special",
                "owner_type": self.current_type.qualified_name if self.current_type else None,
                "generic": True,
            },
        )
        return self.visitChildren(context)

    def visitCreator(self, context):
        created_name = context.createdName()
        if (
            created_name is not None
            and created_name.primitiveType() is None
            and context.classCreatorRest() is not None
        ):
            destination = created_name.getText()
            self._edge(
                "INSTANTIATES",
                destination,
                context,
                meta={
                    "target_type": destination,
                    "argument_count": self._argument_count(context.classCreatorRest().arguments())
                    if context.classCreatorRest() is not None
                    else None,
                    "argument_types": self._argument_types(context.classCreatorRest().arguments())
                    if context.classCreatorRest() is not None
                    else [],
                    "invocation_kind": "constructor",
                    "owner_type": self.current_type.qualified_name if self.current_type else None,
                },
            )
        return self.visitChildren(context)

    def _field_names(self) -> set[str]:
        return (
            self._fields_by_type.get(self.current_type.qualified_name, set())
            if self.current_type
            else set()
        )

    def _field_reference(self, context: ParserRuleContext) -> tuple[str, str | None] | None:
        text = context.getText()
        if not text:
            return None
        base_text = text.split("[", 1)[0]
        if "." in base_text:
            receiver, name = base_text.rsplit(".", 1)
            if name in {"this", "super"} or not name:
                return None
            target = name if receiver in {"this", "super"} else base_text
        else:
            name = base_text
            if name not in self._field_names():
                return None
            target = name
        qualified = None
        if name in self._field_names():
            qualified = f"{self.current_type.qualified_name}#{name}"
        return target, qualified

    def _is_write_target(self, context: ParserRuleContext) -> bool:
        node = context
        parent = node.parentCtx
        while parent is not None and JavaParser.ruleNames[parent.getRuleIndex()] == "expression":
            children = getattr(parent, "children", ()) or ()
            if children and children[0] is node:
                operator = getattr(parent, "bop", None)
                if operator is not None and operator.text in _ASSIGNMENT_OPERATORS:
                    return True
                node = parent
                parent = parent.parentCtx
                continue
            break
        return False

    def _emit_field_access(self, context: ParserRuleContext, access: str, mode: str) -> None:
        resolved = self._field_reference(context)
        if resolved is None:
            return
        destination, qualified = resolved
        self._edge(
            mode,
            destination,
            context,
            meta={
                "access": mode.lower(),
                "target_qualified_name": qualified,
                "field_name": destination.rsplit(".", 1)[-1],
            },
        )

    def _handle_expression(self, context):
        operator = getattr(context, "bop", None)
        children = getattr(context, "children", ()) or ()
        if operator is not None and operator.text in _ASSIGNMENT_OPERATORS and children:
            lhs = children[0]
            if isinstance(lhs, ParserRuleContext):
                if operator.text != "=":
                    self._emit_field_access(lhs, lhs.getText(), "READS")
                self._emit_field_access(lhs, lhs.getText(), "WRITES")
        postfix = getattr(context, "postfix", None)
        prefix = getattr(context, "prefix", None)
        if postfix is not None or prefix is not None:
            target = children[0] if children else None
            if isinstance(target, ParserRuleContext):
                target_rule = JavaParser.ruleNames[target.getRuleIndex()]
                if (
                    target_rule != "expression"
                    or getattr(target, "bop", None) is None
                    or target.bop.text != "."
                ):
                    self._emit_field_access(target, target.getText(), "READS")
                self._emit_field_access(target, target.getText(), "WRITES")

        if (
            operator is not None
            and operator.text == "."
            and children
            and isinstance(children[-1], ParserRuleContext)
            and JavaParser.ruleNames[children[-1].getRuleIndex()] == "identifier"
            and not any(
                JavaParser.ruleNames[c.getRuleIndex()] == "methodCall"
                for c in children
                if isinstance(c, ParserRuleContext)
            )
            and not (
                context.parentCtx is not None
                and JavaParser.ruleNames[context.parentCtx.getRuleIndex()] == "expression"
                and getattr(context.parentCtx, "bop", None) is not None
                and context.parentCtx.bop.text == "."
                and (getattr(context.parentCtx, "children", ()) or [None])[0] is context
            )
        ):
            if not self._is_write_target(context):
                self._emit_field_access(context, context.getText(), "READS")
        return self.visitChildren(context)

    # ``expression`` is a labelled ANTLR rule.  The generated visitor
    # dispatches to the labelled alternatives below rather than to a generic
    # ``visitExpression`` method.
    def visitBinaryOperatorExpression(self, context):
        return self._handle_expression(context)

    def visitMemberReferenceExpression(self, context):
        return self._handle_expression(context)

    def visitPostIncrementDecrementOperatorExpression(self, context):
        return self._handle_expression(context)

    def visitUnaryOperatorExpression(self, context):
        return self._handle_expression(context)

    def visitPrimary(self, context):
        identifier = context.identifier()
        if identifier is not None and not self._is_write_target(context):
            self._emit_field_access(context, identifier.getText(), "READS")
        return self.visitChildren(context)
