"""CI ingestion, credential scope and automatic change-package selection."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func
from doctus_models.database import CIBuildRun, CIBuildToken, CodeEntity, KnowledgeSource, User
from core.db_setup import SessionLocal
from services.ci_builds import CIBuildUpload, store_upload


@pytest.fixture
def ci_source(client, db_session, test_project, test_team):
    source = KnowledgeSource(
        name="ci",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="main",
        repo_fingerprint="repo",
        sync_status="completed",
        sync_cursor={"last_commit": "a" * 40},
    )
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        name="Worker",
        type="class",
        file_path="Worker.java",
        start_line=1,
        end_line=2,
    )
    db_session.add(entity)
    db_session.commit()
    response = client.post(
        f"/projects/{test_project}/ci-tokens", json={"source_id": source.id, "name": "pipeline"}
    )
    assert response.status_code == 201, response.text
    return source, entity, response.json()


def payload(source, **changes):
    result = {
        "source_id": source.id,
        "commit": "a" * 40,
        "branch": "main",
        "provider": "github",
        "run_id": "100",
        "attempt": 1,
        "job_name": "verify",
        "variant": "jdk21",
        "status": "success",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_url": "https://example.test/build/100?token=discard",
        "active_profiles": ["integration"],
        "modules": [
            {
                "path": ".",
                "effective_pom": "<project><groupId>demo</groupId><artifactId>app</artifactId><version>1</version></project>",
                "dependency_tree": {
                    "artifactId": "app",
                    "version": "1",
                    "children": [
                        {"groupId": "lib", "artifactId": "api", "version": "2", "scope": "compile"}
                    ],
                },
                "test_reports": [
                    {
                        "path": "target/surefire-reports/TEST-app.xml",
                        "sha256": "f" * 64,
                        "tests": 3,
                        "failure": 0,
                        "error": 0,
                        "skipped": 1,
                    }
                ],
            }
        ],
    }
    result.update(changes)
    return result


def upload(client, token, body):
    return client.post(
        "/ci/builds", headers={"Authorization": "Bearer " + token["token"]}, json=body
    )


def test_upload_before_sync_is_attached_to_exact_commit(
    ci_source, client, db_session, test_project
):
    source, entity, token = ci_source
    response = upload(client, token, payload(source, commit="b" * 40))
    assert response.status_code == 201, response.text
    assert response.json()["build"]["pipeline_url"] == "https://example.test/build/100"
    package = f"/projects/{test_project}/change-package?entity_id={entity.id}"
    assert client.get(package).json()["ci_builds"]["status"] == "missing"
    source.sync_cursor = {"last_commit": "b" * 40}
    db_session.commit()
    builds = client.get(package).json()["ci_builds"]
    assert builds["status"] == "found"
    assert builds["items"][0]["commit"] == "b" * 40
    assert builds["items"][0]["summary"]["test_results"]["tests"] == 3
    assert builds["items"][0]["summary"]["modules"][0]["maven"]["dependencies"][1]["version"] == "2"


def test_retries_conflicts_and_late_older_attempt(ci_source, client, db_session, test_project):
    source, entity, token = ci_source
    body = payload(source, status="failed", attempt=2)
    assert upload(client, token, body).status_code == 201
    retried = upload(client, token, {**body, "finished_at": datetime.now(timezone.utc).isoformat()})
    assert retried.status_code == 200 and retried.json()["duplicate"]
    assert upload(client, token, {**body, "status": "success"}).status_code == 409
    assert upload(client, token, payload(source, attempt=1)).status_code == 201
    builds = client.get(f"/projects/{test_project}/change-package?entity_id={entity.id}").json()[
        "ci_builds"
    ]
    assert len(builds["items"]) == 1
    assert builds["items"][0]["attempt"] == 2
    assert builds["items"][0]["status"] == "failed"
    assert db_session.query(CIBuildRun).filter_by(source_id=source.id).count() == 2


def test_auth_scope_revocation_and_incomplete_tests(ci_source, client, db_session, test_project):
    source, entity, token = ci_source
    assert client.post("/ci/builds", json=payload(source)).status_code == 401
    assert upload(client, token, payload(source, source_id=source.id + 10000)).status_code == 422
    assert upload(client, token, payload(source, branch="release")).status_code == 422
    bad = payload(source)
    bad["modules"][0]["test_reports"][0]["failure"] = 4
    assert upload(client, token, bad).status_code == 422
    body = payload(source, collection_errors=["test_report_limit"])
    assert upload(client, token, body).json()["build"]["summary"]["test_status"] == "incomplete"
    assert client.delete(f"/projects/{test_project}/ci-tokens/{token['id']}").status_code == 204
    assert upload(client, token, payload(source, run_id="101")).status_code == 401
    stored = db_session.get(CIBuildToken, token["id"])
    assert stored.token_hash != token["token"]
    assert stored.token_hash == __import__("hashlib").sha256(token["token"].encode()).hexdigest()
    listed = client.get(f"/projects/{test_project}/ci-tokens").json()
    assert "token" not in listed["tokens"][0] and "token_hash" not in listed["tokens"][0]


def test_expiry_and_disabled_owner(ci_source, client, db_session):
    source, _, token = ci_source
    row = db_session.get(CIBuildToken, token["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert upload(client, token, payload(source)).status_code == 401
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    owner = db_session.get(User, row.user_id)
    owner.is_active = False
    db_session.commit()
    assert upload(client, token, payload(source)).status_code == 403
    owner.is_active = True
    db_session.commit()


def test_concurrent_identical_uploads_have_one_record(ci_source, db_session):
    source, _, token = ci_source
    body = CIBuildUpload.model_validate(payload(source))

    def persist():
        with SessionLocal() as db:
            row = db.get(CIBuildToken, token["id"])
            return store_upload(db, row, body)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: persist(), range(2)))
    assert {result[0]["id"] for result in results} == {results[0][0]["id"]}
    assert sorted(result[1] for result in results) == [False, True]
    assert db_session.query(func.count(CIBuildRun.id)).filter_by(source_id=source.id).scalar() == 1


def test_runner_posts_multimodule_reports_and_preserves_maven_failure(
    ci_source, client, db_session, tmp_path, monkeypatch
):
    import os
    from pathlib import Path
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import subprocess

    source, _, token = ci_source

    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.com")
    (tmp_path / ".gitignore").write_text("target/\n")
    (tmp_path / "pom.xml").write_text("<project><artifactId>reactor</artifactId></project>")
    executable = tmp_path / "fake-maven"
    executable.write_text("""#!/usr/bin/env python3
import sys
from pathlib import Path
if 'verify' in sys.argv:
 p=Path('app/target/surefire-reports'); p.mkdir(parents=True,exist_ok=True)
 (p/'TEST-new.xml').write_text('<testsuite><testcase name="works"/><testcase name="fails"><failure/></testcase></testsuite>')
 p=Path('api/target/failsafe-reports'); p.mkdir(parents=True,exist_ok=True)
 (p/'TEST-integration.xml').write_text('<testsuite><testcase name="integration"/></testsuite>')
 raise SystemExit(3)
if any('effective-pom' in arg for arg in sys.argv):
 p=Path('target/doctus-ci'); p.mkdir(parents=True,exist_ok=True)
 (p/'effective-pom.xml').write_text('<projects><project><groupId>demo</groupId><artifactId>reactor</artifactId><version>1</version><properties><password>DO_NOT_UPLOAD</password></properties></project></projects>')
if any(':tree' in arg for arg in sys.argv):
 p=Path('app/target/doctus-ci'); p.mkdir(parents=True,exist_ok=True)
 (p/'dependencies.json').write_text('{"artifactId":"app","children":[{"artifactId":"api","version":"2"}]}')
""")
    executable.chmod(0o755)
    git("add", ".")
    git("commit", "-m", "reactor")
    source.sync_cursor = {"last_commit": git("rev-parse", "HEAD")}
    db_session.commit()
    stale = tmp_path / "app/target/surefire-reports"
    stale.mkdir(parents=True)
    (stale / "TEST-stale.xml").write_text('<testsuite tests="99"/>')
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            content = self.rfile.read(int(self.headers["Content-Length"]))
            captured.append(content)
            response = client.post(
                "/ci/builds",
                content=content,
                headers={
                    "Authorization": self.headers["Authorization"],
                    "Content-Type": "application/json",
                },
            )
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = Path(__file__).resolve().parents[2] / "scripts" / "publish_maven_ci.py"
        environment = {
            **os.environ,
            "DOCTUS_URL": f"http://127.0.0.1:{server.server_port}",
            "DOCTUS_SOURCE_ID": str(source.id),
            "DOCTUS_CI_TOKEN": token["token"],
        }
        for key in ("GITHUB_SHA", "GITHUB_HEAD_REF", "GITHUB_REF_NAME", "CI_COMMIT_SHA"):
            environment.pop(key, None)
        result = subprocess.run(
            [
                "python",
                str(script),
                "--workspace",
                str(tmp_path),
                "--provider",
                "generic",
                "--run-id",
                "runner-1",
                "--branch",
                "main",
                "--maven",
                str(executable),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert result.returncode == 3, result.stdout + result.stderr
    assert token["token"] not in result.stdout + result.stderr
    assert len(captured) == 1
    assert b"DO_NOT_UPLOAD" not in captured[0]
    row = db_session.query(CIBuildRun).filter_by(source_id=source.id, run_id="runner-1").one()
    assert row.status == "failed"
    assert row.summary["test_results"]["tests"] == 3
    assert row.summary["test_results"]["failure"] == 1
    assert row.summary["test_status"] == "failed"
    assert len(row.summary["modules"]) == 3


def test_project_members_cannot_manage_ci_credentials(
    ci_source, client, db_session, test_project, test_team
):
    from uuid import uuid4
    from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
    from doctus_models.database import ProjectMembership, TeamMembership

    source, _, token = ci_source
    member = User(
        username="ci-member-" + uuid4().hex,
        email=uuid4().hex + "@example.test",
        role="user",
        is_active=True,
    )
    db_session.add(member)
    db_session.flush()
    db_session.add_all(
        [
            TeamMembership(team_id=test_team, user_id=member.id),
            ProjectMembership(project_id=test_project, user_id=member.id, role="member"),
        ]
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(member.id))
    try:
        listed = client.get(f"/projects/{test_project}/ci-tokens")
        assert listed.status_code == 200
        assert listed.json()["can_manage"] is False and listed.json()["tokens"] == []
        assert (
            client.post(
                f"/projects/{test_project}/ci-tokens",
                json={"source_id": source.id, "name": "forbidden"},
            ).status_code
            == 403
        )
        assert client.delete(f"/projects/{test_project}/ci-tokens/{token['id']}").status_code == 403
    finally:
        db_session.query(ProjectMembership).filter_by(user_id=member.id).delete()
        db_session.query(TeamMembership).filter_by(user_id=member.id).delete()
        db_session.delete(member)
        db_session.commit()


def test_source_change_and_empty_reports_are_explicit(ci_source, client, db_session, test_project):
    source, entity, token = ci_source
    response = upload(client, token, payload(source, modules=[]))
    assert response.status_code == 201
    assert response.json()["build"]["summary"]["test_status"] == "unknown"
    source.branch = "release"
    db_session.commit()
    assert upload(client, token, payload(source, run_id="new", branch="release")).status_code == 422
    builds = client.get(f"/projects/{test_project}/change-package?entity_id={entity.id}").json()[
        "ci_builds"
    ]
    assert builds["status"] == "missing"
