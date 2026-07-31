# Doctus — Lizenz-/Provenienzbericht (NF-003, AP-9)

Release-Voraussetzung laut `docs/IMPLEMENTIERUNGSPLAN.md` §12.4. Deckt alle
Bestandteile ab, die im Betrieb tatsächlich ausgeliefert werden: Python-
(Backend, Parser), Node-Abhängigkeiten (Frontend), Container-Basisimages und
die beiden Ollama-Modelle. Wird laufend über die CI-Jobs `licenses` (Code)
gepflegt — für die Container-Images und Modelle ist die Prüfung manuell und
muss vor jedem Release wiederholt werden (siehe Abschnitt „Nicht automatisch
geprüft" unten).

**Regel (CLAUDE.md):** strikt Open Source, nur MIT/BSD/Apache-2.0. Jede
Abhängigkeit mit abweichender Lizenz braucht eine benannte, begründete
Ausnahme hier **und** in `scripts/license_exceptions_python.json` /
`scripts/license_exceptions_node.json`.

**Stand 31.07.2026.** Ein Fund verstößt aktuell gegen diese Regel und ist
**nicht freigegeben** (siehe unten, `Unidecode`) — Entscheidung mit dem
Auftraggeber offen, siehe `docs/ENTSCHEIDUNGEN.md` E-7. Der CI-Job `licenses`
ist deshalb bewusst rot, bis diese Entscheidung getroffen ist.

---

## 1. Python — Backend (`backend/requirements.txt`)

Geprüft mit `pip-licenses` gegen `scripts/license_allowlist_python.txt`
(alle MIT-/BSD-/Apache-2.0-Varianten plus PSF-2.0 und Unlicense/Public
Domain, wie sie pip-licenses tatsächlich meldet). 143 installierte Pakete
(inkl. transitiver Abhängigkeiten), davon vier Ausnahmen:

| Paket | Lizenz | Status | Begründung |
|---|---|---|---|
| `psycopg2-binary` | LGPL-3.0-or-later | akzeptiert | Reiner DB-Treiber, unverändert, dynamisch verlinkt — keine Copyleft-Pflicht für Doctus selbst. Seit AP-0 gesetzt. |
| `certifi` | MPL-2.0 | akzeptiert | Transitiv über `httpx`/`requests` (CA-Bundle). Datei-basierte Weak-Copyleft-Lizenz, unverändert eingebunden, De-facto-Standardabhängigkeit im Python-Ökosystem. |
| `mcp-atlassian` | von pip-licenses als „UNKNOWN" gemeldet | akzeptiert | PyPI-Metadaten tragen keinen License-Classifier. Tatsächliche Lizenz laut Quell-Repo (`github.com/sooperset/mcp-atlassian/blob/main/LICENSE`, geprüft 31.07.2026): **MIT**. Nur eine Metadatenlücke beim Upstream-Projekt, kein Verstoß. |
| **`Unidecode`** | **GPL-2.0-or-later** | **NICHT freigegeben** | Transitive Pflichtabhängigkeit von `mcp-atlassian` (Confluence-/Jira-Konnektor, AP-3/AP-8) — steht nicht in `backend/requirements.txt`, wird aber automatisch mitinstalliert. Copyleft, verstößt gegen die „nur MIT/BSD/Apache-2.0"-Regel. Siehe `docs/ENTSCHEIDUNGEN.md` E-7 für Optionen und offene Entscheidung. |

Alle übrigen 139 Pakete tragen eine erlaubte Lizenz (MIT/BSD/Apache-2.0 oder
gleichwertige Varianten wie `MIT-0`, `MIT-CMU`, `PSF-2.0`, `The Unlicense`).

## 2. Python — Parser (`parser/requirements.txt`)

Gleiche Prüfung, 57 installierte Pakete. Zwei Ausnahmen, beide bereits oben
begründet und hier ebenfalls akzeptiert: `psycopg2-binary` (LGPL-3.0),
`certifi` (MPL-2.0). `mcp-atlassian`/`Unidecode` sind hier **nicht**
installiert — der Parser-Service braucht keinen Confluence-/Jira-Client.

## 3. Node — Frontend (`frontend/package.json`, nur `dependencies`)

Geprüft mit `license-checker --production` gegen
`scripts/license_allowlist_node.txt`. 323 Pakete, vier Ausnahmen:

| Paket | Lizenz | Status | Begründung |
|---|---|---|---|
| `@img/sharp-libvips-linux-x64`, `@img/sharp-libvips-linuxmusl-x64` | LGPL-3.0-or-later | akzeptiert | Natives Binärpaket von `sharp` (Next.js-Bildoptimierung), unverändert, als separater Prozess eingebunden — analog zu `psycopg2-binary`. |
| `caniuse-lite` | CC-BY-4.0 | akzeptiert | Reine Build-Zeit-Kompatibilitätsdaten (Browserslist/PostCSS), kein Code. Namensnennungspflicht ist mit diesem Eintrag erfüllt. |
| `doctus-frontend` | UNLICENSED | akzeptiert | Das eigene Paket selbst, keine Fremdabhängigkeit. |

`devDependencies` (Playwright, ESLint, Vitest u.a.) werden nicht ausgeliefert
und sind hier bewusst ausgenommen (`--production`).

## 4. Container-Basisimages (`docker-compose.yml`, digest-gepinnt)

| Image | Lizenz | Bemerkung |
|---|---|---|
| `ankane/pgvector` | PostgreSQL-Lizenz (Kern) + PostgreSQL-Lizenz (pgvector-Extension) | Beide permissiv, BSD-/MIT-äquivalent. |
| `valkey/valkey` | BSD-3-Clause | Bewusst statt Redis (seit dessen Lizenzwechsel auf SSPL/RSALv2) — siehe CLAUDE.md-Umgebungsabschnitt. |
| `ollama/ollama` | MIT | Server/CLI, nicht die Modelle selbst (siehe unten). |

Backend-, Parser- und Frontend-Images werden selbst gebaut (kein Basisimage
mit fremder Lizenz außer den o.g. Python-/Node-Abhängigkeiten).

## 5. Ollama-Modelle

| Modell | Lizenz | Quelle |
|---|---|---|
| `mistral-nemo` (Instruct) | Apache-2.0 | Mistral AI / NVIDIA, geprüft 31.07.2026 gegen die Modellkarte auf Hugging Face. |
| `bge-m3` (Embeddings) | MIT | BAAI, geprüft 31.07.2026 gegen die Modellkarte auf Hugging Face. |

Beide Modelllizenzen sind permissiv und erlauben On-Premise-Redistribution
im Offline-Bundle (NF-002) ohne Sonderklausel.

---

## Nicht automatisch geprüft (manueller Nachzug vor jedem Release)

- **Container-Basisimages**: keine automatisierte Lizenzprüfung der
  Image-Inhalte (nur der oben dokumentierte manuelle Check). Ein
  `syft`/`grype`-SBOM-Lauf gegen die gebauten Images wäre der nächste
  Ausbauschritt, ist aber kein MUSS laut Plan.
- **Modelllizenzen**: ändern sich mit jedem `OLLAMA_MODEL`-Wechsel in
  `.env` — bei Modellwechsel diesen Abschnitt manuell nachziehen.
- **Transitive Docker-Build-Werkzeuge** (z.B. `build-essential` im
  Parser-Image für Compile-Schritte) sind Betriebssystempakete der
  Basisdistribution, nicht Teil des ausgelieferten Codes — hier bewusst
  nicht erfasst.

## Werkzeuge

- `scripts/check_licenses_python.py` (+ `license_allowlist_python.txt` +
  `license_exceptions_python.json`) — CI-Job `licenses`, Schritte
  „Backend-/Parser-Abhängigkeiten prüfen".
- `scripts/check_licenses_node.mjs` (+ `license_allowlist_node.txt` +
  `license_exceptions_node.json`) — CI-Job `licenses`, Schritt
  „Frontend-Lizenzen prüfen".
- Neues Paket mit permissiver Lizenz, die pip-licenses/license-checker mit
  einem neuen String meldet → Allowlist ergänzen. Neues Paket mit
  Copyleft-/unklarer Lizenz → Ausnahmeliste **und** diesen Bericht ergänzen,
  nicht stillschweigend durchwinken.
