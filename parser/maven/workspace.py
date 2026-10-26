"""Bind Java source sets to offline effective reactor dependencies."""

from collections import defaultdict
import posixpath

from .model import configured_profiles, effective_models


def apply_maven_scopes(results, projects, *, active_profiles=None):
    models = {p.file_path: (p.meta_json or {}).get("maven_model") for p in projects}
    models = {path: model for path, model in models.items() if model}
    effective = effective_models(
        models,
        active_profiles=configured_profiles() if active_profiles is None else active_profiles,
    )
    coordinates = defaultdict(list)
    for path, model in effective.items():
        coordinates[(model["groupId"], model["artifactId"])].append(path)

    def visible(path, is_test, runtime=False):
        found, issues = {path}, []
        queue = [(path, True, frozenset())]
        while queue:
            current, direct, exclusions = queue.pop(0)
            for dep in effective[current]["dependencies"]:
                scope = dep.get("scope") or "compile"
                key = dep["groupId"] + ":" + dep["artifactId"]
                if key in exclusions or (not direct and dep.get("optional") == "true"):
                    continue
                if scope == "test" and (not is_test or not direct):
                    continue
                if (scope == "runtime" and not is_test and not runtime) or (
                    scope == "provided" and not direct
                ):
                    continue
                if scope not in {"compile", "provided", "test", "runtime"} or dep.get("classifier"):
                    continue
                if dep.get("type") not in {None, "", "jar"}:
                    continue
                matches = coordinates.get((dep["groupId"], dep["artifactId"]), [])
                if len(matches) > 1:
                    issues.append("ambiguous reactor dependency: " + key)
                if len(matches) == 1:
                    target = matches[0]
                    version = dep.get("version")
                    if version and version != effective[target]["version"]:
                        issues.append("reactor version mismatch: " + key)
                        continue
                    if target not in found:
                        found.add(target)
                        queue.append(
                            (target, False, exclusions | frozenset(dep.get("exclusions", [])))
                        )
        return sorted(posixpath.dirname(p) or "." for p in found), issues

    for result in results:
        matches = []
        for path, model in effective.items():
            directory = posixpath.dirname(path)
            for key, source_set in (("sourceDirectory", "main"), ("testSourceDirectory", "test")):
                root = posixpath.normpath(posixpath.join(directory, model[key]))
                if result.path.startswith(root + "/"):
                    matches.append((len(root), path, source_set))
            for generated in ("target/generated-sources", "src/generated"):
                if result.path.startswith(posixpath.join(directory, generated) + "/"):
                    matches.append((len(directory), path, "main"))
        if not matches:
            continue
        _, path, source_set = max(matches)
        visibility, issues = visible(path, source_set != "main")
        runtime_visibility, _ = visible(path, source_set != "main", runtime=True)
        for entity in result.entities:
            entity.meta.update(module=posixpath.dirname(path) or ".", source_set=source_set)
            if entity.meta.get("is_file_root"):
                entity.meta.update(
                    maven_visibility=visibility,
                    maven_runtime_visibility=runtime_visibility,
                    maven_issues=effective[path]["issues"] + issues,
                    maven_active_profiles=effective[path]["active_profiles"],
                )
        # A changed POM can invalidate a previously resolved target even if both
        # Java files are unchanged. Re-evaluate declarations against this model.
        for edge in result.edges:
            if edge.type in {
                "CALLS",
                "IMPORTS",
                "USES_TYPE",
                "EXTENDS",
                "IMPLEMENTS",
                "INSTANTIATES",
                "REFERENCES_METHOD",
            }:
                if edge.resolution in {"resolved", "external"}:
                    edge.resolution = "unresolved"
                    for key in ("target_qualified_name", "target_file_path", "external"):
                        edge.meta.pop(key, None)
    return effective


def resolve_scoped_java(results, entities, resolver):
    groups = defaultdict(list)
    for result in results:
        groups[result.variant_key].append(result)
    resolved = 0
    for variant, group in groups.items():
        projects = [e for e in entities if e.type == "maven_project" and e.variant_key == variant]
        apply_maven_scopes(group, projects)
        resolved += resolver(group)
    return resolved
