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
from .variables import select_visible_variable


_TYPE_ENTITY_TYPES = {
    "class",
    "interface",
    "enum",
    "record",
    "annotation_type",
    "local_class",
    "anonymous_class",
}
_MAX_CONDITION_CHARS = 120
# Datenfluss je Routine (`meta["data_flow"]`, siehe docs/ENTSCHEIDUNGEN.md E-15): Obergrenzen, damit die Tabelle klein bleibt.
_FLOW_STATEMENTS = 80
_FLOW_SOURCES = 8
_FLOW_TEXT = 160
_ROUTINE_SCOPE_TYPES = {"method", "constructor", "lambda", "initializer"}
# Ab hier gehört ein Aufruf zu einem anderen Ablauf (eigene Methode/Lambda/Klasse).
_CONTROL_PATH_STOP_RULES = {
    "methodDeclaration", "constructorDeclaration", "interfaceMethodDeclaration",
    "lambdaExpression", "classBody", "compactConstructorDeclaration",
}

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


# Statische JDK-Fabriken, deren Rückgabetyp der Typname selbst bestimmt (O-309): `List.of(...)` ist eine `List`.
_STATIC_FACTORY_TYPES = {
    "List": {"of", "copyOf"}, "Set": {"of", "copyOf"}, "Map": {"of", "copyOf", "ofEntries"},
    "Optional": {"of", "ofNullable", "empty"}, "Arrays": {"asList"}, "String": {"valueOf", "format", "join"},
}
_STATIC_FACTORY_RETURNS = {("Arrays", "asList"): "List", ("String", "valueOf"): "String",
                           ("String", "format"): "String", ("String", "join"): "String"}


def _whole_call(text: str, open_index: int) -> bool:
    """Ob die Klammer ab `open_index` erst am Ende des Ausdrucks schließt (der Aufruf ist der ganze Ausdruck)."""
    depth = 0
    in_string = False
    for index in range(open_index, len(text)):
        char = text[index]
        if char == '"' and text[index - 1:index] != "\\":
            in_string = not in_string
        elif not in_string:
            depth += (char == "(") - (char == ")")
            if depth == 0:
                return index == len(text) - 1
    return False


def _inferred_expression_type(text: str) -> str | None:
    """Belegbarer Typ eines Argumentausdrucks, sonst None (nie raten)."""
    if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.class", text):
        return "Class"
    cast = re.fullmatch(
        r"\(([A-Z][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(?:<[^()]*>)?\)[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\(.*\))?", text
    )
    if cast:  # `(Typ) name.chain(...)`: kein Operator außerhalb von Klammern, der den Typ ändern könnte
        return cast.group(1)
    if re.match(r'"(?:[^"\\]|\\.)*"\+', text):
        return "String"  # Zeichenkettenliteral + Ausdruck ist immer ein String
    factory = re.match(r"([A-Z][\w$]*)\.([a-z][\w$]*)\(", text)
    if factory and factory.group(2) in _STATIC_FACTORY_TYPES.get(factory.group(1), ()) and _whole_call(text, factory.end() - 1):
        return _STATIC_FACTORY_RETURNS.get((factory.group(1), factory.group(2)), factory.group(1))
    return None


class JavaRelationshipVisitor(JavaParserVisitor):
    """Collect source-backed Java edges while walking declarations and bodies."""

    def __init__(self, root: Entity, entities: list[Entity]) -> None:
        super().__init__()
        self.edges: list[ParsedEdge] = []
        self._scopes = [root]
        self._types: list[Entity] = []
        self._package_name: str | None = None
        self._imports: set[str] = set()
        self._entities = entities
        self._header_type_contexts: set[int] = set()
        self._fields_by_type: dict[str, set[str]] = {}
        self._variables: dict[tuple[str, str], list[Entity]] = {}
        self._entity_qnames: set[str] = set()
        self.flows: dict[str, list[dict]] = {}
        for entity in entities:
            self._entity_qnames.add(entity.qualified_name)
            if entity.type == "field" and entity.parent_qualified_name:
                self._fields_by_type.setdefault(entity.parent_qualified_name, set()).add(
                    entity.name
                )
            if entity.type in {"local_variable", "parameter"} and entity.parent_qualified_name:
                self._variables.setdefault((entity.parent_qualified_name, entity.name), []).append(entity)

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

    @staticmethod
    def _source_text(context: ParserRuleContext | None) -> str:
        """Originaltext eines Teilbaums (mit Leerzeichen), gekürzt und einzeilig."""
        if context is None or context.start is None or context.stop is None:
            return ""
        text = context.start.getInputStream().getText(context.start.start, context.stop.stop)
        text = " ".join(text.split())
        return text if len(text) <= _MAX_CONDITION_CHARS else text[: _MAX_CONDITION_CHARS - 1] + "…"

    def _control_path(self, context: ParserRuleContext) -> list[dict[str, str]]:
        """Bedingungen und Schleifen, unter denen ein Aufruf steht (außen → innen).

        Gleiche Form wie `control_path` der COBOL-Kanten, damit die Ablaufansicht
        beide Sprachen einheitlich darstellt.
        """
        path: list[dict[str, str]] = []
        child = context
        current = context.parentCtx
        while current is not None:
            rule = JavaParser.ruleNames[current.getRuleIndex()]
            if rule in _CONTROL_PATH_STOP_RULES:
                break
            if rule == "statement" and current.start is not None:
                keyword = current.start.text.casefold()
                statements = self._as_list(current.statement())
                expressions = self._as_list(current.expression())
                body = child in statements
                if keyword == "if" and body and expressions:
                    branch = "ELSE" if len(statements) > 1 and child is statements[1] else "THEN"
                    path.append({"type": "IF", "branch": branch, "condition": self._source_text(expressions[0])})
                elif keyword == "while" and body and expressions:
                    path.append({"type": "LOOP", "kind": "WHILE", "text": self._source_text(expressions[0])})
                elif keyword == "do" and body and expressions:
                    path.append({"type": "LOOP", "kind": "DO_WHILE", "text": self._source_text(expressions[0])})
                elif keyword == "for" and body:
                    control = current.forControl()
                    is_each = control is not None and control.enhancedForControl() is not None
                    path.append({"type": "LOOP", "kind": "FOR_EACH" if is_each else "FOR", "text": self._source_text(control)})
                elif keyword == "switch" and expressions:
                    labels = ""
                    if JavaParser.ruleNames[child.getRuleIndex()] == "switchBlockStatementGroup":
                        labels = ", ".join(self._source_text(label) for label in self._as_list(child.switchLabel()))
                    path.append({"type": "SWITCH", "branch": "CASE", "subject": self._source_text(expressions[0]), "when": labels})
            child = current
            current = current.parentCtx
        path.reverse()
        return path

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
        start_column = context.start.column if context.start is not None else None
        end_column = (
            context.stop.column + len(context.stop.text)
            if context.stop is not None and context.stop.line == start and context.stop.text
            else None
        )
        edge_meta = {
            "language": "java",
            "source_qualified_name": source.qualified_name,
            "src_start_column": start_column,
            "src_end_column": end_column,
            **(meta or {}),
        }
        if edge_type == "CALLS":
            current = context.parentCtx
            while current is not None:
                rule = JavaParser.ruleNames[current.getRuleIndex()]
                if rule == "catchClause":
                    catch_type = current.catchType().getText()
                    edge_meta.update({
                        "control_role": "exception_handler",
                        "control_context": f"catch({catch_type})",
                        "exception_types": [part for part in catch_type.split("|") if part],
                    })
                    break
                if rule == "finallyBlock":
                    edge_meta.update({
                        "control_role": "cleanup",
                        "control_context": "finally",
                    })
                    break
                if (
                    rule == "statement"
                    and current.start is not None
                    and current.start.text.casefold() == "try"
                ):
                    edge_meta.update({
                        "control_role": "try_body",
                        "control_context": "try",
                    })
                    break
                current = current.parentCtx
        if edge_type == "CALLS":
            control_path = self._control_path(context)
            if control_path:
                edge_meta["control_path"] = control_path
        self.edges.append(
            ParsedEdge(
                type=edge_type,
                src_name=source.qualified_name or source.name,
                dst_name=destination,
                resolution="unresolved",
                src_start_line=start,
                src_end_line=end,
                meta=edge_meta,
            )
        )

    def _entity_for_type(self, name: str) -> Entity | None:
        if self.current_type is None:
            # Declarations without a package are children of the compilation
            # unit, not of a synthetic ``None`` parent.
            parent = self._package_name or self._scopes[0].qualified_name
        elif self._scopes[-1].type in {"method", "constructor", "lambda"}:
            parent = self._scopes[-1].qualified_name
        else:
            parent = self.current_type.qualified_name
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
        self._imports.add(destination)
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

    def visitAnnotation(self, context):
        name = context.qualifiedName().getText() if context.qualifiedName() is not None else ""
        if name.rsplit(".", 1)[-1] == "Value" and (
            name != "Value" or self._imports_package("org.springframework.")
        ):
            for key in re.findall(r"\$\{([\w.\-]+)(?::[^}]*)?\}", self._source_text(context)):
                self._property_key_edge(key, context, "spring_value", "certain")
        return self.visitChildren(context)

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

    @staticmethod
    def _string_literal(expression: ParserRuleContext | None) -> str | None:
        """Wert eines reinen Zeichenkettenliterals, sonst None (kein Raten bei Ausdrücken)."""
        text = expression.getText() if expression is not None else ""
        match = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', text)
        return match.group(1) if match else None

    def _first_string_argument(self, arguments: ParserRuleContext | None) -> str | None:
        expression_list = arguments.expressionList() if arguments is not None else None
        expressions = expression_list.expression() if expression_list is not None else []
        return self._string_literal(expressions[0]) if expressions else None

    def _property_key_edge(self, key: str, context: ParserRuleContext, via: str, certainty: str) -> None:
        """Verweis auf einen `.properties`-Schlüssel; aufgelöst wird später gegen die Property-Entities."""
        if not key or not re.fullmatch(r"[\w.\-]+", key):
            return
        self._edge(
            "REFERENCES_PROPERTY_KEY",
            key,
            context,
            meta={
                "property_key": key, "key_source": via, "certainty": certainty,
                "target_entity_type": "property",
                "owner_type": self.current_type.qualified_name if self.current_type else None,
            },
        )

    def _imports_package(self, prefix: str) -> bool:
        return any(name.startswith(prefix) for name in self._imports)

    def _argument_count(self, context: ParserRuleContext) -> int:
        expression_list = context.expressionList()
        return len(expression_list.expression()) if expression_list is not None else 0

    @staticmethod
    def _argument_expressions(context: ParserRuleContext) -> list[str]:
        expression_list = context.expressionList()
        if expression_list is None:
            return []
        return [expression.getText()[:500] for expression in expression_list.expression()[:16]]

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
                result.append(match.group(1) if match else _inferred_expression_type(text))
        return result

    def visitMethodCall(self, context):
        identifier = context.identifier()
        if identifier is not None:
            name = identifier.getText()
        elif context.SUPER() is not None:
            name = "super"  # Konstruktordelegation; getText() enthielte die Argumente
        elif context.THIS() is not None:
            name = "this"
        else:
            name = context.getText().rstrip("()")
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
                "symbol_start_column": (
                    identifier.start.column if identifier is not None and identifier.start is not None else None
                ),
                "symbol_end_column": (
                    identifier.stop.column + len(identifier.stop.text)
                    if identifier is not None and identifier.stop is not None and identifier.stop.text
                    else None
                ),
                "receiver": receiver,
                "argument_count": self._argument_count(context.arguments()),
                "argument_types": self._argument_types(context.arguments()),
                "argument_expressions": self._argument_expressions(context.arguments()),
                "argument_refs": self._argument_refs(context.arguments()),
                "invocation_kind": invocation_kind,
                "owner_type": self.current_type.qualified_name if self.current_type else None,
            },
        )
        # Wicket `Component#getString("key")`: nur ohne Receiver und mit Wicket-Import belegt.
        if name == "getString" and receiver in (None, "this") and self._imports_package("org.apache.wicket."):
            key = self._first_string_argument(context.arguments())
            if key is not None:
                self._property_key_edge(key, context, "wicket_get_string", "probable")
        # Class-literal receivers prove java.lang.Class resource semantics.
        # Arbitrary methods named getResource are not sufficient evidence.
        if name in {"getResource", "getResourceAsStream"} and receiver and receiver.endswith(".class"):
            arguments = context.arguments().expressionList()
            expressions = arguments.expression() if arguments is not None else []
            if len(expressions) == 1:
                expression = expressions[0].getText()
                literal = re.fullmatch(r'"([^"\\]*)"', expression)
                value = literal.group(1) if literal else None
                # Relative Class resources require the receiver's package; only
                # the current class is known without external type resolution.
                owner = receiver[:-6]
                current = self.current_type
                known_owner = current and owner in {current.name, current.qualified_name}
                target = value.lstrip("/") if value and value.startswith("/") else (
                    "/".join(filter(None, [(self._package_name or "").replace(".", "/"), value]))
                    if value and known_owner else None
                )
                self._edge("USES_RESOURCE", value or expression, context, meta={
                    "resource_base": "classpath", "target_file_path": target,
                    "resource_expression": expression, "receiver": receiver,
                })
                if not literal:
                    self.edges[-1].resolution = "dynamic"
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
                "symbol_start_column": identifier.start.column if identifier.start is not None else None,
                "symbol_end_column": (
                    identifier.stop.column + len(identifier.stop.text)
                    if identifier.stop is not None and identifier.stop.text else None
                ),
                "receiver": receiver,
                "argument_count": self._argument_count(arguments),
                "argument_types": self._argument_types(arguments),
                "argument_expressions": self._argument_expressions(arguments),
                "argument_refs": self._argument_refs(arguments),
                "invocation_kind": "virtual" if receiver not in {"super", "this"} else "special",
                "owner_type": self.current_type.qualified_name if self.current_type else None,
                "generic": True,
            },
        )
        return self.visitChildren(context)

    def visitLambdaExpression(self, context):
        start_line, _ = self._span(context)
        col = context.start.column
        candidates = [
            e
            for e in self._entities
            if e.type == "lambda"
            and e.start_line == start_line
            and e.qualified_name.endswith(f"@lambda:{start_line}:{col}")
        ]
        entity = candidates[0] if candidates else None
        if entity is None:
            return self.visitChildren(context)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()

    def visitMethodReferenceExpression(self, context):
        reference = context.getText()
        if "::" not in reference:
            return self.visitChildren(context)
        receiver, member = reference.split("::", 1)
        member = re.sub(r"^<.*>", "", member)
        if member != "new" and not re.fullmatch(r"[A-Za-z_$][\w$]*", member):
            return self.visitChildren(context)
        receiver_kind = (
            "special" if receiver in {"this", "super"}
            else "type" if receiver[:1].isupper() or "." in receiver
            else "expression"
        )
        self._edge(
            "REFERENCES_METHOD",
            reference,
            context,
            meta={
                "method_name": member,
                "receiver": receiver,
                "receiver_kind": receiver_kind,
                "reference_kind": "constructor" if member == "new" else "method",
                "invocation_kind": "method_reference",
                "owner_type": self.current_type.qualified_name if self.current_type else None,
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
                    "argument_expressions": self._argument_expressions(context.classCreatorRest().arguments())
                    if context.classCreatorRest() is not None
                    else [],
                    "argument_refs": self._argument_refs(context.classCreatorRest().arguments())
                    if context.classCreatorRest() is not None
                    else [],
                    "invocation_kind": "constructor",
                    "owner_type": self.current_type.qualified_name if self.current_type else None,
                },
            )

        rest = context.classCreatorRest()
        if (
            created_name is not None
            and rest is not None
            and created_name.getText().rsplit(".", 1)[-1] == "ResourceModel"
        ):
            key = self._first_string_argument(rest.arguments())
            if key is not None:
                self._property_key_edge(key, context, "wicket_resource_model", "certain")
        class_body = rest.classBody() if rest is not None else None
        if class_body is None:
            return self.visitChildren(context)

        if created_name is not None:
            self.visit(created_name)
        if rest.arguments() is not None:
            self.visit(rest.arguments())

        start_line, _ = self._span(class_body)
        col = class_body.start.column
        candidates = [
            e
            for e in self._entities
            if e.type == "anonymous_class"
            and e.start_line == start_line
            and e.qualified_name.endswith(f"@anonymous:{start_line}:{col}")
        ]
        entity = candidates[0] if candidates else None
        if entity is None:
            return self.visit(class_body)

        self._types.append(entity)
        self._scopes.append(entity)
        try:
            return self.visit(class_body)
        finally:
            self._scopes.pop()
            self._types.pop()

    # ------------------------------------------------------------------ data flow (meta["data_flow"], E-15)
    def _flow_holder(self) -> Entity | None:
        """The routine a statement belongs to; a field initializer belongs to its type."""
        for scope in reversed(self._scopes):
            if scope.type in _ROUTINE_SCOPE_TYPES:
                return scope
        return self.current_type

    def _classify_name(self, name: str, line: int, column: int) -> dict:
        """What a name denotes at one position: local variable or parameter by lexical scope, field, member, or unknown."""
        root = name.split("[", 1)[0]
        if root.startswith("this."):
            root = root[5:]
            field = root if "." not in root else None
            if field and field in self._field_names() and self.current_type is not None:
                return {"kind": "field", "name": field, "qualified_name": f"{self.current_type.qualified_name}#{field}"}
            return {"kind": "member", "name": name.split("[", 1)[0]}
        if "." in root:
            return {"kind": "member", "name": root}
        scopes = [s.qualified_name for s in reversed(self._scopes) if s.type in _ROUTINE_SCOPE_TYPES]
        for scope_name in scopes:
            variables = self._variables.get((scope_name, root), [])
            if variables:
                selected, status = select_visible_variable(variables, line, column)
                if status == "found":
                    return {"kind": selected[0].type, "name": root, "qualified_name": selected[0].qualified_name}
                if status == "ambiguous":
                    return {"kind": "unknown", "name": root}
        if root in self._field_names() and self.current_type is not None:
            return {"kind": "field", "name": root, "qualified_name": f"{self.current_type.qualified_name}#{root}"}
        return {"kind": "unknown", "name": root}

    def _classify_context(self, context: ParserRuleContext) -> dict:
        start = context.start
        return self._classify_name(
            self._source_text(context).replace(" ", ""),
            start.line if start is not None else 0,
            start.column if start is not None else 0,
        )

    def _flow_sources(self, context: ParserRuleContext | None) -> list[dict]:
        """Names, calls and creations an expression reads, in source order (bounded; literals only when nothing else)."""
        found: list[dict] = []
        state = {"literal": False}

        def add(item: dict) -> None:
            key = (item.get("kind"), item.get("name"), item.get("via"))
            if len(found) < _FLOW_SOURCES and all((f.get("kind"), f.get("name"), f.get("via")) != key for f in found):
                found.append(item)

        def walk(node, via: str | None = None) -> None:
            if not isinstance(node, ParserRuleContext) or len(found) >= _FLOW_SOURCES:
                return
            rule = JavaParser.ruleNames[node.getRuleIndex()]
            if rule == "lambdaExpression":
                add({"kind": "lambda", "name": "lambda"})
                return
            if rule == "literal":
                state["literal"] = True
                return
            if rule == "creator":
                name = node.createdName().getText() if node.createdName() is not None else "?"
                add({"kind": "new", "name": name, **({"via": via} if via else {})})
                for child in node.getChildren():
                    if isinstance(child, ParserRuleContext) and JavaParser.ruleNames[child.getRuleIndex()] != "createdName":
                        walk(child, f"new:{name}")
                return
            if rule == "primary":
                identifier = node.identifier()
                if identifier is not None:
                    item = self._classify_context(identifier)
                    add({**item, **({"via": via} if via else {})})
                    return
            if rule == "expression":
                operator = getattr(node, "bop", None)
                children = getattr(node, "children", ()) or ()
                if operator is not None and operator.text == "." and children:
                    last = children[-1]
                    last_rule = JavaParser.ruleNames[last.getRuleIndex()] if isinstance(last, ParserRuleContext) else None
                    if last_rule == "methodCall":
                        name = last.identifier().getText() if last.identifier() is not None else last.getText().split("(")[0]
                        walk(children[0], via or "receiver")
                        add({"kind": "call", "name": f"{self._source_text(children[0])}.{name}"[:80],
                             **({"via": via} if via else {})})
                        walk(last.arguments(), f"call:{name}")
                        return
                    if last_rule == "identifier":
                        item = self._classify_context(node)
                        add({**item, **({"via": via} if via else {})})
                        if self._source_text(children[0]) != "this":
                            walk(children[0], via or "member")
                        return
            if rule == "methodCall":  # unqualified call: `build(a, b)`
                name = node.identifier().getText() if node.identifier() is not None else "this"
                add({"kind": "call", "name": name, **({"via": via} if via else {})})
                walk(node.arguments(), f"call:{name}")
                return
            for child in node.getChildren():
                walk(child, via)

        walk(context)
        if not found and state["literal"]:
            found.append({"kind": "literal", "name": self._source_text(context)[:40]})
        return found

    def _flow_statement(self, context: ParserRuleContext) -> tuple[int, int, str]:
        """Start line, end line and text of the statement a node belongs to (stops at a lambda or class boundary)."""
        node = context
        while node is not None:
            rule = JavaParser.ruleNames[node.getRuleIndex()]
            if rule in {"statement", "localVariableDeclaration", "fieldDeclaration", "lambdaBody"}:
                break
            if rule in {"lambdaExpression", "classBody", "methodDeclaration"}:
                node = context
                break
            node = node.parentCtx
        node = node or context
        start, end = self._span(node)
        return start, end, self._source_text(node)[:_FLOW_TEXT]

    def _record_flow(self, context: ParserRuleContext, operation: str, target: dict, sources_from: ParserRuleContext | None) -> None:
        holder = self._flow_holder()
        if holder is None:
            return
        statements = self.flows.setdefault(holder.qualified_name, [])
        if len(statements) >= _FLOW_STATEMENTS:
            return
        line, end_line, text = self._flow_statement(context)
        statements.append({
            "line": line, "end_line": end_line, "operation": operation, "target": target,
            "sources": self._flow_sources(sources_from), "text": text,
        })

    def _argument_refs(self, arguments: ParserRuleContext | None) -> list[dict | None]:
        """For each argument: the data entity it names when it is a plain name (`id`, `this.x`), else None."""
        expression_list = arguments.expressionList() if arguments is not None else None
        if expression_list is None:
            return []
        refs: list[dict | None] = []
        for expression in expression_list.expression()[:16]:
            text = self._source_text(expression).replace(" ", "")
            if re.fullmatch(r"(?:this\.)?[A-Za-z_$][\w$]*", text):
                item = self._classify_context(expression)
                refs.append({k: v for k, v in item.items() if k in {"kind", "name", "qualified_name"}} if item["kind"] != "unknown" else None)
            else:
                refs.append(None)
        return refs

    def _declarator_target(self, identifier: ParserRuleContext, declarator: ParserRuleContext, local: bool) -> dict:
        name = identifier.getText()
        if local:
            holder = self._flow_holder()
            line = self._span(declarator)[0]
            qualified = f"{holder.qualified_name}@local:{name}:{line}:{identifier.start.column}" if holder is not None else ""
            for scope in (s for s in reversed(self._scopes) if s.type in _ROUTINE_SCOPE_TYPES):
                for kind in ("local", "foreach"):
                    candidate = f"{scope.qualified_name}@{kind}:{name}:{line}:{identifier.start.column}"
                    if candidate in self._entity_qnames:
                        return {"kind": "local_variable", "name": name, "qualified_name": candidate}
            return {"kind": "local_variable", "name": name, "qualified_name": qualified} if qualified in self._entity_qnames else {"kind": "unknown", "name": name}
        if self.current_type is not None and name in self._field_names():
            return {"kind": "field", "name": name, "qualified_name": f"{self.current_type.qualified_name}#{name}"}
        return {"kind": "unknown", "name": name}

    def visitVariableDeclarator(self, context):
        initializer = context.variableInitializer()
        parent = context.parentCtx.parentCtx if context.parentCtx is not None else None
        owner = JavaParser.ruleNames[parent.getRuleIndex()] if parent is not None else None
        if initializer is not None and owner in {"localVariableDeclaration", "fieldDeclaration"}:
            identifier = context.variableDeclaratorId().identifier()
            self._record_flow(context, "init", self._declarator_target(identifier, context, owner == "localVariableDeclaration"), initializer)
        return self.visitChildren(context)

    def visitLocalVariableDeclaration(self, context):
        if context.VAR() is not None and context.identifier() is not None and context.expression() is not None:
            self._record_flow(
                context, "init", self._declarator_target(context.identifier(), context, True), context.expression()
            )
        return self.visitChildren(context)

    def visitStatement(self, context):
        if context.RETURN() is not None:
            expressions = self._as_list(context.expression())  # die Regel nennt `expression` mehrfach: Liste
            if expressions:
                self._record_flow(context, "return", {"kind": "return", "name": "return"}, expressions[0])
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
                rhs = children[-1] if len(children) >= 3 and isinstance(children[-1], ParserRuleContext) else None
                if rhs is not None:
                    self._record_flow(
                        context, "assign" if operator.text == "=" else "compound_assign", self._classify_context(lhs), rhs
                    )
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
                if (postfix is not None and postfix.text in {"++", "--"}) or (prefix is not None and prefix.text in {"++", "--"}):
                    self._record_flow(context, "increment", self._classify_context(target), None)

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
