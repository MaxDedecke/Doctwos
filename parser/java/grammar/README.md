# Java grammar provenance and regeneration

Doctus pins the optimized Java grammar from `antlr/grammars-v4/java/java` at
upstream commit `20efa537586610f5aebd584429ac1b5993a30381`:

- [JavaLexer.g4](https://github.com/antlr/grammars-v4/blob/20efa537586610f5aebd584429ac1b5993a30381/java/java/JavaLexer.g4)
- [JavaParser.g4](https://github.com/antlr/grammars-v4/blob/20efa537586610f5aebd584429ac1b5993a30381/java/java/JavaParser.g4)
- [Upstream README](https://github.com/antlr/grammars-v4/blob/20efa537586610f5aebd584429ac1b5993a30381/java/java/README.md)

Both grammar files carry the BSD 3-Clause license and their copyright notices
in their headers. Keep those headers with the source files and include the
license in Doctus distribution notices. The upstream README identifies Java 24
as its current tested language level, so it is a suitable superset candidate
for the Java 21 MVP. Doctus still validates every in-scope Java 21 feature in
its own golden corpus; preview-only syntax is outside the MVP unless added by
an explicit fixture and decision.

The grammar directory currently has Java and C# target support only. Its Java
parser relies on a target-specific superclass and two semantic predicates.
Doctus implements equivalent Python behavior in
`../_antlr/JavaParserBase.py` and does not copy the upstream Java helper class.
The generator and runtime are both pinned to ANTLR 4.13.2, matching
`parser/requirements.txt`; the generator is a development-time tool and is not
installed in the runtime image. The upstream license is included at
`../LICENSE-upstream-grammars-v4-java`.

`parser/java/generate_parser.sh` is the supported offline regeneration entry
point. Provide a local ANTLR 4.13.2 complete JAR through `ANTLR_JAR`; the script
generates the Python 3 lexer, parser and visitor under `parser/java/_antlr/`.
Grammar changes must update the upstream pin and pass the Java golden corpus
before generated files are accepted. The bridge and declaration visitor have
Java 8/21 syntax tests; symbol-oriented chunks, explicit Git opt-in, standard
build-output excludes and module-path metadata are implemented. Regenerate the
parser snapshots from `parser/` with:

```bash
PYTHONPATH=. python tests/update_java_goldens.py
python -m pytest tests/test_java_antlr_bridge.py tests/test_java_golden.py -q
```
