"""Bounded, offline Maven models. No plugin execution or repository downloads."""

from __future__ import annotations

import os
import posixpath
import re
import xml.etree.ElementTree as ET
from copy import deepcopy


def children(node, name):
    return [c for c in node if c.tag.rsplit("}", 1)[-1] == name] if node is not None else []


def child(node, name):
    return next(iter(children(node, name)), None)


def value(node, name, default=""):
    found = child(node, name)
    return (found.text or "").strip() if found is not None else default


def dependencies(node):
    return [
        {
            key: value(dep, key)
            for key in (
                "groupId",
                "artifactId",
                "version",
                "scope",
                "type",
                "classifier",
                "optional",
            )
        }
        | {
            "exclusions": [
                value(e, "groupId") + ":" + value(e, "artifactId")
                for e in children(child(dep, "exclusions"), "exclusion")
            ]
        }
        for dep in children(child(node, "dependencies"), "dependency")
    ]


def fragment(node):
    props = child(node, "properties")
    build = child(node, "build")
    return {
        "properties": {p.tag.rsplit("}", 1)[-1]: (p.text or "").strip() for p in props}
        if props is not None
        else {},
        "dependencies": dependencies(node),
        "management": dependencies(child(node, "dependencyManagement")),
        "modules": [(m.text or "").strip() for m in children(child(node, "modules"), "module")],
        "sourceDirectory": value(build, "sourceDirectory", "src/main/java"),
        "testSourceDirectory": value(build, "testSourceDirectory", "src/test/java"),
    }


def read_model(source):
    project = ET.fromstring(source)
    parent = child(project, "parent")
    model = fragment(project)
    model.update({k: value(project, k) for k in ("groupId", "artifactId", "version")})
    model["parent"] = {k: value(parent, k) for k in ("groupId", "artifactId", "version")}
    model["parent"]["relativePath"] = value(parent, "relativePath", "../pom.xml")
    model["profiles"] = []
    for profile in children(child(project, "profiles"), "profile"):
        activation = child(profile, "activation")
        model["profiles"].append(
            fragment(profile)
            | {
                "id": value(profile, "id"),
                "default": value(activation, "activeByDefault") == "true",
                "activation": ET.tostring(activation, encoding="unicode")
                if activation is not None
                else None,
            }
        )
    return model


def interpolate(text, properties):
    previous = set()
    for _ in range(32):
        if text in previous:
            break
        previous.add(text)
        updated = re.sub(r"\$\{([^}]+)\}", lambda m: str(properties.get(m[1], m[0])), text)
        if updated == text:
            break
        text = updated
    return text


def effective_models(models, *, active_profiles=(), properties=None):
    """Resolve checked-in parents/BOMs; retain unavailable or cyclic inputs as issues."""
    cache = {}
    supplied = dict(properties or {})
    active = set(active_profiles)

    def effective(path, stack=()):
        if path in cache:
            return cache[path]
        if path in stack:
            return {
                "issues": ["cyclic Maven parent/BOM: " + path],
                "properties": {},
                "dependencies": [],
                "management": {},
                "groupId": "",
                "version": "",
            }
        raw = deepcopy(models[path])
        issues = []
        parent = {}
        declaration = raw.get("parent", {})
        parent_path = posixpath.normpath(
            posixpath.join(posixpath.dirname(path), declaration.get("relativePath", "../pom.xml"))
        )
        if declaration.get("artifactId"):
            if declaration.get("relativePath") and parent_path in models:
                parent = effective(parent_path, (*stack, path))
                if parent.get("artifactId") != declaration["artifactId"]:
                    issues.append("parent coordinates do not match relativePath")
                    parent = {}
            else:
                matches = [
                    p
                    for p, m in models.items()
                    if m.get("artifactId") == declaration["artifactId"]
                    and m.get("groupId") == declaration.get("groupId")
                ]
                if len(matches) == 1:
                    parent = effective(matches[0], (*stack, path))
                else:
                    issues.append("parent unavailable or ambiguous: " + declaration["artifactId"])
        profiles = raw.pop("profiles", [])
        selected = [p for p in profiles if p["id"] in active]
        if not selected:
            selected = [p for p in profiles if p["default"] and not active]
        for profile in selected:
            raw["properties"].update(profile["properties"])
            raw["dependencies"].extend(profile["dependencies"])
            raw["management"].extend(profile["management"])
            raw["modules"].extend(profile["modules"])
        props = {**parent.get("properties", {}), **raw["properties"], **supplied}
        group = raw.get("groupId") or parent.get("groupId") or declaration.get("groupId", "")
        version = raw.get("version") or parent.get("version") or declaration.get("version", "")
        props.update(
            {
                "project.groupId": group,
                "pom.groupId": group,
                "project.artifactId": raw["artifactId"],
                "project.version": version,
                "pom.version": version,
                "project.parent.version": parent.get("version", declaration.get("version", "")),
            }
        )
        props = {k: interpolate(v, props) for k, v in props.items()}
        raw.update(
            {
                "groupId": interpolate(group, props),
                "version": interpolate(version, props),
                "properties": props,
                "issues": [*parent.get("issues", []), *issues],
                "active_profiles": [p["id"] for p in selected],
            }
        )
        management = dict(parent.get("management", {}))
        for dep in raw["management"]:
            dep = {k: interpolate(v, props) if isinstance(v, str) else v for k, v in dep.items()}
            key = dep["groupId"] + ":" + dep["artifactId"]
            if dep["type"] == "pom" and dep["scope"] == "import":
                matches = [
                    p
                    for p, m in models.items()
                    if m.get("artifactId") == dep["artifactId"]
                    and m.get("groupId") == dep["groupId"]
                ]
                if len(matches) == 1:
                    management.update(effective(matches[0], (*stack, path)).get("management", {}))
                else:
                    raw["issues"].append("BOM unavailable or ambiguous: " + key)
            else:
                management[key] = dep
        merged = {
            d["groupId"] + ":" + d["artifactId"]: dict(d) for d in parent.get("dependencies", [])
        }
        for dep in raw["dependencies"]:
            dep = {k: interpolate(v, props) if isinstance(v, str) else v for k, v in dep.items()}
            key = dep["groupId"] + ":" + dep["artifactId"]
            managed = management.get(key, {})
            merged[key] = {k: v or managed.get(k, "") for k, v in dep.items()}
        raw["dependencies"] = list(merged.values())
        raw["management"] = management
        raw["modules"] = [interpolate(m, props) for m in raw["modules"]]
        for key in ("sourceDirectory", "testSourceDirectory"):
            raw[key] = interpolate(raw[key], props)
        cache[path] = raw
        return raw

    for path in sorted(models):
        effective(path)
    return cache


def configured_profiles():
    return tuple(filter(None, re.split(r"[,\s]+", os.getenv("DOCTUS_MAVEN_PROFILES", ""))))
