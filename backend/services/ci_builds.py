"""Validate, persist and select immutable commit-specific CI results."""

import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.orm import aliased

from doctus_models.database import CIBuildRun, KnowledgeSource
from doctus_models.insight_versions import _digest
from services.build_evidence import BuildEvidence, summarize_artifacts


def repository_identity(source):
    return source.repo_fingerprint or _digest(source.url or str(source.id))


class CITestReport(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tests: int = Field(ge=0)
    failure: int = Field(ge=0)
    error: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failures: list[dict[str, str]] = Field(default_factory=list, max_length=30)
    failures_truncated: bool = False

    @model_validator(mode="after")
    def consistent_counts(self):
        if self.failure + self.error + self.skipped > self.tests:
            raise ValueError("Inconsistent JUnit counts")
        return self


class CIModule(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    effective_pom: str | None = Field(default=None, max_length=1_000_000)
    dependency_tree: dict = Field(default_factory=dict)
    test_reports: list[CITestReport] = Field(default_factory=list, max_length=1000)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    collection_errors: list[str] = Field(default_factory=list, max_length=30)


class CIBuildUpload(BaseModel):
    source_id: int = Field(ge=1)
    commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    branch: str = Field(min_length=1, max_length=256)
    provider: str = Field(pattern=r"^(github|gitlab|jenkins|generic)$")
    run_id: str = Field(min_length=1, max_length=200)
    attempt: int = Field(default=1, ge=1)
    job_name: str = Field(min_length=1, max_length=200)
    variant: str = Field(default="default", min_length=1, max_length=200)
    status: str = Field(pattern=r"^(success|failed|cancelled)$")
    pipeline_url: str | None = Field(default=None, max_length=2000)
    finished_at: datetime
    active_profiles: list[str] = Field(default_factory=list, max_length=100)
    java_version: str | None = Field(default=None, max_length=200)
    modules: list[CIModule] = Field(default_factory=list, max_length=200)
    collection_errors: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("pipeline_url")
    @classmethod
    def safe_url(cls, value):
        if value is None:
            return None
        parts = urlsplit(value)
        if (
            parts.scheme not in {"https", "http"}
            or not parts.netloc
            or parts.username
            or parts.password
        ):
            raise ValueError("Expected a credential-free HTTP build URL")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    @field_validator("finished_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Build time needs a timezone")
        return value

    @model_validator(mode="after")
    def unique_artifacts(self):
        paths = [module.path for module in self.modules]
        reports = [report.path for module in self.modules for report in module.test_reports]
        if len(paths) != len(set(paths)) or len(reports) != len(set(reports)):
            raise ValueError("Duplicate module or test report paths")
        return self


def summarize_upload(body):
    modules = []
    totals = {key: 0 for key in ("tests", "failure", "error", "skipped")}
    report_count = 0
    for module in body.modules:
        maven = None
        if module.effective_pom or module.dependency_tree:
            artifact = BuildEvidence(
                source_id=body.source_id,
                commit=body.commit,
                effective_pom=module.effective_pom
                or "<project><artifactId>unavailable</artifactId></project>",
                dependency_tree=module.dependency_tree,
            )
            maven = summarize_artifacts(artifact)
            if not module.effective_pom:
                maven["modules"] = []
        for report in module.test_reports:
            report_count += 1
            for key in totals:
                totals[key] += getattr(report, key)
        modules.append(
            {
                "path": module.path,
                "maven": maven,
                "test_reports": [report.model_dump() for report in module.test_reports],
                "artifact_hashes": module.artifact_hashes,
                "collection_errors": module.collection_errors,
            }
        )
    test_status = "unknown"
    if totals["failure"] or totals["error"]:
        test_status = "failed"
    elif report_count and totals["tests"] > 0:
        test_status = "passed"
    incomplete_tests = any(
        "test" in error or error == "module_limit" for error in body.collection_errors
    ) or any("test" in error for module in body.modules for error in module.collection_errors)
    if incomplete_tests and test_status != "failed":
        test_status = "incomplete"
    return {
        "modules": modules,
        "active_profiles": body.active_profiles,
        "java_version": body.java_version,
        "test_results": totals,
        "test_report_count": report_count,
        "test_status": test_status,
        "collection_errors": body.collection_errors,
    }


def public_run(row):
    return {
        "id": row.id,
        "source_id": row.source_id,
        "commit": row.commit,
        "branch": row.branch,
        "provider": row.provider,
        "run_id": row.run_id,
        "attempt": row.attempt,
        "job_name": row.job_name,
        "variant": row.variant,
        "status": row.status,
        "pipeline_url": row.pipeline_url,
        "finished_at": row.finished_at.isoformat(),
        "received_at": row.created_at.isoformat(),
        "summary": row.summary,
    }


def store_upload(db, token, body):
    source = (
        db.query(KnowledgeSource).filter_by(id=token.source_id, project_id=token.project_id).first()
    )
    if not source or (source.type or "").lower() != "git" or body.source_id != token.source_id:
        raise ValueError("CI token source does not match this build")
    if repository_identity(source) != token.repository or source.branch != token.branch:
        raise ValueError("CI source configuration changed; issue a new token")
    if source.branch and body.branch != source.branch:
        raise ValueError("Build branch differs from the configured source branch")
    summary = summarize_upload(body)
    digest_body = body.model_dump(mode="json", exclude={"finished_at"})
    payload_hash = hashlib.sha256(json.dumps(digest_body, sort_keys=True).encode()).hexdigest()
    values = {
        key: getattr(body, key)
        for key in (
            "commit",
            "branch",
            "provider",
            "run_id",
            "attempt",
            "job_name",
            "variant",
            "status",
            "pipeline_url",
            "finished_at",
        )
    }
    values.update(
        project_id=token.project_id,
        source_id=token.source_id,
        token_id=token.id,
        repository=token.repository,
        payload_hash=payload_hash,
        summary=summary,
    )
    identity = ("repository", "branch", "provider", "run_id", "attempt", "job_name", "variant")
    values["identity_hash"] = hashlib.sha256(
        json.dumps({key: values[key] for key in identity}, sort_keys=True).encode()
    ).hexdigest()
    row_id = db.execute(
        insert(CIBuildRun)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_ci_build_run_identity")
        .returning(CIBuildRun.id)
    ).scalar()
    duplicate = row_id is None
    if duplicate:
        row = (
            db.query(CIBuildRun)
            .filter_by(source_id=token.source_id, identity_hash=values["identity_hash"])
            .one()
        )
        if row.payload_hash != payload_hash:
            raise FileExistsError("This build attempt already has different immutable results")
    else:
        row = db.get(CIBuildRun, row_id)
    db.commit()
    db.refresh(row)
    return public_run(row), duplicate


def matching_builds(db, project_id, impact, nodes):
    source_ids = {node.get("source_id") for node in nodes if node.get("source_id") is not None}
    target = impact.get("target") or {}
    if target.get("source_id"):
        source_ids.add(target["source_id"])
    sources = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id.in_(source_ids),
            KnowledgeSource.project_id == project_id,
            KnowledgeSource.type.ilike("git"),
        )
        .all()
        if source_ids
        else []
    )
    items = []
    unavailable = False
    truncated = False
    for source in sources:
        commit = (source.sync_cursor or {}).get("last_commit")
        if source.sync_status != "completed" or not commit:
            unavailable = True
            continue
        query = db.query(CIBuildRun).filter_by(
            project_id=project_id,
            source_id=source.id,
            commit=commit,
            repository=repository_identity(source),
        )
        if source.branch:
            query = query.filter(CIBuildRun.branch == source.branch)
        newer = aliased(CIBuildRun)
        superseded = (
            select(newer.id)
            .where(
                newer.source_id == CIBuildRun.source_id,
                newer.repository == CIBuildRun.repository,
                newer.branch == CIBuildRun.branch,
                newer.commit == CIBuildRun.commit,
                newer.provider == CIBuildRun.provider,
                newer.run_id == CIBuildRun.run_id,
                newer.job_name == CIBuildRun.job_name,
                newer.variant == CIBuildRun.variant,
                newer.attempt > CIBuildRun.attempt,
            )
            .correlate(CIBuildRun)
            .exists()
        )
        query = query.filter(~superseded)
        rows = query.order_by(CIBuildRun.finished_at.desc(), CIBuildRun.id.desc()).limit(21).all()
        truncated = truncated or len(rows) > 20
        items.extend(public_run(row) for row in rows[:20])
    items.sort(key=lambda row: row["finished_at"], reverse=True)
    return {
        "status": "found" if items else "index_unavailable" if unavailable else "missing",
        "items": items[:20],
        "truncated": truncated or len(items) > 20,
    }


def validate_insight_ci_evidence(db, project_id, evidence):
    """Do not rebind a historical chat's build outcome to today's source commit."""
    for item in evidence:
        build_id = item.get("ci_build_id")
        if build_id is None:
            continue
        row = (
            db.query(CIBuildRun).filter_by(id=build_id, project_id=project_id).first()
            if type(build_id) is int
            else None
        )
        source = (
            db.query(KnowledgeSource).filter_by(id=row.source_id, project_id=project_id).first()
            if row
            else None
        )
        if (
            row is None
            or source is None
            or item.get("source_id") != row.source_id
            or item.get("source_commit", row.commit) != row.commit
            or source.sync_status != "completed"
            or (source.sync_cursor or {}).get("last_commit") != row.commit
            or repository_identity(source) != row.repository
            or (source.branch and source.branch != row.branch)
        ):
            raise ValueError("CI-Beleg gehört nicht zum vollständig indizierten Quellenstand")
