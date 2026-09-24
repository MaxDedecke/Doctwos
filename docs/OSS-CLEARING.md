# Doctus — Lizenz-/Provenienzbericht (NF-003, AP-9)

Release-Voraussetzung für alle Bestandteile, die im Betrieb tatsächlich
ausgeliefert werden: Python-
(Backend, Parser), Node-Abhängigkeiten (Frontend), Container-Basisimages und
die beiden Ollama-Modelle. Wird laufend über die CI-Jobs `licenses` (Code)
gepflegt — für die Container-Images und Modelle ist die Prüfung manuell und
muss vor jedem Release wiederholt werden (siehe Abschnitt „Nicht automatisch
geprüft" unten).

Wichtig für die Interpretation eines externen Scanners: Die Allowlist und die
Ausnahmelisten definieren die Doctus-Freigabepolitik, sie behaupten nicht, dass
ein Scanner keinerlei Lizenzbefund ausgeben wird. LGPL-, MPL- und CC-BY-Artefakte
bleiben bei einer strengen „nur MIT/BSD/Apache"-Richtlinie sichtbare Treffer,
werden hier aber als begründete, nicht blockierende Ausnahmen behandelt. Ein
Clearing mit dieser Policy kann daher grün sein, obwohl ein Rohscan Treffer
meldet.

Der Bericht ist außerdem kein Open-Source-Lizenzhinweis für Doctus selbst:
Das eigene Projekt ist laut `README.md` „All rights reserved". Für eine
Weitergabe braucht Doctus daher zusätzlich eine eigene Nutzungs-/Lieferlizenz.

**Regel (CLAUDE.md):** strikt Open Source, nur MIT/BSD/Apache-2.0. Jede
Abhängigkeit mit abweichender Lizenz braucht eine benannte, begründete
Ausnahme hier **und** in `scripts/license_exceptions_python.json` /
`scripts/license_exceptions_node.json`.

**Stand 31.07.2026:** Ein Fund (`Unidecode`, GPL-2.0-or-later, transitiv über
`mcp-atlassian`) verstieß gegen diese Regel und war nicht freigegeben, CI-Job
`licenses` bewusst rot. **Update 08.08.2026: gelöst.** Ein MIT-lizenziertes
Shim-Paket (`backend/vendor/unidecode_shim/`) ersetzt die GPL-Abhängigkeit
vollständig — `mcp-atlassian` selbst bleibt unverändert, die eine Funktion,
die es aus `Unidecode` nutzt, wurde unter MIT nachgebaut. `licenses` ist
seitdem grün, kein Release-Blocker mehr. Details: `docs/ENTSCHEIDUNGEN.md`
E-7, `backend/vendor/unidecode_shim/README.md`.

---

## 1. Python — Backend (`backend/requirements.txt`)

O-324 pins the already transitively installed official `mcp==1.29.0` SDK
directly for the inbound server. Its package license is MIT. The implementation
uses the bundled `mcp.server.fastmcp` module; it does not add a standalone
FastMCP upgrade or the `orjson`/`pathspec` dependencies deferred in O-158.

Geprüft mit `pip-licenses` gegen `scripts/license_allowlist_python.txt`
(alle MIT-/BSD-/Apache-2.0-Varianten plus PSF-2.0 und Unlicense/Public
Domain, wie sie pip-licenses tatsächlich meldet). 143 installierte Pakete
(inkl. transitiver Abhängigkeiten), davon drei Ausnahmen (Stand 08.08.2026,
nach der E-7-Lösung — vorher vier, siehe unten):

| Paket | Lizenz | Status | Begründung |
|---|---|---|---|
| `psycopg2-binary` | LGPL-3.0-or-later | akzeptiert | Reiner DB-Treiber, unverändert, dynamisch verlinkt — keine Copyleft-Pflicht für Doctus selbst. Seit AP-0 gesetzt. |
| `certifi` | MPL-2.0 | akzeptiert | Transitiv über `httpx`/`requests` (CA-Bundle). Datei-basierte Weak-Copyleft-Lizenz, unverändert eingebunden, De-facto-Standardabhängigkeit im Python-Ökosystem. |
| `mcp-atlassian` | von pip-licenses als „UNKNOWN" gemeldet | akzeptiert | PyPI-Metadaten tragen keinen License-Classifier. Tatsächliche Lizenz laut Quell-Repo (`github.com/sooperset/mcp-atlassian/blob/main/LICENSE`, geprüft 31.07.2026): **MIT**. Nur eine Metadatenlücke beim Upstream-Projekt, kein Verstoß. |

`Unidecode` (GPL-2.0-or-later, transitive Pflichtabhängigkeit von
`mcp-atlassian`) stand bis 08.08.2026 hier als nicht freigegebener,
blockierender Fund. Gelöst durch `backend/vendor/unidecode_shim/` — ein
MIT-lizenziertes Paket, das sich selbst als `unidecode` deklariert, sodass
`pip` `mcp-atlassian`s `unidecode>=1.3.0`-Anforderung dagegen auflöst statt
das echte PyPI-Paket zu laden. `pip-licenses` meldet seitdem `unidecode`/MIT
(Teil der normalen Allowlist, keine Ausnahme mehr nötig). Details:
`docs/ENTSCHEIDUNGEN.md` E-7, `backend/vendor/unidecode_shim/README.md`.

Alle übrigen 140 Pakete tragen eine erlaubte Lizenz (MIT/BSD/Apache-2.0 oder
gleichwertige Varianten wie `MIT-0`, `MIT-CMU`, `PSF-2.0`, `The Unlicense`).

## 2. Python — Parser (`parser/requirements.txt`)

Gleiche Prüfung, 57 installierte Pakete. Zwei Ausnahmen, beide bereits oben
begründet und hier ebenfalls akzeptiert: `psycopg2-binary` (LGPL-3.0),
`certifi` (MPL-2.0). `mcp-atlassian`/`unidecode` sind hier **nicht**
installiert — der Parser-Service braucht keinen Confluence-/Jira-Client.

### Python-Entwicklungswerkzeuge (O-064, 06.09.2026)

| Paket | Version | Lizenz | Herkunft / Verwendung |
|---|---|---|---|
| `ruff` | `0.16.6` | MIT | [Astral / Ruff](https://github.com/astral-sh/ruff), [Release auf PyPI](https://pypi.org/project/ruff/0.16.6/). `License-Expression: MIT` in den installierten Wheel-Metadaten geprüft. Gepinnt in `requirements-lint.txt`; ausschließlich lokales Entwicklungswerkzeug und CI-Job `python-quality`, keine Installation über die Runtime-Requirements. |

Ruff erfüllt die reguläre Lizenz-Allowlist; keine Ausnahme erforderlich.
Die Runtime-Lizenzprüfung bleibt auf die ausgelieferten Abhängigkeiten begrenzt.

## 3. Node — Frontend (`frontend/package.json`, nur `dependencies`)

Geprüft mit `license-checker --production` gegen
`scripts/license_allowlist_node.txt`. 325 Pakete (05.09.2026: `@tanstack/react-virtual`
+ `@tanstack/virtual-core` für O-036 hinzugekommen, beide MIT, keine neue
Ausnahme nötig), vier Ausnahmen:

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

## 6. Grammatik-Provenienz (E-11 — Spike Phase 1, seit Phase 3 produktiv)

`antlr4-python3-runtime` ist seit Phase 3 (E-11) eine reguläre Laufzeit-
Abhängigkeit in `parser/requirements.txt` — läuft also mit durch
`scripts/check_licenses_python.py`/CI-Job `licenses` wie jedes andere Paket.
Dieser Abschnitt bleibt trotzdem bestehen, weil die Grammatik selbst
(`Cobol85.g4`/`Cobol85Preprocessor.g4`) eine **separate** Lizenzquelle ist,
die kein automatisierter `pip-licenses`-Lauf erfasst — nur die generierten
`.py`-Dateien unter `parser/cobol/_antlr/` sind aus ihr abgeleitet, nicht das
Pip-Paket selbst.

| Artefakt | Lizenz | Quelle |
|---|---|---|
| `antlr4-python3-runtime==4.13.2` | BSD-3-Clause | PyPI, `parser/requirements.txt` — läuft automatisiert über CI-Job `licenses`. |
| `Cobol85.g4` / `Cobol85Preprocessor.g4` (Quelle für `parser/cobol/_antlr/*.py`, generiert zur Entwicklungszeit, committet wie normaler Code) | MIT | `github.com/antlr/grammars-v4`, Pfad `cobol85/`, gepinnter Commit `e1c222f3f0e7c1b2fec799e94e34fc388b03f887` (2026-08-08), Kopie unter `parser/cobol/grammar/` (O-065: am 06.09.2026 byte-identisch aus dem entfernten Spike verschoben). Grammatik-Header verweist auf `github.com/uwol/cobol85parser` als Ursprung; dessen `LICENSE`-Datei (MIT, Copyright (c) 2017 Ulrich Wolffgang) am 11.08.2026 direkt eingesehen und als `parser/cobol/grammar/LICENSE-upstream-cobol85parser` mitgeführt — `grammars-v4` selbst hat kein Root-`LICENSE`, das den Cobol85-Grammatikordner abdeckt, deshalb Verifikation direkt an der Quelle statt Annahme. |

Beide MIT/BSD-3-Clause, kompatibel mit Architekturprinzip 2. Ergebnis auch in
`docs/ENTSCHEIDUNGEN.md` E-11 referenziert.

## 7. Java-Grammatik und Release-Artefakte

Die Java-Quellgrammatik stammt aus
`antlr/grammars-v4/java/java` und ist auf den Commit
`20efa537586610f5aebd584429ac1b5993a30381` gepinnt. `JavaLexer.g4` und
`JavaParser.g4` tragen den BSD-3-Clause-Lizenztext; die mitgeführte Kopie der
Lizenz liegt unter `parser/java/LICENSE-upstream-grammars-v4-java`. Herkunft,
Sprachstand und Regenerierung sind zusätzlich in
`parser/java/grammar/README.md` festgehalten.

Die eingecheckten Dateien unter `parser/java/_antlr/` sind daraus abgeleitete
Python-Artefakte. Die ANTLR-Generierung ist ein Build-/Entwicklungsschritt und
kein Bestandteil der Produktions-Runtime. Für eine nachvollziehbare Änderung
müssen Grammatik-Pin, Lizenzkopie, generierte Dateien und Java-Golden-Korpus
gemeinsam geprüft werden.

Offline-Regenerierung ist möglich, wenn das ANTLR-4.13.2-Complete-JAR bereits
lokal vorliegt:

```bash
cd parser
ANTLR_JAR=/path/to/antlr-4.13.2-complete.jar ./java/generate_parser.sh
PYTHONPATH=. python tests/update_java_goldens.py
python -m pytest tests/test_java_antlr_bridge.py tests/test_java_golden.py -q
```

Der Vorgang benötigt keine Netzverbindung. Ein Release darf nicht aus einer
unversionierten oder spontan aus dem Internet geladenen Grammatik regeneriert
werden. Änderungen an der Upstream-Revision brauchen einen neuen Provenienz-
und Lizenznachtrag.

Die Produktions- und Offline-Images enthalten weder `tests/`,
`requirements-dev.txt` noch das ANTLR-Generator-JAR. Das Parser-Dev-Target ist
nur über den Test-/Entwicklungsdienst in `docker-compose.dev.yml` verfügbar
(`--profile test`) und wird nicht in `docker-compose.offline.yml` gestartet.
Damit bleibt der ausgelieferte Runtime-Inhalt auf die benötigten Parser- und
Runtime-Abhängigkeiten begrenzt.

---

## Nicht automatisch geprüft (manueller Nachzug vor jedem Release)

- **Security-Advisories der Node-Abhängigkeiten**: Der Lizenzscan ist kein
  Vulnerability-Scan. Beim T5.4-Lauf am 16.09.2026 meldete `npm audit
  --omit=dev` eine kritische Next.js- und eine hohe `sharp`-Vulnerability;
  npm bot ein Update auf `next@16.3.5` außerhalb des aktuellen deklarativen
  Versionsbereichs an. Vor produktiver Auslieferung separat bewerten und
  testen.

- **Container-Basisimages**: keine automatisierte Lizenzprüfung der
  Image-Inhalte (nur der oben dokumentierte manuelle Check). Ein
  `syft`/`grype`-SBOM-Lauf gegen die gebauten Images wäre der nächste
  Ausbauschritt. Ein Rohscan der Distribution-Basis und der darin enthaltenen
  Systembibliotheken kann zusätzliche LGPL-/GPL-Befunde liefern; bis dieser
  Lauf erfolgt ist, gibt es dafür keinen vollständigen „keine Treffer"-Nachweis.
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
