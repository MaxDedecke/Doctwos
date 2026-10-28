"""Stable dependency fingerprints, including relationships discovered during import."""

from core.analysis_fingerprint import analysis_fingerprint


class DependencyFingerprints:
    def __init__(self, inputs, hashes, dependencies):
        self.inputs, self.hashes, self.dependencies = (
            inputs,
            hashes,
            dependencies,
        )
        self.base = {path: analysis_fingerprint(**values) for path, values in inputs.items()}
        self.cache = {}

    def for_path(self, path, stack=frozenset()):
        values = self.inputs.get(path)
        if values is None:
            return ""
        if path in stack or len(stack) >= 64:
            return self.base[path]
        if path in self.cache:
            return self.cache[path]
        dependencies = dict(values.get("dependencies") or {})
        for target in sorted(self.dependencies.get(path, ())):
            dependencies[f"source:{target}:content_hash"] = self.hashes.get(target, "")
            dependencies[f"source:{target}:analysis_fingerprint"] = self.for_path(
                target, stack | {path}
            )
        self.cache[path] = analysis_fingerprint(**{**values, "dependencies": dependencies})
        return self.cache[path]

    def persist_discovered(self, db, source_id, dependency_reader):
        from doctus_models.database import SourceScanFile

        settled = DependencyFingerprints(self.inputs, self.hashes, dependency_reader(db, source_id))
        # Evaluate in the same deterministic order as the next scan, including
        # cyclic include/type dependencies. Newly learned edges need no reparse.
        for path in sorted(self.inputs):
            settled.for_path(path)
        for row in db.query(SourceScanFile).filter(SourceScanFile.source_id == source_id).all():
            if row.file_path in settled.inputs and row.parse_status != "error":
                row.analysis_fingerprint = settled.for_path(row.file_path)
        db.flush()
