"""Standard-library artifact parsing shared by the CI runner and API."""

import hashlib
import xml.etree.ElementTree as ET


def xml_root(value):
    if "<!DOCTYPE" in value.upper() or "<!ENTITY" in value.upper():
        raise ValueError("XML declarations with DTD/entities are unsupported")
    try:
        return ET.fromstring(value)
    except ET.ParseError as exc:
        raise ValueError("Malformed build artifact XML") from exc


def children(node, name):
    return [child for child in node if child.tag.rsplit("}", 1)[-1] == name]


def child(node, name):
    return next(iter(children(node, name)), ET.Element(name))


def pom_projects(value):
    root = xml_root(value)
    projects = [root] if root.tag.rsplit("}", 1)[-1] == "project" else list(root)
    if not projects or any(p.tag.rsplit("}", 1)[-1] != "project" for p in projects):
        raise ValueError("Expected Maven effective POM project elements")
    return projects


def sanitize_pom(value):
    """Discard properties and plugin configuration before crossing the CI boundary."""
    projects = pom_projects(value)
    result = ET.Element("projects")
    for project in projects:
        target = ET.SubElement(result, "project")
        for name in ("groupId", "artifactId", "version", "packaging"):
            text = child(project, name).text
            if text:
                ET.SubElement(target, name).text = text
        deps = ET.SubElement(target, "dependencies")
        for dep in children(child(project, "dependencies"), "dependency"):
            copy = ET.SubElement(deps, "dependency")
            for name in (
                "groupId",
                "artifactId",
                "version",
                "scope",
                "type",
                "classifier",
                "optional",
            ):
                text = child(dep, name).text
                if text:
                    ET.SubElement(copy, name).text = text
    return ET.tostring(result, encoding="unicode")


def parse_test_report(value, path):
    root = xml_root(value)
    if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
        raise ValueError("Expected JUnit testsuite or testsuites")
    counts = {"tests": 0, "failure": 0, "error": 0, "skipped": 0}
    failures = []
    cases = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
    for case in cases:
        counts["tests"] += 1
        kinds = {node.tag.rsplit("}", 1)[-1] for node in case}
        status = next((kind for kind in ("error", "failure", "skipped") if kind in kinds), None)
        if status:
            counts[status] += 1
        if status in {"failure", "error"} and len(failures) < 30:
            failures.append(
                {
                    "name": case.get("name", "")[:300],
                    "class": case.get("classname", "")[:300],
                    "status": status,
                }
            )
    if not cases:
        leaves = [
            node
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "testsuite" and not children(node, "testsuite")
        ]
        for suite in leaves:
            for key, attr in (
                ("tests", "tests"),
                ("failure", "failures"),
                ("error", "errors"),
                ("skipped", "skipped"),
            ):
                counts[key] += int(suite.get(attr, "0"))
    if (
        any(n < 0 for n in counts.values())
        or sum(counts[k] for k in ("failure", "error", "skipped")) > counts["tests"]
    ):
        raise ValueError("Inconsistent JUnit counts")
    return {
        "path": path,
        "sha256": hashlib.sha256(value.encode()).hexdigest(),
        **counts,
        "failures": failures,
        "failures_truncated": counts["failure"] + counts["error"] > len(failures),
    }
