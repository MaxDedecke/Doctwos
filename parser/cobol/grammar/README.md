# COBOL grammar sources

These are the sources for the production parser in `../_antlr/`.
They were moved unchanged from the historical ANTLR spike as part of O-065. Since
06.11.2026 Doctus extends `Cobol85.g4` for further COBOL dialects; every change is marked with a
`// Doctus:` comment (e.g. `EXIT PERFORM [CYCLE]`, `EXIT PARAGRAPH`, `EXIT SECTION`).

- Upstream: `antlr/grammars-v4`, directory `cobol85/`
- Pinned revision: `e1c222f3f0e7c1b2fec799e94e34fc388b03f887`
- Generator and Python runtime: ANTLR 4.13.2
- License: MIT; see `LICENSE-upstream-cobol85parser` and the grammar headers.
- Architecture and provenance: `docs/ENTSCHEIDUNGEN.md` E-11 and
  `docs/OSS-CLEARING.md`, relative to the repository root.

## Regeneration

Java is needed only on the development machine, never in the runtime image. Without a local
Java, the official `eclipse-temurin:17-jre` image works (mount this directory, run the same commands).
The generator reproduces the committed files byte for byte from an unchanged grammar.
With the ANTLR 4.13.2 generator available locally, run from this directory:

```bash
java -jar /path/to/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -o ../_antlr Cobol85Preprocessor.g4
java -jar /path/to/antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -o ../_antlr Cobol85.g4
```

Review the generated changes and run the COBOL unit and golden-file tests
from `parser/` using its development environment:

```bash
python -m pytest tests/ -k cobol -v
```

The removed experiment and its findings are preserved at commit
`2d0a96706158f69a030c5b83c619c70cd108466b`, path
`parser/spikes/antlr_cobol/README.md` (for example via `git show`).
