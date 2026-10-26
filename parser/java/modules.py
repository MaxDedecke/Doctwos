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


def source_kind_from_path(path: str) -> str | None:
    """Classify conventional Java and generated-source roots without I/O."""
    parts = path.replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if parts[index] == "src" and parts[index + 1].lower() in _JAVA_SOURCE_SETS:
            if parts[index + 2] == "java":
                return "source"
            if parts[index + 2] == "resources":
                return "resource"
        if parts[index : index + 2] == ["target", "generated-sources"]:
            return "generated"
        if parts[index : index + 2] == ["src", "generated"]:
            return "generated"
    return None


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
        if parts[index : index + 2] == ["target", "generated-sources"]:
            return "main"
        if parts[index : index + 2] == ["src", "generated"]:
            return "main"
    return None


def module_from_path(path: str) -> str | None:
    """Return the path before a conventional ``src/<set>/java`` root."""

    parts = path.replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if (
            parts[index] == "src"
            and parts[index + 1].lower() in _JAVA_SOURCE_SETS
            and parts[index + 2] in {"java", "resources"}
        ):
            return "/".join(parts[:index]) or "."
        if parts[index : index + 2] == ["target", "generated-sources"] or parts[
            index : index + 2
        ] == ["src", "generated"]:
            return "/".join(parts[:index]) or "."
    return None


_BUILD_EXCLUDED_DIRS = {
    "target",
    "build",
    ".gradle",
    "bin",
    "out",
    ".idea",
    ".settings",
}


def is_build_excluded(path, extensions):
    import os
    from core.language_detection import detect_language

    if detect_language(path, extensions) != "java":
        return False
    parts = path.replace("\\", "/").split("/")
    enabled = os.getenv("DOCTUS_INCLUDE_GENERATED_JAVA", "").lower() in {"1", "true", "yes"}
    generated = any(
        parts[i : i + 2] == ["target", "generated-sources"] for i in range(len(parts) - 2)
    )
    if enabled and generated:
        return False
    return any(p.lower() in _BUILD_EXCLUDED_DIRS for p in parts[:-1])
