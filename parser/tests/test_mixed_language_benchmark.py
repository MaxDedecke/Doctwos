from __future__ import annotations

from scripts.benchmark_mixed_language import run


def test_local_benchmark_covers_five_languages_without_model_calls(tmp_path):
    sources = {
        "src/Main.java": "class Main { void run() {} }\n",
        "resources/report.xsl": (
            '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
            '<xsl:template name="main"/></xsl:stylesheet>\n'
        ),
        "resources/input.xml": "<root/>\n",
        "web/page.jsp": "<p>ok</p>\n",
        "scripts/start.sh": "#!/bin/sh\nprintf ok\n",
    }
    for relative, content in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    report = run(tmp_path, "fixture-revision")

    assert report["dataset_revision"] == "fixture-revision"
    assert {name: data["files"] for name, data in report["languages"].items()} == {
        "java": 1,
        "xslt": 1,
        "xml": 1,
        "jsp": 1,
        "shell": 1,
    }
    assert all(
        next(iter(data["parse_outcomes"].values())) == 1
        for data in report["languages"].values()
    )
    assert "no build, embedding, retrieval, or chat request" in report["limits"][0]
