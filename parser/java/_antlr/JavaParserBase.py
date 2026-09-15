"""Doctus-owned Python support for semantic predicates in JavaParser.g4."""

from __future__ import annotations

from antlr4 import Parser


class JavaParserBase(Parser):
    """Implements the two predicates required by the pinned Java grammar."""

    def IsNotIdentifierAssign(self) -> bool:
        """Distinguish annotation values from ``name = value`` pairs."""

        if self._input.LA(2) != self.ASSIGN:
            return True

        identifier_tokens = (
            "IDENTIFIER",
            "MODULE",
            "OPEN",
            "REQUIRES",
            "EXPORTS",
            "OPENS",
            "TO",
            "USES",
            "PROVIDES",
            "WHEN",
            "WITH",
            "TRANSITIVE",
            "YIELD",
            "SEALED",
            "PERMITS",
            "RECORD",
            "VAR",
        )
        return self._input.LA(1) not in {
            getattr(self, token_name)
            for token_name in identifier_tokens
            if hasattr(self, token_name)
        }

    def DoLastRecordComponent(self) -> bool:
        """Require a variable-arity record component to be the final one."""

        components = self._ctx.recordComponent()
        return not any(component.ELLIPSIS() is not None for component in components[:-1])
