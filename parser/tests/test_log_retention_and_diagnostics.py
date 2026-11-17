"""Logdateien bleiben begrenzt; das Diagnosepaket enthält Zustand und Logs, aber keine Zugangsdaten."""

import os

from tasks import diagnostics
from tasks.log_retention import trim_logs


def test_large_log_files_are_copied_aside_and_truncated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_FILE_MAX_MB", "1")
    monkeypatch.setenv("LOG_FILE_KEEP", "2")
    folder = tmp_path / "parser-worker"
    folder.mkdir()
    log = folder / "parser-worker.log"
    small = tmp_path / "parser-worker" / "other.log"
    small.write_text("klein\n")

    for round_ in range(3):
        log.write_bytes(f"runde {round_}\n".encode() * 200_000)
        assert trim_logs(str(tmp_path)) == [str(log)]
        assert log.stat().st_size == 0

    assert (folder / "parser-worker.log.1").read_bytes().startswith(b"runde 2")
    assert (folder / "parser-worker.log.2").read_bytes().startswith(b"runde 1")
    assert not (folder / "parser-worker.log.3").exists()
    assert small.read_text() == "klein\n"


def test_writers_keep_appending_after_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_FILE_MAX_MB", "1")
    folder = tmp_path / "backend-api"
    folder.mkdir()
    log = folder / "backend-api.log"
    with open(log, "a") as writer:
        writer.write("x" * (1024 * 1024 + 1))
        writer.flush()
        trim_logs(str(tmp_path))
        writer.write("nach dem Kürzen\n")
        writer.flush()
    assert log.read_text().endswith("nach dem Kürzen\n")
    assert os.path.getsize(log) < 1024


def test_bundle_text_loses_credentials_from_urls_headers_and_parameters():
    text = (
        "clone https://deploy:glpat-abcdef123456@git.intern/team/app.git\n"
        "Authorization: Bearer sk-live-0123456789abcdef\n"
        '{"PRIVATE-TOKEN": "glpat-zyxwvu987654"}\n'
        "GET /api?token=abcd1234&page=2\n"
        "ENV-Geheimnis s3cr3t-value im Text\n"
    )

    cleaned = diagnostics._sanitize(text, {"s3cr3t-value"})

    for secret in (
        "glpat-abcdef123456",
        "sk-live-0123456789abcdef",
        "glpat-zyxwvu987654",
        "abcd1234",
        "s3cr3t-value",
    ):
        assert secret not in cleaned
    assert "git.intern/team/app.git" in cleaned and "page=2" in cleaned


def test_service_logs_in_the_bundle_are_the_tail_of_current_and_previous_file(
    tmp_path, monkeypatch
):
    root = tmp_path / "logs"
    (root / "parser-worker").mkdir(parents=True)
    (root / "parser-worker" / "parser-worker.log").write_text("alt\n" * 10 + "neueste Zeile\n")
    (root / "parser-worker" / "parser-worker.log.1").write_text("vorher\n")
    (root / "parser-worker" / "parser-worker.log.2").write_text("ganz alt\n")
    monkeypatch.setattr(diagnostics, "LOGS_ROOT", str(root))
    monkeypatch.setattr(diagnostics, "LOG_TAIL_BYTES", 20)
    out = tmp_path / "out"
    out.mkdir()

    diagnostics._copy_service_logs(str(out), set())

    current = (out / "logs_parser-worker.txt").read_text()
    assert current.endswith("neueste Zeile\n") and "nur die letzten" in current
    assert (out / "logs_parser-worker_previous.txt").read_text() == "vorher\n"
    assert sorted(p.name for p in out.iterdir()) == [
        "logs_parser-worker.txt",
        "logs_parser-worker_previous.txt",
    ]
