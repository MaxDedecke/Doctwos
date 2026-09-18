"""Opt-in checks on the unmodified local JUnit reference checkout."""
import os
from pathlib import Path

import pytest

from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def test_junit_engine_super_call_is_not_reported_as_recursion():
    root = os.getenv('JUNIT_REFERENCE_ROOT')
    if not root:
        pytest.skip('Set JUNIT_REFERENCE_ROOT to the JUnit reference checkout')
    path = 'junit-jupiter-engine/src/main/java/org/junit/jupiter/engine/JupiterTestEngine.java'
    source = (Path(root) / path).read_text(encoding='utf-8')
    result = parse_java_file(source, path)
    resolve_global_edges([result])
    calls = [e for e in result.edges if e.type == 'CALLS'
             and e.meta.get('receiver') == 'super'
             and e.meta.get('method_name') == 'createExecutorService']
    assert len(calls) == 1
    edge = calls[0]
    assert 'super.createExecutorService(request)' in source.splitlines()[edge.src_start_line - 1]
    assert edge.resolution == 'unresolved'
    assert edge.meta['resolution_reason'] == 'super_dispatch_requires_hierarchy'
