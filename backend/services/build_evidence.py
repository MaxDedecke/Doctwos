"""Read caller-supplied Maven/CI artifacts bound to an indexed commit."""

import json
from pydantic import BaseModel, Field, field_validator
from doctus_models.database import KnowledgeSource
from doctus_models.ci_artifacts import xml_root as _xml


class BuildEvidence(BaseModel):
    source_id: int = Field(ge=1)
    commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    effective_pom: str = Field(max_length=1_000_000)
    dependency_tree: dict = Field(default_factory=dict)
    active_profiles: list[str] = Field(default_factory=list, max_length=100)
    junit_xml: str | None = Field(default=None, max_length=1_000_000)

    @field_validator("dependency_tree")
    @classmethod
    def bounded_tree(cls, value):
        if len(json.dumps(value)) > 1_000_000:
            raise ValueError("Dependency tree exceeds 1 MB")
        return value


def summarize_build_evidence(db, project_id, body):
    source = db.query(KnowledgeSource).filter_by(id=body.source_id, project_id=project_id).first()
    if (
        not source
        or source.sync_status != "completed"
        or (source.sync_cursor or {}).get("last_commit") != body.commit
    ):
        raise ValueError("Build artifacts must match a completed indexed source commit")
    return summarize_artifacts(body)


def summarize_artifacts(body):
    pom = _xml(body.effective_pom)
    projects = [pom] if pom.tag.rsplit("}", 1)[-1] == "project" else list(pom)
    modules = []
    for project in projects[:100]:
        values = {n.tag.rsplit("}", 1)[-1]: (n.text or "").strip() for n in project}
        if project.tag.rsplit("}", 1)[-1] != "project" or not values.get("artifactId"):
            raise ValueError("Expected Maven effective POM project elements")
        modules.append({key: values.get(key) for key in ("groupId", "artifactId", "version")})
    if not modules:
        raise ValueError("Effective POM contains no projects")
    dependencies, pending = [], [body.dependency_tree] if body.dependency_tree else []
    while pending and len(dependencies) < 500:
        node = pending.pop(0)
        if not isinstance(node, dict) or not node.get("artifactId"):
            raise ValueError("Expected Maven dependency:tree JSON objects")
        dependencies.append(
            {
                key: node.get(key)
                for key in ("groupId", "artifactId", "version", "scope", "type", "classifier")
            }
        )
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("Dependency children must be a list")
        pending.extend(children[:501])
    tests = None
    if body.junit_xml:
        report = _xml(body.junit_xml)
        cases = [n for n in report.iter() if n.tag.rsplit("}", 1)[-1] == "testcase"]
        if report.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
            raise ValueError("Expected JUnit testsuite or testsuites")
        tests = {
            "tests": len(cases),
            **{
                kind: sum(any(c.tag.rsplit("}", 1)[-1] == kind for c in case) for case in cases)
                for kind in ("failure", "error", "skipped")
            },
        }
    return {
        "source_id": body.source_id,
        "commit": body.commit,
        "provenance": "caller_supplied_build_artifacts",
        "modules": modules,
        "dependencies": dependencies,
        "active_profiles": body.active_profiles,
        "test_results": tests,
        "truncated": bool(pending) or len(projects) > 100,
    }
