"""Extract Java declarations from the generated ANTLR parse tree."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from antlr4 import ParserRuleContext

from core.model import Entity

from ._antlr.JavaParser import JavaParser
from ._antlr.JavaParserVisitor import JavaParserVisitor


_TYPE_RULES = {
    "classDeclaration": "class",
    "interfaceDeclaration": "interface",
    "enumDeclaration": "enum",
    "recordDeclaration": "record",
    "annotationTypeDeclaration": "annotation_type",
}
_JAVA_MODIFIERS = {
    "abstract",
    "default",
    "final",
    "native",
    "private",
    "protected",
    "public",
    "sealed",
    "static",
    "strictfp",
    "synchronized",
    "transient",
    "volatile",
    "non-sealed",
}
_DECLARATION_BOUNDARIES = {
    "classBodyDeclaration",
    "interfaceBodyDeclaration",
    "annotationTypeElementDeclaration",
    "typeDeclaration",
    "compactConstructorDeclaration",
}


class JavaDeclarationVisitor(JavaParserVisitor):
    """Collect named declarations while deliberately skipping executable bodies."""

    def __init__(self, root: Entity) -> None:
        super().__init__()
        self.entities = [root]
        self._parents = [root]
        self._package_name: str | None = None
        self._module_path = root.meta.get("module")
        self._source_set = root.meta.get("source_set")
        self._source_kind = root.meta.get("source_kind")
        self._lombok_policies: list[set[str]] = []
        self._explicit_method_keys: list[set[tuple[str, tuple[str, ...]]]] = []

    @property
    def parent(self) -> Entity:
        return self._parents[-1]

    def _span(self, context: ParserRuleContext) -> tuple[int, int]:
        start = context.start.line if context.start is not None else 1
        stop = context.stop.line if context.stop is not None else start
        return start, max(start, stop)

    def _modifier_meta(self, context: ParserRuleContext) -> dict:
        current = context
        while current is not None:
            values: list[str] = []
            for rule_name in (
                "modifier",
                "interfaceMethodModifier",
                "classOrInterfaceModifier",
                "constantModifier",
            ):
                accessor = getattr(current, rule_name, None)
                if accessor is None:
                    continue
                children = accessor()
                if children is None:
                    continue
                if not isinstance(children, list):
                    children = [children]
                values.extend(
                    child.getText() for child in children if child.getText() in _JAVA_MODIFIERS
                )
            rule_name = JavaParser.ruleNames[current.getRuleIndex()]
            if values or rule_name in _DECLARATION_BOUNDARIES:
                modifiers = list(dict.fromkeys(values))
                visibility = next(
                    (item for item in ("public", "protected", "private") if item in modifiers),
                    "package",
                )
                return {"modifiers": modifiers, "visibility": visibility}
            current = current.parentCtx
        return {"modifiers": [], "visibility": "package"}

    def _declaration_context(self, context: ParserRuleContext) -> ParserRuleContext:
        current = context
        while current is not None:
            rule_name = JavaParser.ruleNames[current.getRuleIndex()]
            if rule_name in _DECLARATION_BOUNDARIES:
                return current
            current = current.parentCtx
        return context

    def _annotation_details(self, context: ParserRuleContext) -> list[tuple[str, str]]:
        details: list[tuple[str, str]] = []
        current = context
        while current is not None:
            annotations = []
            direct = getattr(current, "annotation", None)
            if direct is not None:
                value = direct()
                if value is not None:
                    annotations.extend(value if isinstance(value, list) else [value])
            for rule_name in ("modifier", "interfaceMethodModifier", "classOrInterfaceModifier"):
                accessor = getattr(current, rule_name, None)
                if accessor is None:
                    continue
                modifiers = accessor()
                if modifiers is None:
                    continue
                if not isinstance(modifiers, list):
                    modifiers = [modifiers]
                for modifier in modifiers:
                    nested = getattr(modifier, "classOrInterfaceModifier", lambda: None)()
                    candidates = nested if isinstance(nested, list) else [nested]
                    candidates.append(modifier)
                    for candidate in candidates:
                        annotation = getattr(candidate, "annotation", lambda: None)()
                        if annotation is None:
                            continue
                        annotations.extend(
                            annotation if isinstance(annotation, list) else [annotation]
                        )
            for annotation in annotations:
                details.append((annotation.qualifiedName().getText(), annotation.getText()))
            if JavaParser.ruleNames[current.getRuleIndex()] in _DECLARATION_BOUNDARIES:
                break
            current = current.parentCtx
        return details

    def _annotation_names(self, context: ParserRuleContext) -> list[str]:
        return [name for name, _ in self._annotation_details(context)]

    def _explicit_methods(
        self, body_context: ParserRuleContext
    ) -> set[tuple[str, tuple[str, ...]]]:
        methods: set[tuple[str, tuple[str, ...]]] = set()

        def walk(node: ParserRuleContext, *, root: bool = False) -> None:
            rule_name = JavaParser.ruleNames[node.getRuleIndex()]
            if not root and rule_name in _TYPE_RULES:
                return
            if rule_name in {"methodDeclaration", "interfaceCommonBodyDeclaration"}:
                methods.add(
                    (
                        node.identifier().getText(),
                        tuple(self._parameter_types(node.formalParameters())),
                    )
                )
                return
            if rule_name == "annotationMethodRest":
                methods.add((node.identifier().getText(), ()))
                return
            if rule_name in {"block", "expression", "variableInitializer"}:
                return
            for child in getattr(node, "children", ()) or ():
                if isinstance(child, ParserRuleContext):
                    walk(child)

        walk(body_context, root=True)
        return methods

    @contextmanager
    def _type_scope(
        self,
        entity: Entity,
        declaration_context: ParserRuleContext,
        body_context: ParserRuleContext,
    ) -> Iterator[None]:
        names = {name.rsplit(".", 1)[-1] for name in self._annotation_names(declaration_context)}
        self._parents.append(entity)
        self._lombok_policies.append(names)
        self._explicit_method_keys.append(self._explicit_methods(body_context))
        try:
            yield
        finally:
            self._explicit_method_keys.pop()
            self._lombok_policies.pop()
            self._parents.pop()

    def _add(
        self,
        context: ParserRuleContext,
        entity_type: str,
        name: str,
        qualified_name: str,
        *,
        meta: dict | None = None,
    ) -> Entity:
        start_line, end_line = self._span(context)
        entity = Entity(
            type=entity_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
            parent_name=self.parent.name,
            qualified_name=qualified_name,
            parent_qualified_name=self.parent.qualified_name,
            meta={
                "language": "java",
                **({"module": self._module_path} if self._module_path is not None else {}),
                **({"source_set": self._source_set} if self._source_set is not None else {}),
                **({"source_kind": self._source_kind} if self._source_kind is not None else {}),
                **(meta or {}),
            },
        )
        self.entities.append(entity)
        return entity

    def _within(self, entity: Entity, context: ParserRuleContext):
        self._parents.append(entity)
        try:
            return self.visit(context)
        finally:
            self._parents.pop()

    def visitCompilationUnit(self, context):
        package_context = context.packageDeclaration()
        if package_context is not None:
            self._package_name = package_context.qualifiedName().getText()
            package = self._add(
                package_context,
                "package",
                self._package_name,
                self._package_name,
                meta={"package": self._package_name},
            )
            self._parents.append(package)
            try:
                modular = context.modularCompulationUnit()
                if modular is not None:
                    self.visit(modular)
                for declaration in context.typeDeclaration():
                    self.visit(declaration)
            finally:
                self._parents.pop()
            return None

        modular = context.modularCompulationUnit()
        if modular is not None:
            self.visit(modular)
        for declaration in context.typeDeclaration():
            self.visit(declaration)
        return None

    def visitModuleDeclaration(self, context):
        name = context.qualifiedName().getText()
        self._add(context, "module", name, name, meta={"module": name})
        return None

    def _type(self, context, entity_type: str, body_context: ParserRuleContext):
        name = context.identifier().getText()
        if self.parent.type in _TYPE_RULES.values():
            qualified_name = f"{self.parent.qualified_name}.{name}"
        elif self._package_name:
            qualified_name = f"{self._package_name}.{name}"
        else:
            qualified_name = name
        entity_context = self._declaration_context(context)
        entity = self._add(
            entity_context,
            entity_type,
            name,
            qualified_name,
            meta={
                **self._modifier_meta(context),
                "annotations": self._annotation_names(entity_context),
            },
        )
        with self._type_scope(entity, entity_context, body_context):
            return self.visit(body_context)

    def visitClassDeclaration(self, context):
        return self._type(context, "class", context.classBody())

    def visitInterfaceDeclaration(self, context):
        return self._type(context, "interface", context.interfaceBody())

    def visitEnumDeclaration(self, context):
        name = context.identifier().getText()
        if self.parent.type in _TYPE_RULES.values():
            qualified_name = f"{self.parent.qualified_name}.{name}"
        elif self._package_name:
            qualified_name = f"{self._package_name}.{name}"
        else:
            qualified_name = name
        entity_context = self._declaration_context(context)
        entity = self._add(
            entity_context,
            "enum",
            name,
            qualified_name,
            meta={
                **self._modifier_meta(context),
                "annotations": self._annotation_names(entity_context),
            },
        )
        with self._type_scope(entity, entity_context, context):
            return self.visitChildren(context)

    def visitRecordDeclaration(self, context):
        return self._type(context, "record", context.recordBody())

    def visitAnnotationTypeDeclaration(self, context):
        return self._type(context, "annotation_type", context.annotationTypeBody())

    def _parameter_types(self, context: ParserRuleContext) -> list[str]:
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
        return result

    def _method_entity(
        self,
        context: ParserRuleContext,
        name: str,
        return_type: str | None,
        parameters_context: ParserRuleContext | None,
        *,
        constructor: bool = False,
    ) -> None:
        parameter_types = self._parameter_types(parameters_context) if parameters_context else []
        signature = f"{name}({','.join(parameter_types)})"
        qname_name = "<init>" if constructor else name
        qualified_name = f"{self.parent.qualified_name}#{qname_name}({','.join(parameter_types)})"
        self._add(
            self._declaration_context(context),
            "constructor" if constructor else "method",
            name,
            qualified_name,
            meta={
                "signature": signature,
                "parameter_types": parameter_types,
                **self._modifier_meta(context),
                "annotations": self._annotation_names(context),
                **({} if constructor else {"return_type": return_type}),
            },
        )

    def visitMethodDeclaration(self, context):
        self._method_entity(
            context,
            context.identifier().getText(),
            context.typeTypeOrVoid().getText(),
            context.formalParameters(),
        )
        return None

    def visitInterfaceCommonBodyDeclaration(self, context):
        self._method_entity(
            context,
            context.identifier().getText(),
            context.typeTypeOrVoid().getText(),
            context.formalParameters(),
        )
        return None

    def visitAnnotationMethodRest(self, context):
        name = context.identifier().getText()
        rest = context.parentCtx.parentCtx
        return_type = rest.typeType().getText()
        self._method_entity(context, name, return_type, None)
        return None

    def visitConstructorDeclaration(self, context):
        self._method_entity(
            context,
            context.identifier().getText(),
            None,
            context.formalParameters(),
            constructor=True,
        )
        return None

    def visitCompactConstructorDeclaration(self, context):
        record = context.parentCtx.parentCtx
        parameters = record.recordHeader().recordComponentList()
        parameter_types = []
        if parameters is not None:
            for component in parameters.recordComponent():
                value = component.typeType().getText()
                if component.ELLIPSIS() is not None:
                    value += "[]"
                parameter_types.append(value)
        signature = f"<init>({','.join(parameter_types)})"
        qualified_name = f"{self.parent.qualified_name}#{signature}"
        self._add(
            context,
            "constructor",
            context.identifier().getText(),
            qualified_name,
            meta={
                "signature": signature,
                "parameter_types": parameter_types,
                "compact": True,
                **self._modifier_meta(context),
            },
        )
        return None

    def _field(
        self,
        context,
        name: str,
        field_type: str,
        *,
        annotations: list[str] | None = None,
        **extra_meta,
    ) -> Entity:
        field_context = (
            context
            if JavaParser.ruleNames[context.getRuleIndex()] == "enumConstant"
            else self._declaration_context(context)
        )
        return self._add(
            field_context,
            "field",
            name,
            f"{self.parent.qualified_name}#{name}",
            meta={
                "field_type": field_type,
                **self._modifier_meta(context),
                "annotations": annotations or self._annotation_names(field_context),
                **extra_meta,
            },
        )

    def _synthesize_lombok_accessors(
        self,
        field: Entity,
        field_type: str,
        field_context: ParserRuleContext,
        annotation_details: list[tuple[str, str]],
    ) -> None:
        if not self._lombok_policies:
            return

        class_annotations = self._lombok_policies[-1]
        field_annotations = {name.rsplit(".", 1)[-1] for name, _ in annotation_details}
        has_class_data = "Data" in class_annotations
        class_level = class_annotations & {"Getter", "Setter", "Data"}
        explicit_getter = "Getter" in field_annotations
        explicit_setter = "Setter" in field_annotations
        getter = explicit_getter or "Getter" in class_level or has_class_data
        setter = explicit_setter or "Setter" in class_level or has_class_data

        for name, text in annotation_details:
            simple_name = name.rsplit(".", 1)[-1]
            if simple_name == "Getter" and "NONE" in text:
                getter = False
            if simple_name == "Setter" and "NONE" in text:
                setter = False

        modifiers = field.meta.get("modifiers", [])
        is_static = "static" in modifiers
        is_final = "final" in modifiers
        if is_static:
            if not explicit_getter:
                getter = False
            if not explicit_setter:
                setter = False
        if is_final:
            setter = False

        is_boolean_is_name = field_type == "boolean" and (
            field.name.startswith("is") and len(field.name) > 2 and field.name[2].isupper()
        )
        property_name = field.name[2:] if is_boolean_is_name else field.name
        capitalized = property_name[:1].upper() + property_name[1:]
        if field_type == "boolean" and not is_boolean_is_name:
            getter_name = f"is{capitalized}"
        elif is_boolean_is_name:
            getter_name = field.name
        else:
            getter_name = f"get{capitalized}"
        setter_name = f"set{capitalized}"

        def add_accessor(name: str, parameter_types: list[str], return_type: str) -> None:
            key = (name, tuple(parameter_types))
            if key in self._explicit_method_keys[-1]:
                return
            self._explicit_method_keys[-1].add(key)
            signature = f"{name}({','.join(parameter_types)})"
            qualified_name = f"{self.parent.qualified_name}#{signature}"
            access_modifiers = ["public"] + (["static"] if is_static else [])
            self._add(
                field_context,
                "method",
                name,
                qualified_name,
                meta={
                    "signature": signature,
                    "parameter_types": parameter_types,
                    "return_type": return_type,
                    "modifiers": access_modifiers,
                    "visibility": "public",
                    "annotations": [],
                    "synthetic": True,
                    "generated_by": "lombok",
                    "source_field": field.qualified_name,
                },
            )

        if getter:
            add_accessor(getter_name, [], field_type)
        if setter:
            add_accessor(setter_name, [field_type], "void")

    def visitFieldDeclaration(self, context):
        field_type = context.typeType().getText()
        field_context = self._declaration_context(context)
        annotations = self._annotation_details(field_context)
        annotation_names = [name for name, _ in annotations]
        for declarator in context.variableDeclarators().variableDeclarator():
            field = self._field(
                declarator,
                declarator.variableDeclaratorId().identifier().getText(),
                field_type,
                annotations=annotation_names,
            )
            self._synthesize_lombok_accessors(field, field_type, field_context, annotations)
        return None

    def visitConstDeclaration(self, context):
        field_type = context.typeType().getText()
        field_context = self._declaration_context(context)
        annotations = self._annotation_details(field_context)
        for declarator in context.constantDeclarator():
            field = self._field(
                declarator,
                declarator.identifier().getText(),
                field_type,
                annotations=[name for name, _ in annotations],
            )
            self._synthesize_lombok_accessors(field, field_type, field_context, annotations)
        return None

    def visitAnnotationConstantRest(self, context):
        rest = context.parentCtx.parentCtx
        field_type = rest.typeType().getText()
        for declarator in context.variableDeclarators().variableDeclarator():
            self._field(
                declarator,
                declarator.variableDeclaratorId().identifier().getText(),
                field_type,
            )
        return None

    def visitEnumConstant(self, context):
        self._field(context, context.identifier().getText(), self.parent.name, enum_constant=True)
        return None

    def visitClassBodyDeclaration(self, context):
        block = context.block()
        if block is not None:
            start_line, _ = self._span(context)
            name = "<clinit>" if context.STATIC() is not None else "<init-block>"
            column = context.start.column if context.start is not None else 0
            self._add(
                context,
                "initializer",
                name,
                f"{self.parent.qualified_name}#{name}@{start_line}:{column}",
                meta={"static": context.STATIC() is not None},
            )
            return None
        return self.visitChildren(context)
