"""Installer credential handoff, without Docker, services or real passwords."""

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = """
=================================================================
 Erster Start: Superuser angelegt.
   Benutzer:  test-admin
   Passwort:  test-only-$literal\\value
 Dieses Passwort wird NUR EINMAL angezeigt und muss beim ersten
 Login geändert werden.
=================================================================
"""
HARNESS = r"""
. "$HELPER"
poll=0
docker() {
    case "$*" in
        "compose logs --no-color --no-log-prefix --since 2026-09-06T12:00:00Z backend-api")
            [ "$LOG_ERROR" != 1 ] || return 1
            if [ "$poll" -eq 0 ]; then
                printf '%s\n' "$FIRST_LOGS"
            else
                printf '%s\n' "$NEXT_LOGS"
            fi
            ;;
        "compose ps -q backend-api") printf '%s\n' test-backend ;;
        "inspect --format "*) printf '%s\n' "$HEALTH" ;;
        *) echo "Unexpected docker arguments: $*" >&2; return 99 ;;
    esac
}
sleep() { poll=$((poll + 1)); }
show_bootstrap_credentials 2026-09-06T12:00:00Z
"""


class BootstrapCredentialsTest(unittest.TestCase):
    def run_helper(self, first="", next_logs="", health="starting", log_error="0"):
        result = subprocess.run(
            ["sh", "-c", HARNESS],
            env={
                **os.environ,
                "HELPER": str(ROOT / "scripts/lib/env-bootstrap.sh"),
                "FIRST_LOGS": first,
                "NEXT_LOGS": next_logs,
                "HEALTH": health,
                "LOG_ERROR": log_error,
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Unexpected docker arguments", result.stderr)
        return result.stdout + result.stderr

    def test_generated_credentials_and_change_reminder(self):
        output = self.run_helper(first=BOOTSTRAP)
        self.assertIn("FIRST LOGIN", output)
        self.assertEqual(output.count("test-admin"), 1)
        self.assertIn(r"test-only-$literal\value", output)
        self.assertIn("Change the password", output)
        self.assertNotIn("WARNING", output)

    def test_waits_for_delayed_bootstrap(self):
        output = self.run_helper(first="Starting migrations", next_logs=BOOTSTRAP)
        self.assertIn("FIRST LOGIN", output)
        self.assertNotIn("Starting migrations", output)

    def test_ready_backend_still_displays_new_credentials(self):
        output = self.run_helper(first=BOOTSTRAP, health="healthy")
        self.assertIn("FIRST LOGIN", output)
        self.assertNotIn("No new generated password", output)

    def test_partial_block_is_not_printed_until_complete(self):
        output = self.run_helper(first=BOOTSTRAP.split(" Dieses")[0], next_logs=BOOTSTRAP)
        self.assertEqual(output.count("test-admin"), 1)
        self.assertIn("FIRST LOGIN", output)

    def test_existing_installation_does_not_wait_or_show_credentials(self):
        output = self.run_helper(health="healthy")
        self.assertIn("existing or configured credentials", output)
        self.assertNotIn("FIRST LOGIN", output)
        self.assertNotIn("WARNING", output)

    def test_configured_password_is_not_echoed(self):
        output = self.run_helper(
            first="[bootstrap] Superuser 'admin' angelegt (Passwort aus BOOTSTRAP_SUPERUSER_PASSWORD).",
            health="healthy",
        )
        self.assertIn("existing or configured credentials", output)
        self.assertNotIn("BOOTSTRAP_SUPERUSER_PASSWORD", output)

    def test_unrelated_log_secrets_are_not_echoed(self):
        output = self.run_helper(
            first="private-log-content\n   Passwort:  unrelated", health="healthy"
        )
        self.assertNotIn("private-log-content", output)
        self.assertNotIn("unrelated", output)

    def test_timeout_is_bounded_and_actionable(self):
        output = self.run_helper()
        self.assertIn("within 120 seconds", output)
        self.assertIn("docker compose logs backend-api", output)
        self.assertNotIn("FIRST LOGIN", output)

    def test_incomplete_credentials_are_never_presented_as_success(self):
        incomplete = BOOTSTRAP.replace("   Passwort:", "   Missing:")
        output = self.run_helper(first=incomplete, next_logs=incomplete)
        self.assertIn("WARNING", output)
        self.assertNotIn("test-admin", output)
        self.assertNotIn("test-only", output)

    def test_log_failure_is_actionable_without_aborting_installation(self):
        output = self.run_helper(log_error="1")
        self.assertIn("Could not read backend startup logs", output)
        self.assertIn("docker compose logs backend-api", output)

    def test_both_installers_capture_boundary_before_start_and_display_after(self):
        for path in (ROOT / "install.sh", ROOT / "scripts/install-offline.sh"):
            with self.subTest(installer=path.name):
                script = path.read_text()
                self.assertLess(
                    script.index("startup_since=$(date"), script.index("docker compose up -d")
                )
                self.assertLess(
                    script.index("docker compose up -d"),
                    script.index('show_bootstrap_credentials "$startup_since"'),
                )


if __name__ == "__main__":
    unittest.main()
