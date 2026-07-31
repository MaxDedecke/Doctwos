#!/usr/bin/env python3
"""NF-003 OSS-Clearing gate: every installed Python package must carry a
license from license_allowlist_python.txt, or be a named, justified
exception in license_exceptions_python.json (docs/OSS-CLEARING.md documents
the same list for humans). Run in an environment that has exactly one
component's requirements.txt installed (backend or parser) plus pip-licenses.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def load_allowlist() -> set[str]:
    text = (SCRIPT_DIR / "license_allowlist_python.txt").read_text(encoding="utf-8")
    return {line.strip() for line in text.splitlines() if line.strip()}


def load_exceptions() -> dict:
    return json.loads((SCRIPT_DIR / "license_exceptions_python.json").read_text(encoding="utf-8"))


def main() -> int:
    allowlist = load_allowlist()
    exceptions = load_exceptions()

    raw = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--from=mixed"],
        capture_output=True, text=True, check=True,
    ).stdout
    packages = json.loads(raw)

    violations = []
    blocked_exceptions = []
    accepted_exceptions = []

    for pkg in packages:
        name = pkg["Name"]
        license_str = pkg["License"]
        parts = [p.strip() for p in license_str.split(";")]

        if name in exceptions:
            entry = exceptions[name]
            (blocked_exceptions if entry["blocking"] else accepted_exceptions).append(
                (name, pkg["Version"], entry)
            )
            continue

        if not parts or not any(p in allowlist for p in parts):
            violations.append((name, pkg["Version"], license_str))

    if accepted_exceptions:
        print("Akzeptierte, dokumentierte Ausnahmen (siehe docs/OSS-CLEARING.md):")
        for name, version, entry in accepted_exceptions:
            print(f"  - {name} {version}: {entry['license']}")
        print()

    exit_code = 0

    if blocked_exceptions:
        print("BLOCKIERENDE Lizenz-Ausnahmen (Entscheidung steht aus):")
        for name, version, entry in blocked_exceptions:
            print(f"  - {name} {version}: {entry['license']}")
            print(f"    {entry['rationale']}")
        print()
        exit_code = 1

    if violations:
        print("Nicht erlaubte/unbekannte Lizenzen (weder Allowlist noch Ausnahmeliste):")
        for name, version, license_str in violations:
            print(f"  - {name} {version}: {license_str}")
        print()
        print(
            "Neues Paket mit permissiver Lizenz? scripts/license_allowlist_python.txt "
            "ergaenzen. Neues Paket mit Copyleft-Lizenz? "
            "scripts/license_exceptions_python.json + docs/OSS-CLEARING.md ergaenzen "
            "und mit dem Auftraggeber klaeren."
        )
        exit_code = 1

    if exit_code == 0:
        print(f"OK — {len(packages)} Pakete, alle Lizenzen erlaubt oder als Ausnahme akzeptiert.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
