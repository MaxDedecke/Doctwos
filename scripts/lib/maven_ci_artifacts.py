"""Collect bounded Maven artifacts without publishing logs or POM properties."""

import hashlib
import json

from doctus_models.ci_artifacts import parse_test_report, sanitize_pom

MAX_FILE = 5_000_000


def _read(path, root):
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(root)
        or path.stat().st_size > MAX_FILE
    ):
        raise ValueError("Artifact outside workspace or too large")
    return path.read_bytes().decode("utf-8")


def collect(root):
    modules = []
    errors = []
    reports_seen = 0
    targets = sorted(
        path
        for path in root.rglob("target")
        if path.is_dir()
        and not path.is_symlink()
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    )
    for target in targets[:200]:
        module = {
            "path": target.parent.relative_to(root).as_posix(),
            "effective_pom": None,
            "dependency_tree": {},
            "test_reports": [],
            "artifact_hashes": {},
            "collection_errors": [],
        }
        for name, filename in (
            ("effective_pom", "effective-pom.xml"),
            ("dependency_tree", "dependencies.json"),
        ):
            path = target / "doctus-ci" / filename
            if not path.is_file():
                continue
            try:
                value = _read(path, root)
                module["artifact_hashes"][name] = hashlib.sha256(value.encode()).hexdigest()
                if name == "effective_pom":
                    value = sanitize_pom(value)
                else:
                    value = json.loads(value)
                if len(json.dumps(value)) > 1_000_000:
                    raise ValueError("Artifact exceeds the upload limit")
                module[name] = value
            except (ValueError, OSError):
                module["collection_errors"].append(name + "_unavailable")
        for folder in ("surefire-reports", "failsafe-reports"):
            for path in sorted((target / folder).glob("TEST-*.xml")):
                if reports_seen >= 1000:
                    errors.append("test_report_limit")
                    break
                reports_seen += 1
                try:
                    report = parse_test_report(_read(path, root), path.relative_to(root).as_posix())
                    report["failures"] = report["failures"][:5]
                    report["failures_truncated"] = report["failure"] + report["error"] > len(
                        report["failures"]
                    )
                    module["test_reports"].append(report)
                except (ValueError, OSError):
                    module["collection_errors"].append("test_report_unavailable")
        if (
            module["effective_pom"]
            or module["dependency_tree"]
            or module["test_reports"]
            or module["collection_errors"]
        ):
            modules.append(module)
    if len(targets) > 200:
        errors.append("module_limit")
    return modules, sorted(set(errors))


def fit_payload(payload):
    # Keep test outcomes and artifact hashes when large effective POMs would
    # otherwise prevent the whole CI result from reaching the server.
    for module in sorted(payload["modules"], key=lambda m: len(json.dumps(m)), reverse=True):
        if len(json.dumps(payload).encode()) <= 7_500_000:
            break
        module["effective_pom"] = None
        module["dependency_tree"] = {}
        module["collection_errors"].append("maven_payload_limit")
    if len(json.dumps(payload).encode()) > 7_500_000:
        raise ValueError("CI report exceeds the upload limit")
    return payload


def clear_previous_artifacts(root):
    """Remove only known generated report files before the new CI build."""
    for target in root.rglob("target"):
        if not target.is_dir() or target.is_symlink() or not target.resolve().is_relative_to(root):
            continue
        paths = [
            target / "doctus-ci" / "effective-pom.xml",
            target / "doctus-ci" / "dependencies.json",
        ]
        for folder in ("surefire-reports", "failsafe-reports"):
            paths.extend((target / folder).glob("TEST-*.xml"))
        for path in paths:
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                path.unlink()
