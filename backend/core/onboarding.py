"""
backend/core/onboarding.py
===========================
Rollen-konditionierte System-Prompts für den Onboarding-Trigger ("Rentner-
Backup", FA-ONB-01). Kein eigener Endpunkt/Agent — die Nachricht läuft durch
den normalen POST /chat SSE-Pfad, nur mit diesem statt dem User-Profil-Prompt.
"""

_PREAMBLE = (
    "Du bist Doctus, der Onboarding-Assistent für das Projekt „{project_name}“. "
    "Ein/e Mitarbeiter/in verschafft sich gerade einen Überblick über dieses Projekt. "
    "Antworte strukturiert mit Überschriften/Stichpunkten, nicht als Fließtext-Wand.\n\n"
)

_ROLE_BLOCKS = {
    "member": (
        "Gib eine allgemeine Projekteinführung: (1) Kurze Zusammenfassung, worum es in "
        "diesem Projekt geht, (2) die wichtigsten Dokumente und Wissensquellen, (3) zentrale "
        "Ansprechpartner/Kontakte falls auffindbar, (4) aktuell offene Punkte/Aufgaben."
    ),
    "admin": (
        "Gib einen vollständigen Überblick: allgemeine Projekteinführung UND zusätzlich "
        "Team-/Zugriffsstatistiken (Mitgliederzahl, Rollenverteilung, verknüpfte "
        "Wissensquellen) sowie Link-/Knowledge-Graph-Statistiken, falls über die "
        "verfügbaren Werkzeuge ermittelbar."
    ),
}

_CLOSING = (
    "\n\nNutze aktiv deine verfügbaren Werkzeuge (Repository-Suche sowie ggf. verbundene "
    "Confluence/Jira-Quellen), um konkrete, historische Entscheidungen, "
    "Protokolleinträge und Dokumente zu finden — verlasse dich nicht auf allgemeines Wissen. "
    "Zitiere Quellen wie gewohnt inline."
)


def build_onboarding_system_prompt(role: str, project_name: str) -> str:
    """Baut den rollen-spezifischen Onboarding-Systemprompt für Projekt `project_name`."""
    role_block = _ROLE_BLOCKS.get(role, _ROLE_BLOCKS["member"])
    return _PREAMBLE.format(project_name=project_name) + role_block + _CLOSING
