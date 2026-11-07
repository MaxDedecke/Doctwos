#!/usr/bin/env python3
"""Run Maven in CI and publish commit-bound evidence using only Python stdlib."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TOOLS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_ROOT / "packages" / "doctus-models"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from maven_ci_artifacts import collect, fit_payload, clear_previous_artifacts  # noqa: E402


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def metadata(root, args):
    env = os.environ
    provider = args.provider or (
        "github"
        if env.get("GITHUB_ACTIONS")
        else "gitlab"
        if env.get("GITLAB_CI")
        else "jenkins"
        if env.get("JENKINS_URL")
        else "generic"
    )
    commit = git(root, "rev-parse", "HEAD")
    expected = args.commit or env.get("GITHUB_SHA") or env.get("CI_COMMIT_SHA") or commit
    if commit != expected:
        raise ValueError("CI commit differs from checked-out HEAD")
    if subprocess.run(
        ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"], check=False
    ).returncode:
        raise ValueError("Tracked workspace differs from the commit")
    branch = (
        args.branch
        or env.get("GITHUB_HEAD_REF")
        or env.get("GITHUB_REF_NAME")
        or env.get("CI_COMMIT_REF_NAME")
        or env.get("BRANCH_NAME")
    )
    if not branch:
        branch = git(root, "symbolic-ref", "--short", "HEAD")
    run_id = (
        args.run_id
        or env.get("GITHUB_RUN_ID")
        or env.get("CI_PIPELINE_ID")
        or env.get("BUILD_NUMBER")
    )
    if not run_id:
        raise ValueError("A stable CI run ID is required")
    attempt = args.attempt or int(env.get("GITHUB_RUN_ATTEMPT") or env.get("CI_JOB_ID") or "1")
    job = (
        args.job_name
        or env.get("GITHUB_JOB")
        or env.get("CI_JOB_NAME")
        or env.get("JOB_NAME")
        or "maven"
    )
    url = args.pipeline_url or env.get("CI_PIPELINE_URL") or env.get("BUILD_URL")
    if not url and provider == "github":
        url = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{env.get('GITHUB_REPOSITORY', '')}/actions/runs/{run_id}"
    return {
        "source_id": args.source_id,
        "commit": commit,
        "branch": branch,
        "provider": provider,
        "run_id": run_id,
        "attempt": attempt,
        "job_name": job,
        "variant": args.variant,
        "pipeline_url": url,
        "java_version": args.java_version,
        "active_profiles": [profile for profile in args.profiles.split(",") if profile],
    }


def run_maven(root, args):
    executable = args.maven
    if not executable:
        wrapper = "mvnw.cmd" if os.name == "nt" else "mvnw"
        executable = str(root / wrapper) if (root / wrapper).is_file() else "mvn"
    common = [executable, "-B", "-ntp", *args.maven_arg]
    if args.profiles:
        common.append("-P" + args.profiles)
    try:
        result = subprocess.run([*common, "clean", "verify"], cwd=root, check=False).returncode
    except OSError:
        return 127, ["maven_command_unavailable"]
    errors = []
    goals = [
        [
            "org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom",
            "-Doutput=target/doctus-ci/effective-pom.xml",
        ],
        [
            "org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree",
            "-DoutputType=json",
            "-DoutputFile=target/doctus-ci/dependencies.json",
        ],
    ]
    for index, goal in enumerate(goals):
        if subprocess.run([*common, *goal], cwd=root, check=False).returncode:
            errors.append(
                ("effective_pom" if index == 0 else "dependency_tree") + "_command_failed"
            )
    return result, errors


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def publish(url, secret, payload):
    parts = urlsplit(url)
    if (
        parts.scheme not in {"https", "http"}
        or not parts.netloc
        or parts.username
        or parts.password
    ):
        raise ValueError("A credential-free HTTP Doctus URL is required")
    context = ssl.create_default_context(cafile=os.environ.get("DOCTUS_CA_FILE"))
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    data = json.dumps(payload).encode()
    for attempt in range(3):
        request = urllib.request.Request(
            url.rstrip("/") + "/ci/builds",
            data=data,
            headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"},
        )
        try:
            with opener.open(request, timeout=30) as response:
                result = json.loads(response.read(20000))
            print("Doctus CI report stored, build ID", result["build"]["id"])
            return
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                detail = ""
                try:
                    message = json.loads(exc.read(2000)).get("detail", "")
                    if isinstance(message, str):
                        detail = message
                    elif isinstance(message, list):
                        detail = "; ".join(str(item.get("msg", "")) for item in message)
                except (ValueError, AttributeError):
                    pass
                detail = detail.replace(secret, "[redacted]")[:400]
                raise ValueError(f"Doctus rejected CI report (HTTP {exc.code}): {detail}") from None
        except urllib.error.URLError:
            pass
        if attempt < 2:
            time.sleep(2**attempt)
    raise ValueError("Doctus CI upload failed after three attempts")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--url", default=os.getenv("DOCTUS_URL"))
    parser.add_argument("--source-id", type=int, default=os.getenv("DOCTUS_SOURCE_ID"))
    parser.add_argument("--provider", choices=["github", "gitlab", "jenkins", "generic"])
    parser.add_argument("--run-id")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--job-name")
    parser.add_argument("--variant", default=os.getenv("DOCTUS_CI_VARIANT", "default"))
    parser.add_argument("--pipeline-url")
    parser.add_argument("--commit")
    parser.add_argument("--branch")
    parser.add_argument("--profiles", default=os.getenv("MAVEN_PROFILES", ""))
    parser.add_argument("--java-version", default=os.getenv("JAVA_VERSION"))
    parser.add_argument("--maven")
    parser.add_argument("--maven-arg", action="append", default=[])
    parser.add_argument("--publish-only", action="store_true")
    parser.add_argument("--status", choices=["success", "failed", "cancelled"])
    args = parser.parse_args(argv)
    secret = os.environ.get("DOCTUS_CI_TOKEN")
    if not args.url or not args.source_id or not secret:
        parser.error("DOCTUS_URL, DOCTUS_SOURCE_ID and DOCTUS_CI_TOKEN are required")
    root = Path(args.workspace).resolve()
    build_exit = 0
    try:
        payload = metadata(root, args)
        if args.publish_only:
            if not args.status:
                raise ValueError("--publish-only needs --status")
            status = args.status
            errors = []
        else:
            clear_previous_artifacts(root)
            build_exit, errors = run_maven(root, args)
            status = "success" if build_exit == 0 else "failed"
        # Re-check after Maven so tracked build modifications cannot be
        # silently attributed to the clean commit.
        metadata(root, args)
        modules, collection_errors = collect(root)
        payload.update(
            status=status,
            finished_at=datetime.now(timezone.utc).isoformat(),
            modules=modules,
            collection_errors=errors + collection_errors,
        )
        publish(args.url, secret, fit_payload(payload))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("Doctus CI:", str(exc), file=sys.stderr)
        return build_exit or 1
    return build_exit


if __name__ == "__main__":
    raise SystemExit(main())
