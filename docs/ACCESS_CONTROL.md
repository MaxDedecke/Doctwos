# Doctus — Zugriffsmodell

**Stand:** 01.09.2026

Doctus schützt Inhalte in zwei aufeinanderfolgenden Ebenen: Team-Zugehörigkeit
grenzt Organisationseinheiten voneinander ab; Projektmitgliedschaft begrenzt
den Zugriff innerhalb eines Teams weiter. Berechtigungsprüfungen erfolgen im
Backend bei jeder Ressource und nicht nur durch die Oberfläche.

## Die zwei Ebenen

| Ebene | Zweck | Modelle | Sichtbare Verwaltung |
|---|---|---|---|
| Team | Organisation und grundlegende Sichtbarkeit | `Team`, `TeamMembership` | Einstellungen → Teams (nur globale Admins) |
| Projekt | Fachlicher Arbeitskontext innerhalb eines Teams | `Project`, `ProjectMembership`, `ProjectAccessRequest` | Einstellungen → Projekte |

Eine Teammitgliedschaft ist die Voraussetzung, ein Projekt dieses Teams
überhaupt zu entdecken oder Zugriff darauf anzufordern. Sie berechtigt jedoch
nicht automatisch zur Nutzung des Projekts: Dafür ist zusätzlich eine
Projektmitgliedschaft nötig. Globale Administratoren dürfen beide Ebenen
uneingeschränkt verwalten.

## Rollen und Aktionen

| Rolle | Berechtigungen |
|---|---|
| Globaler Administrator (`User.role == superuser`) | Sieht alle Teams und Projekte; verwaltet Teams, Nutzer und Mitgliedschaften. |
| Projekt-Ersteller oder Projekt-Admin | Verwaltet Mitglieder und Zugriffsanfragen des jeweiligen Projekts. |
| Nutzer (`User.role == user`) mit Projektrolle `admin` | Verwaltet Mitglieder, Zugriffsanfragen und projektbezogene Quellen des jeweiligen Projekts. |
| Nutzer (`User.role == user`) mit Projektrolle `member` | Nutzt ausschließlich die ihm zugewiesenen Projekte und deren Quellen; globale Verwaltungsaktionen sind nicht erlaubt. |

Das aktuelle Datenmodell kennt auf Benutzerebene ausschließlich `superuser` und
`user`; zusätzliche fachliche Rollen wie `pruefingenieur` sind nicht als
implementierte Berechtigung hinterlegt und werden daher nicht als wirksame
Rolle behandelt.

Neue oder nicht zugewiesene Nutzer erhalten keine implizite Mitgliedschaft.
Der beim Erststart angelegte Superuser wird für den sicheren Bootstrap in das
Standardteam aufgenommen; daraus folgt keine automatische Zuweisung späterer
Nutzer.

## Durchsetzung im Backend

- `backend/core/teams.py` liefert mit `get_visible_team_ids()` die erlaubten
  Teams; `assert_team_visible()` verschleiert fremde Teams bewusst mit HTTP
  404, damit deren Existenz nicht verraten wird.
- `backend/core/projects.py` liefert mit `get_visible_project_ids()` die
  erlaubten Projekte; `assert_project_visible()` schützt Projektressourcen.
- Eine Zugriffsanfrage prüft zunächst die Team-Sichtbarkeit. Fremde Projekte
  sind somit weder anfragbar noch über ihre Kennung aufdeckbar.
- Projektgebundene Wissensquellen, Dokumente, Entitäten, Links und Graphdaten
  erfordern zusätzlich die Mitgliedschaft im konkreten Projekt. Globale Quellen
  bleiben für berechtigte Teammitglieder sichtbar.
- Die globale Modellumschaltung (`POST /model-info`) ist ausschließlich für
  globale Administratoren erlaubt; Lesen von Modellinformationen bleibt möglich.
- API-Router filtern Listen bereits bei der Abfrage und prüfen Einzelobjekte
  erneut. Das Frontend verbessert die Bedienung, ersetzt diese Prüfungen aber
  nicht.

Codeanalyse kann zusätzlich pro Projekt für den allgemeinen Kontext
freigegeben werden. Dieses Opt-in erweitert weder Team- noch
Projektberechtigungen; es steuert nur, in welchem Kontext zugänglicher
Codeanalyse-Inhalt angezeigt werden darf.

## Benutzeroberfläche und API

Globale Administratoren verwalten Teams und Teammitgliedschaften über den
Teams-Tab. Im Projekte-Tab können Projekt-Admins Mitglieder aus dem eigenen
Team verwalten und offene Anfragen entscheiden. Teammitglieder sehen
entdeckbare, aber noch nicht beigetretene Projekte und können eine Anfrage
stellen. Die Oberfläche bezieht die Kandidatenliste projektbezogen; sie greift
nicht auf die globale Nutzerverwaltung zurück.

Die maßgeblichen APIs liegen in `backend/api/teams.py`,
`backend/api/users.py` und `backend/api/projects.py`; die UI-Anbindung liegt
in den Settings-Tabs des Frontends.

## Verifikation und offene Weiterentwicklung

`backend/tests/test_teams.py`, `backend/tests/test_teams_helper.py`,
`backend/tests/test_project_membership.py` und
`backend/tests/test_knowledge_sources.py` decken die zentralen Verwaltungs-,
Sichtbarkeits-, Quellen- und Anfrageregeln ab. O-013 ist technisch umgesetzt;
eine separate fachliche Freigabe der Rollenregeln bleibt davon unberührt.
