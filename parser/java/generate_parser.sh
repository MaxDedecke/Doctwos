#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
GRAMMAR_DIR="$SCRIPT_DIR/grammar"
OUTPUT_DIR="$SCRIPT_DIR/_antlr"
ANTLR_JAR="${ANTLR_JAR:-}"

if [[ -z "$ANTLR_JAR" || ! -f "$ANTLR_JAR" ]]; then
  echo "Set ANTLR_JAR to the local antlr-4.13.2-complete.jar" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
cd "$GRAMMAR_DIR"
java -jar "$ANTLR_JAR" -Dlanguage=Python3 -visitor -no-listener \
  -o "$OUTPUT_DIR" JavaLexer.g4
java -jar "$ANTLR_JAR" -Dlanguage=Python3 -visitor -no-listener \
  -lib "$OUTPUT_DIR" -o "$OUTPUT_DIR" JavaParser.g4
rm -f "$OUTPUT_DIR/JavaLexer.interp" "$OUTPUT_DIR/JavaLexer.tokens" \
  "$OUTPUT_DIR/JavaParser.interp" "$OUTPUT_DIR/JavaParser.tokens"
for generated in "$OUTPUT_DIR"/*.py; do
  sed -i -e 's/[[:space:]]\+$//' "$generated"
  perl -0pi -e 's/\n+\z/\n/' "$generated"
done
