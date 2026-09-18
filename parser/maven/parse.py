"""Parse Maven POMs without executing Maven or resolving dependencies."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseDiagnostic, ParseResult, ParsedEdge


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _child_text(element: ET.Element | None, name: str) -> str | None:
    if element is None:
        return None
    child = next((item for item in list(element) if _local_name(item.tag) == name), None)
    value = "".join(child.itertext()).strip() if child is not None else ""
    return value or None


def _line_for(source: str, needle: str, cursor: int) -> tuple[int, int]:
    index = source.find(needle, cursor)
    if index < 0:
        return 1, cursor
    line = source.count("\n", 0, index) + 1
    return line, index + len(needle)


def _add_entity(
    entities: list[Entity],
    *,
    entity_type: str,
    name: str,
    qualified_name: str,
    path: str,
    parent: Entity | None,
    line: int,
    meta: dict,
) -> Entity:
    entity = Entity(
        type=entity_type,
        name=name,
        start_line=line,
        end_line=line,
        parent_name=parent.name if parent else None,
        qualified_name=qualified_name,
        parent_qualified_name=parent.qualified_name if parent else None,
        meta={"language": "maven", "path": path, **meta},
    )
    entities.append(entity)
    return entity


def parse_maven_pom(source: str, path: str, **_: object) -> ParseResult:
    """Extract project, module, dependency and plugin metadata from a POM.

    The parser deliberately treats properties and unresolved expressions as
    source facts. It never interpolates values, invokes Maven, reads a local
    repository, or assumes that a dependency can be downloaded.
    """

    normalized_path = PurePosixPath(path.replace("\\", "/")).as_posix()
    chunks = [
        Chunk(
            content=chunk["content"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            meta={"language": "maven", **chunk.get("meta", {})},
        )
        for chunk in CodeParser("maven").chunk_file(source)
    ]
    try:
        project = ET.fromstring(source)
    except ET.ParseError as exc:
        return ParseResult(
            program_name=PurePosixPath(path).stem or "pom",
            path=path,
            source_format="free",
            chunks=chunks,
            diagnostics=[
                ParseDiagnostic(
                    code="MAVEN_POM_XML_ERROR",
                    severity="error",
                    phase="parser",
                    message=f"pom.xml ist kein gültiges XML: {exc}",
                    line=1,
                    column=0,
                )
            ],
        )

    cursor = 0
    project_name = _child_text(project, "artifactId") or PurePosixPath(path).parent.name or "pom"
    group_id = _child_text(project, "groupId")
    version = _child_text(project, "version")
    packaging = _child_text(project, "packaging") or "jar"
    parent = next((item for item in list(project) if _local_name(item.tag) == "parent"), None)
    parent_group = _child_text(parent, "groupId")
    parent_version = _child_text(parent, "version")
    effective_group = group_id or parent_group

    root_line, cursor = _line_for(source, "<project", cursor)
    root_qname = normalized_path
    root = _add_entity(
        [],
        entity_type="maven_project",
        name=project_name,
        qualified_name=root_qname,
        path=path,
        parent=None,
        line=root_line,
        meta={
            "build_system": "maven",
            "group_id": effective_group,
            "artifact_id": project_name,
            "version": version or parent_version,
            "packaging": packaging,
            "parent_group_id": parent_group,
        },
    )
    entities = [root]
    edges: list[ParsedEdge] = []

    properties = next((item for item in list(project) if _local_name(item.tag) == "properties"), None)
    if properties is not None:
        for prop in list(properties):
            name = _local_name(prop.tag)
            value = "".join(prop.itertext()).strip()
            line, cursor = _line_for(source, f"<{name}", cursor)
            qname = f"{root_qname}::property:{name}"
            _add_entity(
                entities,
                entity_type="maven_property",
                name=name,
                qualified_name=qname,
                path=path,
                parent=root,
                line=line,
                meta={"value": value},
            )

    modules = next((item for item in list(project) if _local_name(item.tag) == "modules"), None)
    if modules is not None:
        for module in _children(modules, "module"):
            module_path = (module.text or "").strip()
            if not module_path:
                continue
            line, cursor = _line_for(source, "<module", cursor)
            qname = f"{root_qname}::module:{module_path}"
            child = _add_entity(
                entities,
                entity_type="maven_module",
                name=module_path,
                qualified_name=qname,
                path=path,
                parent=root,
                line=line,
                meta={"module_path": module_path},
            )
            edges.append(
                ParsedEdge(
                    type="CONTAINS_MODULE",
                    src_name=root_qname,
                    dst_name=child.qualified_name or child.name,
                    resolution="resolved",
                    src_start_line=line,
                    src_end_line=line,
                    meta={"language": "maven", "target_qualified_name": child.qualified_name},
                )
            )

    dependencies = next((item for item in list(project) if _local_name(item.tag) == "dependencies"), None)
    if dependencies is not None:
        for dependency in _children(dependencies, "dependency"):
            dep_group = _child_text(dependency, "groupId") or ""
            dep_artifact = _child_text(dependency, "artifactId") or ""
            if not dep_artifact:
                continue
            coordinate = f"{dep_group}:{dep_artifact}" if dep_group else dep_artifact
            line, cursor = _line_for(source, "<dependency", cursor)
            qname = f"{root_qname}::dependency:{coordinate}"
            child = _add_entity(
                entities,
                entity_type="maven_dependency",
                name=coordinate,
                qualified_name=qname,
                path=path,
                parent=root,
                line=line,
                meta={
                    "group_id": dep_group or None,
                    "artifact_id": dep_artifact,
                    "version": _child_text(dependency, "version"),
                    "scope": _child_text(dependency, "scope") or "compile",
                    "optional": _child_text(dependency, "optional") == "true",
                },
            )
            edges.append(
                ParsedEdge(
                    type="DEPENDS_ON",
                    src_name=root_qname,
                    dst_name=child.qualified_name or child.name,
                    resolution="resolved",
                    src_start_line=line,
                    src_end_line=line,
                    meta={"language": "maven", "target_qualified_name": child.qualified_name},
                )
            )

    build = next((item for item in list(project) if _local_name(item.tag) == "build"), None)
    # Conventional roots are facts about the Maven model, not guesses about
    # files that happen to exist. Custom roots are retained literally (even
    # with ${...}) and never expanded or fetched.
    source_roots = [
        ("main", "source", "src/main/java"), ("test", "source", "src/test/java"),
        ("main", "resource", "src/main/resources"), ("test", "resource", "src/test/resources"),
    ]
    if build is not None:
        for element_name, source_set in (("sourceDirectory", "main"), ("testSourceDirectory", "test")):
            value = _child_text(build, element_name)
            if value:
                source_roots.append((source_set, "source", value))
        resources = next((item for item in list(build) if _local_name(item.tag) == "resources"), None)
        test_resources = next((item for item in list(build) if _local_name(item.tag) == "testResources"), None)
        for container, source_set in ((resources, "main"), (test_resources, "test")):
            if container is not None:
                for resource in _children(container, "resource"):
                    directory = _child_text(resource, "directory")
                    if directory:
                        source_roots.append((source_set, "resource", directory))
    for source_set, source_kind, directory in dict.fromkeys(source_roots):
        line, cursor = _line_for(source, directory, cursor)
        qname = f"{root_qname}::source-root:{source_set}:{source_kind}:{directory}"
        child = _add_entity(entities, entity_type="maven_source_root", name=directory,
            qualified_name=qname, path=path, parent=root, line=line,
            meta={"source_set": source_set, "source_kind": source_kind, "directory": directory,
                  "conventional": directory.startswith("src/")})
        edges.append(ParsedEdge(type="DECLARES_SOURCE_ROOT", src_name=root_qname,
            dst_name=child.qualified_name or child.name, resolution="resolved", src_start_line=line,
            src_end_line=line, meta={"language": "maven", "target_qualified_name": child.qualified_name}))
    plugins = next((item for item in list(build or []) if _local_name(item.tag) == "plugins"), None)
    if plugins is not None:
        for plugin in _children(plugins, "plugin"):
            plugin_group = _child_text(plugin, "groupId") or "org.apache.maven.plugins"
            plugin_artifact = _child_text(plugin, "artifactId") or ""
            if not plugin_artifact:
                continue
            coordinate = f"{plugin_group}:{plugin_artifact}"
            line, cursor = _line_for(source, "<plugin", cursor)
            qname = f"{root_qname}::plugin:{coordinate}"
            child = _add_entity(
                entities,
                entity_type="maven_plugin",
                name=coordinate,
                qualified_name=qname,
                path=path,
                parent=root,
                line=line,
                meta={"group_id": plugin_group, "artifact_id": plugin_artifact, "version": _child_text(plugin, "version")},
            )
            edges.append(
                ParsedEdge(
                    type="USES_PLUGIN",
                    src_name=root_qname,
                    dst_name=child.qualified_name or child.name,
                    resolution="resolved",
                    src_start_line=line,
                    src_end_line=line,
                    meta={"language": "maven", "target_qualified_name": child.qualified_name},
                )
            )

    return ParseResult(
        program_name=project_name,
        path=path,
        source_format="free",
        entities=entities,
        edges=edges,
        chunks=chunks,
    )
