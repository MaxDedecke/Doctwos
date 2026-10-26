"""Java 25 visitor additions kept separate from the declaration/body visitors."""

from pathlib import PurePosixPath

from core.model import ParsedEdge
from .declarations import JavaDeclarationVisitor
from .relationships import JavaRelationshipVisitor


class ModernDeclarationVisitor(JavaDeclarationVisitor):
    def visitModuleDeclaration(self, context):
        super().visitModuleDeclaration(context)
        module = self.entities[-1]
        module.meta["exports"] = [
            d.qualifiedName(0).getText()
            for d in context.moduleDirective()
            if d.EXPORTS() is not None and d.TO() is None
        ]
        module.meta["requires_transitive"] = [
            d.qualifiedName(0).getText()
            for d in context.moduleDirective()
            if d.REQUIRES() is not None
            and any(m.getText() == "transitive" for m in d.requiresModifier())
        ]
        return None

    def visitCompilationUnit(self, context):
        compact = context.compactCompilationUnit()
        if compact is None:
            return super().visitCompilationUnit(context)
        if not any(
            (
                compact.methodDeclaration(),
                compact.genericMethodDeclaration(),
                compact.fieldDeclaration(),
            )
        ):
            return None
        name = PurePosixPath(self.entities[0].name).stem
        entity = self._add(
            compact,
            "class",
            name,
            name,
            meta={"implicit_class": True, "annotations": [], "annotation_details": []},
        )
        with self._type_scope(entity, compact, compact):
            return self.visitChildren(compact)


class ModernRelationshipVisitor(JavaRelationshipVisitor):
    def visitCompactCompilationUnit(self, context):
        entity = next((e for e in self._entities if e.meta.get("implicit_class")), None)
        if entity is None:
            return None
        self._types.append(entity)
        self._scopes.append(entity)
        try:
            return self.visitChildren(context)
        finally:
            self._scopes.pop()
            self._types.pop()

    def visitModuleImportDeclaration(self, context):
        name = context.qualifiedName().getText()
        self.edges.append(
            ParsedEdge(
                type="IMPORTS_MODULE",
                src_name=self._scopes[0].qualified_name,
                dst_name=name,
                resolution="unresolved",
                src_start_line=context.start.line,
                src_end_line=context.stop.line,
                meta={
                    "language": "java",
                    "source_qualified_name": self._scopes[0].qualified_name,
                    "target_module": name,
                    "resolution_reason": "module_exports_required",
                },
            )
        )
