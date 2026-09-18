"""Java parser entry point that returns the shared in-memory ParseResult."""

from __future__ import annotations

from pathlib import Path

from core.model import Entity, ParseDiagnostic, ParseResult

from .antlr_bridge import parse_java_source
from .chunking import chunk_java_source
from .declarations import JavaDeclarationVisitor
from .modules import module_from_path, source_set_from_path
from .relationships import JavaRelationshipVisitor
from .resolution import resolve_local_edges
from ._antlr.JavaParser import JavaParser


def parse_java_file(
    source: str,
    path: str,
    *,
    max_diagnostics: int = 50,
) -> ParseResult:
    """Parse Java declarations without accessing the filesystem or database."""

    parsed = parse_java_source(source, max_diagnostics=max_diagnostics)
    normalized_path = Path(path).as_posix()
    root_name = Path(path).name or normalized_path or "<memory>"
    module = module_from_path(normalized_path)
    source_set = source_set_from_path(normalized_path)
    root_meta = {"language": "java", "is_file_root": True}
    if module is not None:
        root_meta["module"] = module
    if source_set is not None:
        root_meta["source_set"] = source_set
    root = Entity(
        type="compilation_unit",
        name=root_name,
        start_line=1,
        end_line=max(1, len(parsed.original_line_map)),
        qualified_name=normalized_path or root_name,
        meta=root_meta,
    )
    visitor = JavaDeclarationVisitor(root)
    if isinstance(parsed.tree, JavaParser.CompilationUnitContext):
        visitor.visit(parsed.tree)
    relationships = JavaRelationshipVisitor(root, visitor.entities)
    if isinstance(parsed.tree, JavaParser.CompilationUnitContext):
        relationships.visit(parsed.tree)
    resolve_local_edges(relationships.edges, visitor.entities)

    diagnostics = [
        ParseDiagnostic(
            code="JAVA_LEXER_ERROR" if item.phase == "lexer" else "JAVA_PARSER_ERROR",
            severity="error",
            phase=item.phase,
            message=item.message,
            line=parsed.original_line(item.line) or item.line,
            column=item.column,
        )
        for item in parsed.diagnostics
    ]
    if parsed.diagnostics_truncated:
        diagnostics.append(
            ParseDiagnostic(
                code="JAVA_DIAGNOSTICS_TRUNCATED",
                severity="warning",
                phase="parser",
                message=f"Weitere Syntaxdiagnosen wurden nach {max_diagnostics} Einträgen abgeschnitten.",
                line=1,
                column=0,
            )
        )

    return ParseResult(
        program_name=Path(path).stem or root_name,
        path=path,
        source_format="free",
        entities=visitor.entities,
        edges=relationships.edges,
        chunks=chunk_java_source(source, visitor.entities),
        diagnostics=diagnostics,
    )
