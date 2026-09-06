"""
Hält die Abhängigkeitsliste des Parsers und den tatsächlich importierten Code
zusammen — konkret für GitPython (O-069).

Hintergrund: `gitpython` stand bis 06.09.2026 in parser/requirements.txt, ohne
dass irgendein Modul es importiert hätte — der Git-Konnektor spricht über
`git_utils.py` direkt per Subprozess mit dem `git`-Binary. Das Paket brachte
allein in der Version 3.1.52 zwanzig Advisories mit (Argument-Injection in
weitergereichten git-Optionen, u. a. RCE über `core.sshCommand`), also ein
Sicherheitsrisiko ohne jeden Gegenwert. Beide Richtungen sind hier festgenagelt:

  * Kommt `import git` zurück, ohne dass das Paket wieder deklariert wird,
    stürzt der Worker erst zur Laufzeit ab.
  * Kommt das Paket zurück, ohne dass es jemand importiert, ist die
    Angriffsfläche ohne Nutzen wieder da.
"""

import ast
import os

PARSER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(PARSER_ROOT, "requirements.txt")


def _python_sources() -> list[str]:
    paths = []
    for dirpath, dirnames, filenames in os.walk(PARSER_ROOT):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git", "vendor"}]
        for name in filenames:
            if name.endswith(".py"):
                paths.append(os.path.join(dirpath, name))
    return paths


def _top_level_imports(path: str) -> set[str]:
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _requirement_names() -> set[str]:
    names = set()
    for line in open(REQUIREMENTS, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-") or line.startswith("."):
            continue
        name = line.split("==")[0].split(">=")[0].split("[")[0].strip()
        if name:
            names.add(name.lower().replace("_", "-"))
    return names


def test_gitpython_wird_nirgends_importiert():
    """Der Git-Konnektor bleibt bei Subprozess-Aufrufen (git_utils.py)."""
    offenders = [path for path in _python_sources() if "git" in _top_level_imports(path)]
    assert offenders == [], (
        "GitPython (`import git`) ist wieder im Einsatz: "
        f"{[os.path.relpath(p, PARSER_ROOT) for p in offenders]}. "
        "Entweder auf git_utils.py umstellen oder gitpython bewusst — mit "
        "aktueller Version — in requirements.txt aufnehmen."
    )


def test_gitpython_steht_nicht_in_den_requirements():
    """Kein ungenutztes Paket mit bekannten Advisories im Laufzeit-Image."""
    assert "gitpython" not in _requirement_names(), (
        "gitpython ist wieder deklariert, obwohl kein Modul es importiert (O-069). "
        "Ungenutzte Pakete gehören nicht ins Laufzeit-Image."
    )
