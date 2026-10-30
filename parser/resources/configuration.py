"""Safe YAML/JSON/INI configuration structure with physical source locations."""

import configparser
import re
from itertools import islice
from pathlib import PurePosixPath

import yaml

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseDiagnostic, ParseResult


# Aliase verweisen auf denselben Knoten: Ein Kilobyte YAML kann so Milliarden Pfade ergeben
# ("Billion Laughs"), auch ganz ohne Werte. `seen` fängt nur Zyklen ab.
_YAML_MAX_NODE_VISITS = 100_000
_MAX_PROPERTIES = 10000


def _yaml_entries(node, prefix="", seen=None, budget=None):
    seen = set() if seen is None else seen
    budget = [_YAML_MAX_NODE_VISITS] if budget is None else budget
    if node is None or id(node) in seen or budget[0] <= 0:
        return
    budget[0] -= 1
    seen = seen | {id(node)}
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode):
                name = prefix + "." + key.value if prefix else key.value
                yield from _yaml_entries(value, name, seen, budget)
    elif isinstance(node, yaml.SequenceNode):
        for index, value in enumerate(node.value):
            yield from _yaml_entries(value, f"{prefix}[{index}]", seen, budget)
    else:
        yield prefix, node.value, node.start_mark.line + 1, node.end_mark.line + 1


def parse_configuration(source, path, **kwargs):
    path = PurePosixPath(path).as_posix()
    root = Entity(
        "configuration_file",
        PurePosixPath(path).name,
        1,
        max(1, len(source.splitlines())),
        qualified_name=path,
        meta={"language": "configuration", "is_file_root": True},
    )
    result = ParseResult(
        root.name,
        path,
        "free",
        entities=[root],
        chunks=[
            Chunk(c["content"], c["start_line"], c["end_line"], {"language": "configuration"})
            for c in CodeParser("configuration").chunk_file(source)
        ],
    )
    try:
        if PurePosixPath(path).suffix.lower() in {".ini", ".cfg", ".conf"}:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read_string(source)
            entries = []
            for section in parser.sections():
                for key, value in parser.items(section):
                    line = next(
                        (
                            n
                            for n, text in enumerate(source.splitlines(), 1)
                            if re.match(r"\s*" + re.escape(key) + r"\s*[=:]", text, re.I)
                        ),
                        1,
                    )
                    entries.append((f"{section}.{key}", value, line, line))
            documents = [entries]
        else:
            documents = [
                _yaml_entries(node) for node in yaml.compose_all(source, Loader=yaml.SafeLoader)
            ]
        seen = {}
        for document_index, document in enumerate(documents):
            entries = list(islice(document, _MAX_PROPERTIES + 1))
            if len(entries) > _MAX_PROPERTIES:
                result.diagnostics.append(
                    ParseDiagnostic(
                        "CONFIGURATION_PROPERTY_LIMIT",
                        "warning",
                        "parser",
                        "Konfiguration enthält mehr als 10000 Schlüssel; weitere Schlüssel sind nur im Quelltext verfügbar.",
                        1,
                        0,
                    )
                )
            profiles = next(
                (
                    value
                    for key, value, *_ in entries
                    if key in {"spring.config.activate.on-profile", "spring.profiles"}
                ),
                "",
            )
            for key, value, start, end in entries[:_MAX_PROPERTIES]:
                occurrence = seen.get(key, 0) + 1
                seen[key] = occurrence
                meta = {
                    "language": "configuration",
                    "property_key": key,
                    "document_index": document_index,
                }
                if profiles:
                    meta["configuration_profile"] = profiles
                if re.search(r"password|secret|token|credential|private|api[._-]?key", key, re.I):
                    meta["value_redacted"] = True
                else:
                    meta["value_preview"] = value[:120]
                result.entities.append(
                    Entity(
                        "property",
                        key,
                        start,
                        end,
                        parent_name=root.name,
                        parent_qualified_name=path,
                        qualified_name=f"{path}::{key}#{occurrence}",
                        meta=meta,
                    )
                )
        root.meta["property_count"] = len(result.entities) - 1
    except (yaml.YAMLError, configparser.Error, RecursionError) as exc:
        result.diagnostics.append(
            ParseDiagnostic(
                "CONFIGURATION_PARSE_ERROR",
                "error",
                "parser",
                f"Konfiguration konnte nicht strukturiert werden: {type(exc).__name__}",
                1,
                0,
            )
        )
    return result
