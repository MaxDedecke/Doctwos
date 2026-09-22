"""Read-only O-245 corpus audit: python audit_java_calls.py /path/to/junit."""

import argparse
from collections import Counter
import json
from pathlib import Path

from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    results = [
        parse_java_file(path.read_text(encoding="utf-8"), path.relative_to(args.root).as_posix())
        for path in sorted(args.root.rglob("*.java"))
    ]
    resolve_global_edges(results)
    calls = [edge for result in results for edge in result.edges if edge.type == "CALLS"]
    resolved_calls = [edge for edge in calls if edge.resolution == "resolved"]
    print(
        json.dumps(
            {
                "files": len(results),
                "diagnostics": sum(len(result.diagnostics) for result in results),
                "calls": len(calls),
                "resolutions": dict(Counter(edge.resolution for edge in calls)),
                "reasons": dict(
                    Counter(edge.meta.get("resolution_reason", "<missing>") for edge in calls)
                ),
                "receiver_evidence": dict(
                    Counter(
                        edge.meta.get("receiver_resolution", "direct_or_static") for edge in calls
                    )
                ),
                "resolved_targets": dict(
                    Counter(
                        edge.meta.get("target_qualified_name", "<missing>")
                        for edge in resolved_calls
                    )
                ),
                "unresolved_examples": [
                    {
                        "path": result.path,
                        "line": edge.src_start_line,
                        "source": edge.src_name,
                        "call": edge.dst_name,
                        "receiver": edge.meta.get("receiver"),
                        "reason": edge.meta.get("resolution_reason"),
                    }
                    for result in results
                    for edge in result.edges
                    if edge.type == "CALLS" and edge.resolution != "resolved"
                ][:50],
                "super_calls": [
                    {
                        "path": result.path,
                        "line": edge.src_start_line,
                        "target": edge.dst_name,
                        "resolution": edge.resolution,
                        "reason": edge.meta.get("resolution_reason"),
                    }
                    for result in results
                    for edge in result.edges
                    if edge.type == "CALLS" and edge.meta.get("receiver") == "super"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
