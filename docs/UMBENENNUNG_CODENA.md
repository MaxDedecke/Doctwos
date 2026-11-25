# Umbenennung der technischen Bezeichner: doctus → codena

Stand 25.11.2026, umgesetzt. Grundlage: Entscheidung E-21 (Produktname Codena). Sichtbare Texte und Doku sind bereits umgestellt;
dieses Dokument regelt die technischen Bezeichner und den Übergang bestehender Installationen (lokale Entwicklung,
Testserver, Pilot `pilot-20261124`).

Leitlinie: **Neue Namen überall, alte Namen werden während der Übergangszeit weiter gelesen.** Nichts, was eine
Installation gespeichert hat (Daten, Modelle, Einstellungen, Sitzungen, CI-Variablen), darf durch die Umbenennung
verloren gehen oder still ins Leere laufen.

## 1. Ohne Übergang (nur im Code)

Diese Bezeichner leben nur im Quelltext oder zur Laufzeit eines Prozesses und werden einfach umbenannt:

| Bereich | alt | neu |
| --- | --- | --- |
| Gemeinsames Modellpaket | `packages/doctus-models`, Import `doctus_models`, Distribution `doctus-models` | `packages/codena-models`, `codena_models`, `codena-models` (Version 2.0.0) |
| Frontend-Interna | CSS-Klassen `doctus-*`, Event `doctus:unauthorized`, postMessage `doctus-web-link`, Mermaid-IDs | `codena-*` |
| Webansicht | `data-doctus-url`, `data-doctus-source` (werden je Abruf erzeugt) | `data-codena-*` |
| Redis-Schlüssel | `doctus:inference:v1:*` (Zulassungszähler, flüchtig) | `codena:inference:v1:*` |
| Grammatikmarker | `// Doctus:` in `Cobol85.g4` | `// Codena:` |
| Testdaten, Beispiel-Domains | `doctus.local`, `doctus.example.com`, Keycloak-Testrealm `doctus` | `codena.*`, Realm `codena` |
| Dateinamen | `produkthandbuch-doctus.*`, `docs/assets/doctus_bilder`, Keycloak-Testrealm-Datei | `codena`-Varianten |
| Maven-Ausgabeordner | `target/doctus-ci/` | `target/codena-ci/` |

Alembic-Revisionen behalten ihre IDs und Dateinamen (`0001_doctus_baseline.py`); geändert werden nur ihre Importe.

## 2. Mit Rückfall auf den alten Namen

| Bereich | neu | Übergang |
| --- | --- | --- |
| Umgebungsvariablen | `CODENA_*` | Ist nur `DOCTUS_X` gesetzt, gilt sie als `CODENA_X` (Python: `codena_models.env_compat`, beim Import des Pakets; eigenständige Skripte und Deployer lesen beide Namen; Compose: `${CODENA_X:-${DOCTUS_X:-…}}`). Beim Start wird je alter Variable ein Hinweis geloggt. |
| Sitzungs-Cookie | `codena_session` | Backend akzeptiert `doctus_session` weiter und setzt beim nächsten Antworten das neue Cookie; Abmelden löscht beide. Niemand wird durch das Update abgemeldet. |
| Browser-Speicher | localStorage `codena-*`, Cookie `codena-theme` | Beim ersten Laden kopiert der Browser jeden Schlüssel `doctus-*` nach `codena-*`, sofern noch nicht vorhanden (Theme, Sprache, KI-Profile, Editor- und Graph-Einstellungen bleiben erhalten). |
| IDE-Erweiterung | Erweiterung `codena.codena-ide`, Befehle und Einstellungen `codena.*` | Einstellungen werden bei fehlendem neuen Wert aus `doctus.*` gelesen. Die Erweiterung hat eine neue Kennung: alte Erweiterung deinstallieren, das persönliche Token einmal neu eingeben (der Secret Storage gehört je Erweiterung). |
| CI-Anbindung | `CODENA_URL`, `CODENA_CI_TOKEN`, `CODENA_SOURCE_ID` …, Action `.github/actions/maven-codena` | `publish_maven_ci.py` liest weiter die `DOCTUS_*`-Namen; `.github/actions/maven-doctus` bleibt als gleichlautende Kopie. Bestehende Pipelines laufen ohne Änderung. |
| Language Server | `ide/codena_lsp.py`, `CODENA_*` | `ide/doctus_lsp.py` startet den neuen Server; `DOCTUS_*` gelten weiter. |
| Deployer | Label `codena.*`, Containerpräfix `codena-llm-` | Bereits laufende Modellcontainer mit Label `doctus.*` werden weiter erkannt, verwaltet und ins aktuelle Compose-Netz gehängt. |

## 3. Compose und Deployment

| Bereich | alt | neu |
| --- | --- | --- |
| Compose-Projekt | `name: doctus` | `name: codena` |
| Container | `doctus-db`, `doctus-backend`, … | `codena-db`, `codena-backend`, … |
| Images | `doctus-backend-api`, `doctus-parser-worker`, `doctus-frontend`, `doctus-deployer`, Offline: `doctus-db`, `doctus-redis`, `doctus-ollama` | `codena-*` |
| Versionsvariable | `DOCTUS_VERSION` | `CODENA_VERSION` (Rückfall auf `DOCTUS_VERSION`) |
| Offline-Bundle | `doctus-offline-bundle-*` | `codena-offline-bundle-*` |
| Logpfad im Container | `/var/log/doctus` | `/var/log/codena` (Host-Pfad `./data/logs` unverändert) |

**Bleibt bewusst:**

- Daten liegen als Bind-Mount unter `./data/` (Postgres, Logs) und sind vom Projektnamen unabhängig.
- Das Modellvolume behält seinen festen Namen `doctus_llm_models`, damit geladene Modelle (zig GB) nicht neu geladen
  werden. Neue Installationen erhalten denselben Namen; er ist nur intern sichtbar.
- Datenbankname und -nutzer kommen aus `.env` (`POSTGRES_DB`). Bestehende Installationen behalten `doctus`;
  `.env.example` schlägt für neue Installationen `codena` vor. Eine Umbenennung der Datenbank ist nicht nötig.
- MCP-Tokenpräfix `dct_mcp_` bleibt, sonst wären alle ausgegebenen Tokens ungültig.
- Signatur-Salts (`doctus-session`, `doctus-oidc-state`, `doctus-web-asset`) bleiben, sonst wären alle Sitzungen und
  signierten Links ungültig. Sie sind nirgends sichtbar.
- Alembic-Revisions-IDs (`0001_doctus_baseline` …) stehen in jeder Datenbank und bleiben.
- Standardpfad des beobachteten Ordners `/tmp/doctus-watched` (nur ohne `WATCHED_FOLDER` in `.env`) bleibt, damit
  ein Ordner-Konnektor nach dem Update nicht still einen leeren Ordner sieht.

**Update einer bestehenden Installation** (einmalig, Daten bleiben erhalten):

```bash
docker compose -p doctus down          # alte Container (Projekt doctus) stoppen, Daten in ./data bleiben
# Images neu laden (Offline-Bundle) bzw. bauen
docker compose up -d                   # startet Projekt codena mit denselben Daten
docker image prune                     # optional: alte doctus-* Images entfernen
```

`install-offline.sh` erledigt den ersten Schritt selbst, wenn es noch Container des Projekts `doctus` findet. Ohne
diesen Schritt laufen alte und neue Container parallel und kollidieren an den Ports 3000/8000.

Vom Deployer gestartete Modellcontainer (`doctus-llm-*`) laufen weiter; der Deployer hängt sie beim ersten Abruf ins
neue Netz `codena_default`, KI-Profile mit `http://doctus-llm-…` gelten weiter als verwaltet. Ein neues Deployment
mit dem Namen eines alten Containers wird abgelehnt.

Bei einer Installation aus dem Repository (lokal, Testserver) gilt dasselbe von Hand:
`docker compose -p doctus down`, danach `docker compose build` und `docker compose up -d`. `DOCTUS_VERSION` in einer
bestehenden `.env` wirkt weiter, bis sie in `CODENA_VERSION` umbenannt wird.

## 4. Rückfall entfernen

Frühestens, wenn alle Installationen (lokal, Testserver, Pilot) auf einer Version mit diesem Übergang laufen und deren
`.env`/CI-Variablen umgestellt sind: `DOCTUS_*`-Rückfall, Cookie-Rückfall, localStorage- und IDE-Übernahme entfernen.
Bis dahin bleibt jeder Rückfall mit einem Kommentar `Übergang doctus→codena` markiert (`grep -rn "Übergang doctus"`).

## Nicht Teil dieser Umbenennung

- Name des Git-Repositorys und des Arbeitsverzeichnisses.
- Historische Belege (Pitch-Unterlagen, Eval- und Benchmark-Ergebnisse) und Ordner außerhalb des Repos
  (`~/doctus-berichte`).
