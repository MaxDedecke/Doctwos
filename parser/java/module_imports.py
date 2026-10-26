"""Repository-backed Java 25 module imports, without inventing external exports."""

from core.model import ParsedEdge


def resolve_module_imports(results):
    modules = {}
    for result in results:
        for entity in result.entities:
            if entity.type == "module":
                modules.setdefault(entity.name, []).append(entity)
    for result in results:
        for edge in list(result.edges):
            if edge.type != "IMPORTS_MODULE":
                continue
            queue, seen, packages = [edge.dst_name], set(), set()
            while queue:
                name = queue.pop()
                if name in seen:
                    continue
                seen.add(name)
                matches = modules.get(name, [])
                if len(matches) != 1:
                    continue
                module = matches[0]
                packages.update(module.meta.get("exports", []))
                queue.extend(module.meta.get("requires_transitive", []))
            root = next((e for e in result.entities if e.meta.get("is_file_root")), None)
            if root is not None:
                root.meta.setdefault("module_import_packages", {})[edge.dst_name] = sorted(packages)


def imports_for(result):
    edges = [edge for edge in result.edges if edge.type == "IMPORTS"]
    root = next((e for e in result.entities if e.meta.get("is_file_root")), None)
    if root is not None:
        for name, packages in root.meta.get("module_import_packages", {}).items():
            for package in packages:
                edges.append(
                    ParsedEdge(
                        "IMPORTS",
                        root.qualified_name,
                        package + ".*",
                        "unresolved",
                        root.start_line,
                        root.start_line,
                        meta={"static": False, "wildcard": True, "module_import": name},
                    )
                )
    return edges
