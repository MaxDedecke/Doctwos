# Doctus – Arbeitsleitlinie

Stand: 26.10.2026 · gilt ab 27.10.2026 bis zum Start eines Pilotkunden.

Diese Datei ist die **zentrale Arbeitsleitlinie**. Sie steht über `docs/TODO.md`: Wo die Reihenfolge dort
abweicht, gilt diese Datei. Grundlage ist die Schwachstellenanalyse vom 26.10.2026
(`~/doctus-berichte/doctus_schwachstellenanalyse_2026-10-26.html`, außerhalb des Repos).

Ziel: Die Befunde mit hoher Schwere schließen oder messbar machen, bevor neue Funktionen entstehen.

---

## 1. Dauerhafte Regeln

Diese Regeln gelten für Menschen und KI-Agenten gleichermaßen. Ein Agent, der einen Auftrag erhält, der gegen
eine Regel verstößt, weist darauf hin und fragt nach, bevor er beginnt.

1. **Feature-Stopp.** Keine neuen Ansichten, Konnektoren, Sprachen, MCP-Werkzeuge oder Deployment-Varianten.
   Erlaubt ist nur Arbeit, die einen Punkt aus Abschnitt 2 oder 3 schließt, ein Sicherheitsproblem behebt oder
   von einem Pilotkunden ausdrücklich verlangt wird.
2. **Grün vor neu.** Ist ein CI-Job rot, wird zuerst er repariert. Kein Commit, der einen roten Job hinterlässt.
3. **Qualität nur am Hold-out-Satz belegen.** Aussagen wie „Antwortqualität verbessert“ gelten nur mit einer Messung
   am eingefrorenen Hold-out-Fragensatz (Abschnitt 2, Tag 3). Entwicklungsfragen (`backend/tests/fixtures/eval_*`)
   sind Regressionstests, kein Qualitätsbeleg.
4. **Keine unbelegten Zahlen nach außen.** Was in README, Pitch oder Handbuch steht (z. B. „100-GB-Monorepos“),
   muss durch eine versionierte Messung gedeckt sein, sonst wird es gestrichen oder als Ziel formuliert.
5. **Große Dateien nicht vergrößern.** Dateien über 800 Zeilen und Funktionen über 150 Zeilen wachsen nicht weiter.
   Wer dort ändert, zieht mindestens den geänderten Teil in ein eigenes Modul heraus.
6. **Nichts mit Host-Root-Rechten im Standard-Stack.** Kein `docker.sock`, kein `privileged`, keine
   ungepinnten Images im Standard-Start.
7. **TODO bleibt kurz.** `docs/TODO.md` enthält höchstens 30 aktive Punkte. Alles andere wandert nach
   „Bewusst zurückgestellt“ oder wird gelöscht.
8. **Dokumentation folgt dem Code am selben Tag.** Wer eine Regel aus `CLAUDE.md` bricht oder ändert, passt
   `CLAUDE.md` im selben Commit an.

---

## 2. Wochenplan 27.10. – 02.11.2026

Jeder Tag endet mit grüner CI, Commit und Push auf `develop` und neu gebauten geänderten Containern.
Ein Tag gilt erst als erledigt, wenn alle „Fertig, wenn“-Punkte erfüllt sind. Was liegen bleibt, wird am
nächsten Morgen zuerst erledigt; der Plan verschiebt sich, er wird nicht übersprungen.

### Tag 1 · Di 27.10. – CI grün, ORM-Gleichstand, kritische Pakete

1. **ORM-Dateien angleichen.** `backend/models/database.py` (988 Zeilen) und `parser/models/database.py`
   (952 Zeilen) unterscheiden sich, u. a. in der Klasse `Insight`. Der CI-Job `model-sync` muss daher rot sein.
   - Mit `diff` jede Abweichung einzeln bewerten; maßgeblich ist der Stand, den die Alembic-Migrationen
     (`backend/alembic/versions/`) tatsächlich erzeugen.
   - Danach beide Dateien byte-identisch machen, auch `crypto_types.py`.
   - Parser-Tests laufen lassen: Der Parser nutzt dann ggf. Spalten, die er vorher nicht kannte.
2. **CI-Gesamtstatus herstellen.** Alle Jobs aus `.github/workflows/ci.yml` lokal nachstellen
   (`ruff check`, `ruff format --check`, `pytest` in `backend/` und `parser/`, Golden-Tests,
   `npx tsc --noEmit`, `npm run lint`, `npm run test`, Lizenzprüfung) und rote Jobs reparieren.
3. **O-388:** `next` 16.3.3 → ≥ 16.3.6 (kritisch), `axios` → ≥ 1.20.0, `pypdf` → ≥ 6.19.0; `fastmcp` nur,
   wenn `mcp-atlassian` kompatibel bleibt, sonst als eigener Punkt notieren.
4. **Dokumentationsdrift beheben:** In `CLAUDE.md` das Standardmodell korrigieren (`qwen3:8b` statt
   `mistral-nemo`) und Prinzip 3 („Keine zusätzlichen Services“) an die tatsächlichen Dienste
   (`link-worker`, `deployer`) anpassen.

**Fertig, wenn:** alle CI-Jobs grün sind; `diff` beider ORM-Dateien leer ist; `grype` die vier Pakete nicht mehr meldet.

### Tag 2 · Mi 28.10. – Host-Sicherheit und Images

1. **Deployer aus dem Standard-Stack nehmen.** `deployer` in `docker-compose.yml` hinter ein Compose-Profil
   (`profiles: ["deployer"]`) legen, sodass `docker compose up` ihn nicht startet. Backend und Frontend müssen
   ohne Deployer fehlerfrei laufen; die UI zeigt „lokale Deployments nicht aktiviert“ statt eines Fehlers.
2. **Risiko dokumentieren.** In `docs/DEPLOYMENT.md` klar benennen: Mit dem Profil `deployer` erhält ein
   Container Zugriff auf `docker.sock` und damit Root-Rechte auf dem Host. Einen eingeschränkten Socket-Proxy
   nur nach OSS-Prüfung einführen (als TODO, nicht diese Woche).
3. **Alle Images per Digest pinnen:** `VLLM_IMAGE`, `LLAMACPP_IMAGE`, `LLAMACPP_CUDA_IMAGE` und jedes weitere
   `:latest` ohne `@sha256:` in Compose-Dateien und `.env.example`.
4. **O-389** (Frontend-Image ohne `devDependencies`) und **O-390** (Python-Basisimage ≥ 3.11.17,
   `setuptools` aktualisieren).
5. `scripts/sbom-scan.sh` erneut ausführen und den SBOM-Bericht in `~/doctus-berichte/` nachziehen.

**Fertig, wenn:** `docker compose up -d` keinen Container mit `docker.sock` startet; `grep -n ':latest' docker-compose*.yml`
nur noch Zeilen mit Digest liefert; der SBOM-Bericht die Funde aus O-389/O-390 nicht mehr enthält.

### Tag 3 · Do 29.10. – Ehrliche Messbasis

1. **Hold-out-Fragensatz v1 anlegen**, und zwar **außerhalb des Repos** unter `~/doctus-holdout/v1/`, damit
   Coding-Agenten ihn beim Entwickeln nicht sehen und Doctus nicht auf ihn hin optimiert wird.
   - 40 Fragen: 20 zu AWS CardDemo (COBOL), 20 zu Apache Syncope (Java).
   - Keine Frage darf einer Frage aus `backend/tests/fixtures/eval_*` oder den bisherigen Benchmark-Kapiteln ähneln.
   - Je Frage: Fragetext, Typ (Aufrufer, Datenherkunft, Copybook/Import, Ablauf, Fachregel, Negativfall),
     Pflichtfakten mit `datei:zeile`, verbotene Aussagen (bekannte Halluzinationsmuster aus O-346).
   - Mindestens 6 Negativfälle, bei denen die richtige Antwort „nicht im Bestand belegt“ lautet.
   - Nach Fertigstellung den SHA-256 der Datei notieren; danach wird sie nicht mehr geändert (Änderung = v2).
2. **Bewertung zweigleisig:** `scripts/eval_chat.py` um `--cases <pfad>` erweitern. Bewertet wird
   (a) per Pflichtfakten-Rubrik und (b) durch einen LLM-Prüfer, der die Antworten **anonymisiert und gemischt**
   erhält und nicht weiß, welche Variante er bewertet. Abweichungen > 20 Prozentpunkte zwischen (a) und (b)
   werden von Hand nachgesehen.
3. **Temperatur für Recherche senken.** Die vier Rückfallwerte `0.7` in `backend/agent.py` durch eine einzige
   Konstante ersetzen (Standard 0.1), die nur greift, wenn weder Anfrage noch Profil (`llm_temperature`) einen
   Wert setzen. Das ist zugleich der erste Schritt zur Vereinheitlichung der Agentenschleife.
   **Umgesetzt 28.10.2026 mit Abweichung:** eine Konstante `core/config.py::DEFAULT_CHAT_TEMPERATURE = 0.2`
   für Agent und Standard-RAG statt 0.1. Begründung: Qwen3 rät von nahezu deterministischem Sampling ab
   (Wiederholungsschleifen, schlechtere Antworten) und empfiehlt im Denkmodus 0.6; das Profil
   „Lokal Qwen3 8B“ trägt deshalb `llm_temperature = 0.6`. Zuvor galt der Profilwert nie, weil das Frontend
   immer `0.7` mitschickte; es sendet jetzt nur noch eine im Browserprofil gesetzte Temperatur.
   Offen: Hold-out-Vergleich `qwen3:8b` bei 0.2 und 0.6 (je 3 Läufe: nutzbare und leere Antworten, Streuung).

**Fertig, wenn:** `~/doctus-holdout/v1/` mit 40 Fragen und notiertem Hash existiert; ein Probelauf mit
`qwen3:8b` über 5 Fragen beide Bewertungen erzeugt; nur noch eine Temperaturkonstante in `agent.py` steht.

### Tag 4 · Fr 30.10. – Mindestmodell entscheiden

1. RunPod-Endpunkt nach `docs/EVALRUN_1.md` bereitstellen, Modelle `qwen3:32b` und – zum Vergleich – ein
   Coder-Modell der 32B-Klasse laden. Embedding-Profil unverändert lassen (kein Reindex).
2. Hold-out v1 laufen lassen: Varianten `qwen3:8b` lokal, 32B-Modell(e) remote; je Variante Agent- und
   Chat-Betrieb; 3 Wiederholungen.
3. Ergebnis als **eine HTML-Datei** in `~/doctus-berichte/` (Qualität, nutzbare Antworten ≥ 50 %, Halluzinationen
   in Negativfällen, Zeit, Tokens). Keine Logs oder Rohdaten im Repo.
4. **Entscheidung E-17 „Mindestmodellklasse“** in `docs/ENTSCHEIDUNGEN.md` festhalten: welches Modell als
   Produktvoraussetzung gilt, welche GPU dafür nötig ist und dass `qwen3:8b` nur als Demo-/Notbetrieb ausgewiesen wird.
   Die UI zeigt beim 8B-Modell einen entsprechenden Hinweis (kleine Änderung, kein neues Feature).

**Fertig, wenn:** HTML-Bericht liegt vor; E-17 ist geschrieben; README und Handbuch nennen die Mindestmodellklasse.

### Tag 5 · Mo 02.11. – Skalierung belegen, Pilot anstoßen, aufräumen

1. **Lasttest.** Mit `scripts/generate_synthetic_cobol_corpus.py` einen Korpus mit **mindestens 5 Mio. Zeilen**
   erzeugen (`--programs` entsprechend erhöhen, `--seed 42`) und mit `scripts/loadtest_ingest_synthetic_corpus.py`
   importieren. Messen: Dauer von Parsen, Persistenz, Linking und Embedding-Stichprobe, DB-Größe, Antwortzeit von
   Call-Graph-Abfragen mit 3 Hops. Ergebnis als HTML in `~/doctus-berichte/`.
   README-Aussagen zur Skalierung an das Messergebnis anpassen (Regel 4).
2. **Pilot anstoßen (Nicht-Code, wichtigster Punkt der Woche).** Einen einseitigen Pilotsteckbrief erstellen:
   Problem, Umfang (ein Bestand, 4 Wochen), Erfolgskriterien (aus O-278: Einarbeitungszeit, Fehleranalysezeit),
   Hardware (aus E-17), Datenschutz/On-Prem. Mindestens **drei konkrete Ansprechpartner** im Fujitsu-Umfeld
   anschreiben, bevorzugt mit BS2000- oder Rechenzentralen-Bestand.
3. **TODO kürzen** auf ≤ 30 aktive Punkte (Regel 7). Punkte, die nur ein Kunde auslösen kann, gesammelt unter
   „Wartet auf Pilot“ zusammenfassen.

**Fertig, wenn:** Lasttestbericht liegt vor und README ist angepasst; drei Anfragen sind verschickt;
`docs/TODO.md` hat ≤ 30 aktive Punkte.

---

## 3. Danach (Wochen 2–4) – nicht in Woche 1 beginnen

In dieser Reihenfolge, jeweils mit Messung am Hold-out-Satz vorher und nachher:

| # | Vorhaben | Befund, der damit schließt |
|---:|---|---|
| 1 | **Eine Agentenschleife** mit Adaptern je Anbieter statt vier Kopien in `backend/agent.py`. **Umgesetzt 28.10.2026** (`agent.py::_research_loop`, Adapter in `services/agent_providers.py`); Hold-out-Messung vorher/nachher steht aus. | Architektur: 4× Agentenschleife |
| 2 | **Belegpflicht strukturell:** Antwort als Liste von Aussagen mit Zitat-ID; Aussagen ohne gültige ID werden verworfen. Graphfragen (Aufrufer, Copybooks, Importe) deterministisch aus dem Index rendern. | KI: erfundene Kanten (O-346) |
| 3 | **Ein Antwortpfad:** immer Beweispaket vorab, Agent recherchiert nur bei gemeldeten Lücken nach. | KI: zwei Betriebsarten |
| 4 | **`POST /chat` zerlegen** in Kontext → Agent → Belegprüfung → Persistenz. **Umgesetzt 28.10.2026** (`services/chat_turn.py`, `chat_sources.py`, `chat_sessions.py`, `chat_feedback.py`, `chat_view_actions.py`). | Architektur: God-Handler |
| 5 | **UI-Kernfluss** Frage → Antwort → Originalstelle → Aufrufer; Nebenansichten (Tropfen, 3D-Graph, Topics) hinter „Erweitert“; Schrift ≥ 12 px; Kontrast ≥ 4,5:1 per axe-Test in CI; kontextbezogene Chat-Vorschläge statt rotierender Überschrift. | UI: Konzeptvielfalt, Typografie |
| 6 | **Gemeinsames Modellpaket** statt zweier ORM-Kopien. | Architektur: Duplikat |
| 7 | **Nischenentscheidung BS2000/openUTM** (O-131 bis O-133, O-144) als E-18 treffen – Ausbau nur mit Pilotbezug. | Zukunft: Nische liegt brach |
| 8 | **Zweite Person** mit Reviewrechten gewinnen; ab dann Merge auf `develop` nur mit Review. | Zukunft: Busfaktor 1 |

---

## 4. Wie die Bewertung messbar besser wird

| Befund (Schwere) | Gilt als behoben, wenn |
|---|---|
| ORM-Duplikat driftet (hoch) | CI-Job `model-sync` ist grün; ab Woche 3 gibt es nur noch ein Modellpaket. |
| Docker-Socket im Standard-Stack (hoch) | Standardstart enthält keinen Socket-Mount; alle Images gepinnt. |
| Lokales Standardmodell trägt nicht (hoch) | E-17 steht; das Mindestmodell erreicht am Hold-out ≥ 60 % nutzbare Antworten. |
| Erfundene Kanten/Quellen (hoch) | Bei Negativfällen und Aufruferfragen am Hold-out 0 erfundene Kanten in 3 Wiederholungen. |
| MCP-Mehrwert kaum messbar (hoch) | Hold-out-Lauf zeigt für Graph- und Datenherkunftsfragen einen Vorsprung ≥ 15 Prozentpunkte gegenüber reinem Dateizugriff mit demselben Modell. |
| Kein Pilot (hoch) | Ein unterschriebener oder terminierter Pilot. |
| Messbasis zu schmal (mittel) | Hold-out v1 eingefroren, zwei Bewertungen je Antwort. |
| Skalierung unbelegt (mittel) | Lasttest ≥ 5 Mio. Zeilen dokumentiert, README angepasst. |
| Dokumentationsdrift (mittel) | `CLAUDE.md` stimmt mit Compose und Standardmodell überein; TODO ≤ 30 aktive Punkte. |

Nach Woche 1 und nach Woche 4 wird die Schwachstellenanalyse neu erstellt und mit der vom 26.10.2026 verglichen.
