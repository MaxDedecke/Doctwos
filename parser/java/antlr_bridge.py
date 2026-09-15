"""Error-tolerant ANTLR bridge for Java source files."""

from __future__ import annotations

from dataclasses import dataclass
import re

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from ._antlr.JavaLexer import JavaLexer
from ._antlr.JavaParser import JavaParser


@dataclass(frozen=True)
class JavaSyntaxDiagnostic:
    line: int
    column: int
    message: str
    phase: str


@dataclass(frozen=True)
class JavaParseResult:
    tree: object
    diagnostics: tuple[JavaSyntaxDiagnostic, ...]
    diagnostics_truncated: bool
    original_line_map: tuple[int, ...]

    def original_line(self, parser_line: int) -> int | None:
        """Map a parser line to its original source line, if it exists."""

        if parser_line < 1 or parser_line > len(self.original_line_map):
            return None
        return self.original_line_map[parser_line - 1]


class _BoundedErrorListener(ErrorListener):
    def __init__(self, maximum: int) -> None:
        super().__init__()
        self.maximum = maximum
        self.diagnostics: list[JavaSyntaxDiagnostic] = []
        self.truncated = False

    def syntaxError(self, recognizer, offending_symbol, line, column, message, exception):
        if len(self.diagnostics) >= self.maximum:
            self.truncated = True
            return
        phase = "lexer" if isinstance(recognizer, JavaLexer) else "parser"
        self.diagnostics.append(JavaSyntaxDiagnostic(line, column, message, phase))


def parse_java_source(source: str, *, max_diagnostics: int = 50) -> JavaParseResult:
    """Parse Java text while retaining recovered trees and bounded diagnostics.

    Line endings are normalized because the generated lexer advances its line
    counter on LF. The normalization preserves a one-to-one source line map.
    """

    if max_diagnostics < 1:
        raise ValueError("max_diagnostics must be at least 1")

    normalized_source = source.replace("\r\n", "\n").replace("\r", "\n")
    source_lines = re.split(r"\r\n|\r|\n", source)
    line_map = tuple(range(1, len(source_lines) + 1))

    listener = _BoundedErrorListener(max_diagnostics)
    lexer = JavaLexer(InputStream(normalized_source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)

    parser = JavaParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.compilationUnit()

    return JavaParseResult(
        tree=tree,
        diagnostics=tuple(listener.diagnostics),
        diagnostics_truncated=listener.truncated,
        original_line_map=line_map,
    )
