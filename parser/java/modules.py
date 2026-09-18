"""Maven/Gradle source-path hints for Java module metadata."""

from __future__ import annotations


_JAVA_SOURCE_SETS = {
    "main",
    "test",
    "integrationtest",
    "integration-test",
    "it",
    "testfixtures",
    "test-fixtures",
}


def source_set_from_path(path: str) -> str | None:
    """Return the conventional source-set name for a Java source path."""

    parts = path.replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if (
            parts[index] == "src"
            and parts[index + 1].lower() in _JAVA_SOURCE_SETS
            and parts[index + 2] == "java"
        ):
            return parts[index + 1]
    return None


def module_from_path(path: str) -> str | None:
    """Return the path before a conventional ``src/<set>/java`` root."""

    parts = path.replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if (
            parts[index] == "src"
            and parts[index + 1].lower() in _JAVA_SOURCE_SETS
            and parts[index + 2] == "java"
        ):
            return "/".join(parts[:index]) or "."
    return None
