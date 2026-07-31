# Doctus — Umsetzungsstand

**Zuletzt aktualisiert:** 31.07.2026 (AP-7 begonnen — Job-Center umgesetzt)
**Referenz:** `docs/IMPLEMENTIERUNGSPLAN.md` (Arbeitspakete AP-0…AP-9) · Entscheidungen in `docs/ENTSCHEIDUNGEN.md`

Dieses Dokument ist die Einstiegsseite für jede neue Session: *Was ist fertig, was ist als
Nächstes dran, was ist bewusst offen.* Wer hier etwas erledigt, hakt es hier ab.

---

## Fortschritt nach Arbeitspaket

| AP | Inhalt | Stand |
|----|--------|-------|
| **AP-0** | Fork, Entkernung, Rename, Alembic-Baseline, Erststart | **fertig** (Erststart am 31.07. mit Docker abgenommen) |
| **AP-1** | Lokale Auth, User-Verwaltung, Bootstrap-Superuser | **fertig** (Tests grün, end-to-end abgenommen) |
| **AP-2** | COBOL-Parser + Testkorpus | **fertig** — alle zehn Module inkl. `parse.py` (`parse_program()`, In-Memory), Golden-File-Testkorpus (99_garbage.cbl, golden/*.json) + CI-Job `parser-golden` stehen (E-6 zur AP-2/AP-4-Grenze weiterhin gültig) |
| **AP-3** | Monorepo-Git-Konnektor, Multi-Branch, resumable Sync | **fertig** — Bare-Mirror + Worktree (`parser/git_utils.py`), resumable über `SourceScanFile` (NF-004), F-016-Dateiklassifikation |
| **AP-4** | Entity-/Kanten-Persistenz + Nachauflösung + Retrieval | **fertig** — Pass 0-2, quellenweite XREF-Vererbung, budgetiertes 1-Hop-Graph-Retrieval sowie `/entities`- und `/callgraph`-Router stehen und sind getestet |
| **AP-5** | Frontend: Panels, Fokus-Objekt, Referenzen-Menü, Zeilen-Chip | **fertig** — strukturierte Zeilenreferenz wird als Chip angezeigt, in `metadata_json.refs[]` persistiert und springt aus der Historie zurück in den Code |
| **AP-6** | Call-Graph-View + Export | **fertig** — Fokusgraph mit 1–3 Hops, Kantentyp-Filtern, Warnknoten für unresolved/dynamic, Code-Navigation und JSON/CSV/GraphML-Download |
| **AP-7** | Design-Tokens (Fujitsu), Job-Center, i18n | **in Arbeit** — Job-Center + de/en umgesetzt, Design-Tokens offen |
| **AP-8** | Konnektoren-Nachzug | offen |
| **AP-9** | Härtung: Lasttest, BITV, OSS-Clearing, Offline-Bundle | offen |

---

## AP-0 — was konkret passiert ist

**Fork.** Template `Condo-develop` (Commit 27789d4) vollständig nach `/root/Doctwos`
kopiert, ohne `.git`/`node_modules`.

**Entkernt (gelöscht):**
- Backend: `api/aec_workflows.py`, `api/regulations.py`, `app/agents/`, `core/oidc.py`,
  `services/ifc_reader.py`, `services/dxf_reader.py`
- Parser: `connectors/{ifc,dwg,gaeb,dalux,autodesk,notion}.py`,
  `tasks/{compliance,regulation_import}.py`
- Frontend: `BimCadViewer.tsx`, `ComplianceView.tsx`
- Betrieb: `.github/keycloak/`, `watched/`, AEC-/Businessplan-/Compliance-Dokumente,
  AEC-Seed- und Eval-Skripte unter `scripts/`
- Tests: alle Compliance-/IFC-/Cloud-CDE-Tests (siehe „Offene Punkte", Testabdeckung)

**Datenmodell (eine Baseline statt 32 Migrationen):**
`backend/alembic/versions/0001_doctus_baseline.py`
- `users`: `username` + `password_hash` (Argon2id) + `role`/`is_active`/
  `must_change_password`/`failed_login_count`/`locked_until` statt OIDC-`sub`
- `code_entities`: `parent_id`, `qualified_name`, `meta_json`, `content_hash`;
  `ifc_guid` entfallen
- `code_edges`: **neu**, inkl. `scope_entity_id` (siehe E-1)
- `source_scan_files`: **neu**, ersetzt `folder_/ifc_/dwg_/gaeb_scan_files`
- `knowledge_sources`: `branch`, `repo_fingerprint`, `sync_cursor`,
  `UNIQUE(project_id, url, branch)`
- entfallen: alle `compliance_*` und `regulation_*`
- HNSW-Index auf `document_chunks.embedding` (m=16, ef_construction=64) übernommen

**Auth (OIDC → lokal):**
- `backend/core/passwords.py` (neu): Argon2id, die einzige Stelle, die hasht/prüft
- `backend/api/auth.py` (neu): `POST /auth/login|logout|change-password`, `GET /auth/me`
- `backend/core/db_setup.py::bootstrap_superuser()`: legt beim ersten Start genau einen
  Superuser an; ohne `BOOTSTRAP_SUPERUSER_PASSWORD` wird eines generiert und einmalig
  ins Startlog geschrieben
- `is_admin()` prüft jetzt `role == 'superuser'` statt `ADMIN_EMAILS`
- Projekt-Rollen auf `admin`/`member` reduziert (`pruefingenieur` entfallen)
- Frontend: `LoginView.tsx` ist ein Formular (Benutzername/Passwort) mit
  erzwungenem Passwortwechsel als zweitem Schritt

**Rename & Betrieb:**
- `condo`→`doctus` über alle Dateien (Bezeichner, Container, Cookie, DB, Images)
- Keine Node.js-Runtime mehr im Backend-Image (F-049) — der einzige Bedarf war der
  Notion-MCP-Server
- Abhängigkeiten: `authlib`, `ifcopenshell`, `ezdxf` raus; `argon2-cffi` rein
- `.env.example`/`docker-compose*.yml`: OIDC-/`ADMIN_EMAILS`-Variablen raus,
  `BOOTSTRAP_SUPERUSER*` rein
- CI: Keycloak-Job entfällt, e2e läuft gegen die lokale Anmeldung; neuer Job
  `no-password-leak` (F-005)
- `config/features.json` auf COBOL/Git umgestellt

**Verifiziert:**
- `npx tsc --noEmit` — fehlerfrei
- `npm run test` (vitest) — 4/4 grün
- `python3 -m compileall backend parser` — fehlerfrei
- Keine offenen Referenzen mehr auf gelöschte Module (Import-Grep über beide Pakete)

---

## AP-1 — was konkret passiert ist

**Rate-Limit und Sperre (F-005).** `backend/core/login_throttle.py` (neu) hält den
Backoff: 5 Fehlversuche frei, ab dem 6. eine Sperre von 60 s mit Verdopplung je
weiterem Fehlversuch, gedeckelt bei 1 h. Zwei Zähler, der höhere gilt — Redis pro
(Benutzername, IP) mit 15-Minuten-Fenster, DB pro Nutzer als dauerhafte Sperre.
Begründung und Ausfallverhalten in E-5.

- `api/auth.py::login` prüft die Sperre **vor** dem Passwortvergleich und
  unabhängig davon, ob es den Benutzernamen gibt — sonst wäre am Sperrverhalten
  ablesbar, welche Konten existieren.
- Antwort bei Sperre: `423` mit `Retry-After`; `LoginView` zeigt daraus die
  Restzeit in der eingestellten Sprache an (`loginView.lockedFor`).
- Client-IP aus `X-Forwarded-For` (erster Eintrag) mit Rückfall auf die
  Socket-Adresse. Der Header ist fälschbar und bestimmt deshalb nur die
  Granularität des Zählers, nie eine Berechtigung.

**Nutzerverwaltung (F-004).** `backend/api/users.py` erweitert, alles
`superuser`-only:

```
GET   /users                       Liste inkl. is_active / is_locked / last_login_at
POST  /users                       anlegen; Startpasswort einmalig in der Antwort
PATCH /users/{id}                  Name, E-Mail, Rolle, aktiv/deaktiviert
POST  /users/{id}/reset-password   neues Startpasswort, hebt die Sperre mit auf
POST  /users/{id}/unlock           Sperre aufheben
```

Gelöscht wird nie (Nutzer hängen an Chatverläufen und Mitgliedschaften) —
`is_active=False` ist die Deaktivierung. Zwei Schutzgriffe gegen das
Sich-selbst-Aussperren: das eigene Konto lässt sich nicht deaktivieren oder
zurückstufen, und der letzte aktive Administrator ebenfalls nicht.

**Ein Provisioning-Pfad (Plan §11).** `backend/core/users.py` (neu) ist die einzige
Stelle, die Konten anlegt und Passwörter setzt; `api/users.py` und der Erststart in
`core/db_setup.py` rufen dort hinein. Ein späterer IdP-Anschluss ergänzt hier einen
zweiten Zweig. Der CI-Job `no-password-leak` erlaubt `password_hash` entsprechend in
`core/users.py` statt in `core/db_setup.py`.

**Frontend.** `UsersSettingsTab.tsx` (neu, Admin-only) im Einstellungs-Modal:
anlegen, Rolle wechseln, deaktivieren/aktivieren, Passwort zurücksetzen, entsperren.
Ein neu vergebenes Passwort steht in einem Hinweisfeld mit Kopieren-Knopf und ist
nach dem Schließen weg — es existiert nirgends sonst. i18n-Schlüssel in de/en ergänzt.

**Nebenbefund mitgenommen.** Der CI-Job `no-password-leak` war seit AP-0 rot: die
Kopfkommentare in `models/crypto_types.py` (beide Kopien) nannten das Feld beim
Namen und lösten den Grep aus. Umformuliert, beide Dateien weiterhin byte-identisch.

**Verifiziert:** `npx tsc --noEmit` fehlerfrei, `npm run test` 4/4 grün,
`python3 -m compileall backend parser` fehlerfrei, `no-password-leak`-Grep lokal
nachgestellt und leer. Die Backoff-Kurve wurde einzeln durchgerechnet
(6.→60 s, 7.→120 s, …, Deckel 3600 s).

---

## Abnahme-Session 31.07.2026 — Docker und pip nachgerüstet

Die Maschine hat jetzt Docker (Engine 29.7.0, Compose v5.3.1) und pip (24.0). Damit
war nachholbar, was seit AP-0 als „nicht verifizierbar" offen stand. Zwei Umgebungen
neben den Containern: `.venv` (backend/requirements-dev.txt) und `.venv-parser`
(parser/requirements-dev.txt), beide gitignored. Tests laufen wie in der CI mit
`python -m pytest tests/` aus dem jeweiligen Verzeichnis — der `pytest`-Aufruf ohne
`-m` findet die Pakete nicht.

### Baseline-Migration gegen eine echte DB — drei Befunde

`alembic upgrade head` gegen eine leere DB lief durch. Die Gegenprobe per
`alembic revision --autogenerate` war beim ersten Lauf **nicht** leer:

1. **`uq_team_memberships_user_team` fehlte in der Baseline** — echter Fehler. Das ORM
   deklariert die Constraint, die von Hand geschriebene Migration hatte sie vergessen.
   Ohne sie legt jeder wiederholte „Mitglied hinzufügen"-Klick eine zweite Zeile an.
   In der Baseline ergänzt.
2. **Die beiden `document_chunks`-Indizes standen nur in der Migration, nicht im ORM.**
   Autogenerate wollte sie folgerichtig löschen — ein stillschweigend entfernter
   HNSW-Index degradiert die Vektorsuche zum Full Scan, ohne Fehlermeldung. Beide sind
   jetzt in `DocumentChunk.__table_args__` deklariert (in beiden Modell-Kopien).
3. **`EncryptedString` erzeugte Scheindeltas** (TEXT → EncryptedString bei jedem Lauf).
   `alembic/env.py` vergleicht Typen jetzt über `TypeDecorator.impl` — sonst verrauscht
   genau die Prüfung, mit der man ein echtes Delta finden will.

Nach den Korrekturen: DB neu angelegt, `upgrade head`, Autogenerate — **Delta leer**.

### Testlauf

`backend`: 74 grün. Vorher gefunden und behoben:
- `test_users_admin.py` (aus AP-1): `client` und `unauthenticated_client` sind
  **dieselbe** TestClient-Instanz — `cookies.clear()` meldete auch den Admin ab.
  Jetzt über einen `as_nobody()`-Kontextmanager, der die Admin-Cookie zurücklegt.
- `test_mcp_client.py::test_notion_source…`: AP-0-Altlast. Notion ist mit AP-0
  entfallen (samt Node.js-Runtime im Backend-Image, F-049), der Test blieb liegen.
  Entfernt.
- `test_project_membership.py` (2 Tests): AP-0 hat `is_admin()` auf
  `role == 'superuser'` umgestellt — und der `client`-Fixture-Nutzer ist genau das.
  Damit sah er team-übergreifend alles und die beiden Team-Grenzen-Tests prüften
  nichts mehr. Neue Fixture `member_client` (gewöhnlicher Nutzer im Default Team),
  beide Tests laufen jetzt darüber.
- `config_router.py`: `FEATURES_CONFIG_PATH` wurde beim Import eingefroren, obwohl der
  Docstring „pro Request neu gelesen" verspricht. Pfad wird jetzt pro Request
  aufgelöst.
- `scripts/lib/env-bootstrap.sh` warnte weiterhin über leere `OIDC_*`-Variablen, die es
  seit AP-0 nicht mehr gibt. Entfernt.

`parser`: 15 grün.

Drei Tests (1 backend, 2 parser) brauchen einen erreichbaren Ollama mit `bge-m3`:
sie prüfen den Embedding-/Retrieval-Pfad. **Keiner der beiden CI-Jobs stellt einen
Ollama bereit** — diese drei sind dort also seit jeher rot, ererbt aus dem Template.
Sie tragen jetzt `@requires_ollama` (`conftest.py`, prüft `/api/tags`): lokal mit
laufendem Stack laufen sie, in der CI werden sie übersprungen statt fehlzuschlagen.
Ein dauerhaft roter Job wird nicht mehr gelesen — das ist die schlechtere Variante.
**Offene Entscheidung:** entweder einen `ollama`-Service in die beiden CI-Jobs
aufnehmen (Image + 1,2 GB Modell pro Lauf) oder es beim Überspringen belassen.

### Erststart-Abnahme (AP-0, war offen)

`./install.sh` gegen eine leere DB: Images gebaut, `docker compose up -d`, **alle
sieben Services healthy**, `GET /health` → `{"status":"healthy"}` mit
`database/redis/ollama = ok`, Frontend auf :3000 → HTTP 200. Der Erststart-Block mit
dem generierten Superuser-Passwort erscheint wie vorgesehen genau einmal im
Backend-Log.

Anmeldung end-to-end durchgespielt: Login mit dem Startpasswort → erzwungener
Wechsel → `/auth/me` → Nutzer anlegen → dessen Login → 403 auf die Verwaltung →
Deaktivieren → 401. Rate-Limit gegen echtes Redis: 5 Fehlversuche frei, der sechste
setzt die Sperre, der siebte bekommt `423` mit `Retry-After: 60`; danach wird auch
das *richtige* Passwort abgewiesen (die Sperre gilt vor dem Vergleich).

**Dabei gefunden — „Sperre aufheben" hob nichts auf.** `POST /users/{id}/unlock`
leerte nur `failed_login_count`/`locked_until` in der DB. Die Redis-Sperre läuft aber
pro (Benutzername, IP) unabhängig weiter: der Nutzer bekam bis zum Ablauf der TTL
weiter `423`, während die Oberfläche „entsperrt" meldete. Behoben mit
`login_throttle.clear_user()` (SCAN über alle IP-Buckets dieses Namens, kein KEYS);
`unlock`, `reset-password` und das Reaktivieren laufen darüber. Nachgeprüft: sperren
→ entsperren → sofortiger Login erfolgreich, keine Redis-Schlüssel übrig.

**Nebenbefund ohne Codeänderung:** Der Startup-Hook läuft auch im pytest-TestClient.
Ein Testlauf gegen eine leere DB legt also den Bootstrap-Superuser an (Passwort nur
in der pytest-Ausgabe). In der CI ist das eine Wegwerf-DB; auf einer Entwicklermaschine
sollte man `DATABASE_URL` für Tests trotzdem nicht auf die Betriebs-DB zeigen lassen.

---

## AP-2 — Fundament (source_format/embedded/lexer)

**Stand 31.07.2026.** Neues Package `parser/cobol/` nach Plan §6.2, bisher drei
der zehn Module plus die dafür nötigen Dataclasses:

- `model.py`: `Segment` (ein Textstück auf einer physischen Zeile, mit
  Spaltenposition) und `LogicalLine` (eine oder mehrere per Continuation
  zusammengefasste physische Zeilen). Die übrigen Plan-Dataclasses
  (`CobolProgram`, `DataItem`, `ParseResult`, …) kommen erst mit
  `divisions.py`/`data_division.py` — kein Vorbau auf Vorrat.
- `source_format.py` (F-021): `detect_format()` und `split_logical_lines()`.
  Autodetektion über zwei Signale: `*>` irgendwo in der Zeile sowie Text in
  Spalte 1-6, der keine Sequenznummer ist, zählen für Free-Format; ein
  gültiger Indikator in Spalte 7 zählt für Fixed-Format. Spaltenzerlegung
  trennt Sequenznummer/Indikator/Area A (8-11)/Area B (12-72), schneidet nach
  Spalte 72 ab, löst Continuation-Zeilen (Indikator `-`) auf und behandelt
  Debug-Zeilen (Indikator `D`) wie Kommentare (kein Debug-Modus-Umschalter in
  v1). Bei einer Continuation innerhalb eines offenen String-Literals wird
  das öffnende Anführungszeichen der Fortsetzungszeile verworfen, sonst
  landet es fälschlich im Literalwert.
- `embedded.py` (F-034): `mask()` ersetzt jeden `EXEC <dialect> … END-EXEC`-
  Block durch eine einzige Platzhalter-LogicalLine (`EMBEDDED-BLOCK-<DIALEKT>`,
  Bindestrich statt Unterstrich — ein `_` würde der Lexer als Worttrenner
  behandeln und den Platzhalter in Einzelteile zerlegen, darunter wieder das
  Wort `EXEC`). Ein eventuell abschließender Punkt nach `END-EXEC` bleibt als
  eigenes Zeichen erhalten, damit die Satzende-Erkennung weiter funktioniert.
  Läuft bewusst vor dem Lexer — sonst zerlegt ein Punkt im SQL-Text die
  Paragraphen. Fehlt ein `END-EXEC` (kaputte/abgeschnittene Quelle), bricht
  nichts ab: der Rest der Datei wird als Teil des Blocks gewertet (Plan §6.1
  Regel 2, „kein Abbruch").
- `lexer.py`: `tokenize()` erzeugt `Token`s (WORD/NUMBER/LITERAL/PERIOD/
  PSEUDO_TEXT) pro `Segment`, mit exakter Spalte und (nur Fixed-Format)
  Area A/B-Zuordnung. Literale lösen die COBOL-Verdopplungsregel für
  eingebettete Anführungszeichen auf (`'IT''S'` → ein Token). Zahlen nutzen
  einen Lookahead, damit z. B. `1D-ARRAY` als ein WORD-Token erhalten bleibt
  statt in `1` (NUMBER) + `D-ARRAY` (WORD) zu zerfallen.

**Bekannte Grenze, dokumentiert im Code statt in einer Entscheidung:** Der
Lexer tokenisiert pro `Segment`, nicht pro verketteter `LogicalLine`. Ein
gewöhnliches Wort (kein Literal), das über eine Continuation-Zeile hinweg
gebrochen wird, zerfällt dadurch in zwei Tokens. Continuation dient in der
Praxis fast ausschließlich langen Literalen/PICTURE-Klauseln — dieser Fall
ist nicht im Testkorpus abgedeckt und wird nachgezogen, falls der reale
Bestand ihn zeigt.

**Testkorpus (Teilausbau).** `parser/tests/cobol_corpus/fixtures/` enthielt bis
hierhin `01_minimal.cbl`, `02_fixed_edge.cbl` (Sequenznummern, Spalte-72-
Abschneiden, Continuation über eine offene Literal-Grenze), `03_free_format.cbl`
und `08_exec_cics.cbl`. Die restlichen Fixtures aus Plan §6.5 (04 COPY
REPLACING, 05 fehlendes Copybook, 06 qualifizierte Datenfelder, 07 EXEC SQL,
99 Garbage) entstehen mit den Modulen, die sie prüfen (`copybook.py`,
`data_division.py`, `sql.py`) — 09/10 sind jetzt da, siehe unten. Das
`golden/*.json`-Verzeichnis aus dem Plan (erwartete `ParseResult`-Serialisierung)
ist noch nicht angelegt — `ParseResult` existiert erst, wenn `parse.py` die
Pipeline orchestriert. Bis dahin prüfen gezielte Unit-Tests jede Stufe einzeln
gegen die Fixtures und einzelne Inline-Beispiele.

**Verifiziert (Fundament):** `python -m pytest tests/` im `parser`-Package —
26/26 neue Tests grün, die 32 bestehenden weiterhin grün. `python3 -m
compileall parser` fehlerfrei.

---

## AP-2 — Struktur (divisions/procedure)

**Stand 31.07.2026.** Zwei weitere der zehn Module, plus die dafür nötigen
Dataclasses in `model.py`: `Division`, `Section`, `Paragraph`, `CobolProgram`,
`ParsedEdge` (dazu `EntityType`/`EdgeType`/`Resolution` als `Literal`-Typen —
spiegeln bewusst die String-Werte aus `backend/models/database.py::CodeEntity.type`
/`CodeEdge.type`/`.resolution`, damit `parse.py` später ohne Übersetzungstabelle
direkt in die DB schreiben kann).

- `divisions.py` (F-020): `scan(tokens) -> (CobolProgram, errors)`. Ein einziger
  linearer Durchlauf über den Token-Strom erkennt IDENTIFICATION/ENVIRONMENT/
  DATA/PROCEDURE DIVISION, PROGRAM-ID, Section-Header (sowohl in DATA als auch
  in PROCEDURE DIVISION) und Paragraphen mit exaktem Zeilenbereich. Bewusst
  über "Satzanfang" erkannt (ein Header ist eine eigene Anweisung, die direkt
  nach einem Punkt beginnt), nicht über Area A/B-Spalten — Area A existiert im
  Free-Format gar nicht, die Grammatik-Regel gilt für beide Formate gleich.
  **Bug gefunden und behoben, bevor er in einen Test hätte einfließen können:**
  `embedded.mask()`s Platzhalter `EMBEDDED-BLOCK-<DIALEKT>` gefolgt vom Punkt
  nach `END-EXEC` ist strukturell nicht von einem Paragraphen-Header (WORD
  PERIOD) zu unterscheiden — ein EXEC-Block direkt unter einem Paragraphen
  hätte dessen Bereich sofort wieder geschlossen. `divisions.py` nimmt
  `EMBEDDED-BLOCK-`-Tokens jetzt explizit von der Header-Erkennung aus (Test:
  `test_embedded_block_does_not_close_enclosing_paragraph_early`).
- `procedure.py` (F-023/024): `scan(program, tokens) -> (list[ParsedEdge], errors)`.
  Durchsucht nur den PROCEDURE-DIVISION-Ausschnitt des Token-Stroms nach CALL/
  PERFORM/GO TO. `CALL 'LITERAL'` → `resolution="unresolved"` (globale
  Auflösung folgt erst im Nachlauf-Pass, Plan §6.4 Pass 2); `CALL WS-VAR`
  (Bezeichner statt Literal) → `resolution="dynamic"`, endgültig, nie
  auflösbar. `PERFORM ziel [THRU ziel2]` und `GO TO ziel [ziel2 …]` sind
  programmlokal (docs/ENTSCHEIDUNGEN.md E-1) und deshalb schon hier gegen die
  Paragraphen-/Section-Namen aus `divisions.py` auflösbar (`resolution=
  "resolved"`, sonst `"unresolved"` — z.B. bei einem Tippfehler im Zielnamen,
  kein Abbruch). `THRU` landet in `meta={"thru": ziel2}`. Inline-`PERFORM
  UNTIL/VARYING … END-PERFORM` ohne Prozedurnamen erzeugt keine Kante, der
  Statement-Rumpf wird trotzdem normal weiter durchsucht (verschachtelte CALLs
  darin werden gefunden).
- **Offener Punkt, keine Entscheidung nötig, nur nachzuziehen:** `GO TO` braucht
  einen eigenen `EdgeType`-Wert `"GOTO"`, der in `backend/models/database.py::
  CodeEdge.type`-Kommentar noch fehlt (dort nur `CALL | PERFORM | COPY |
  DEFINES | USES | READS | WRITES` gelistet). Nachziehen, sobald `parse.py`
  das Ergebnis von `procedure.py` an die DB-Schicht anbindet — blockiert
  `divisions.py`/`procedure.py` selbst nicht, die beide parser-intern bleiben.

**Testkorpus erweitert:** `09_dynamic_call.cbl` (statischer + dynamischer
CALL) und `10_perform_thru.cbl` (PERFORM THRU + unaufgelöstes PERFORM, vier
Paragraphen zur Prüfung exakter Zeilenbereiche) liegen jetzt unter
`parser/tests/cobol_corpus/fixtures/`.

**Verifiziert:** `test_cobol_divisions.py` (9 Tests) und `test_cobol_procedure.py`
(7 Tests) neu, macht 57 Tests im `parser`-Package — 48 grün, 2 übersprungen,
7 rot (dieselben vorbestehenden DB-Tests wie zuvor, brauchen ein laufendes
`db`/Docker-Netz aus dem Container-Netzwerk heraus, nicht vom Host-`venv` aus
erreichbar — `docker compose exec parser-worker` hat aktuell kein `pytest`
installiert, da nur `requirements.txt` im Image steht, nicht
`requirements-dev.txt`). `python3 -m compileall parser` weiterhin fehlerfrei.
(Korrigiert: eine frühere Fassung dieses Abschnitts nannte fälschlich 74
Tests/65 grün — nachgezählt gegen den Commit von damals, `7ad2ec0`, per
`git worktree`: tatsächlich 57/48.)

---

## AP-2 — Datenfelder (data_division/xref)

**Stand 31.07.2026.** Die zwei nächsten Module aus dem Plan-Layout (§6.2),
plus zwei neue Dataclasses in `model.py`: `DataItem`, `FileDescriptor`.

- `data_division.py` (F-025): `parse(program, tokens) -> (list[DataItem],
  list[FileDescriptor], errors)`. Ein linearer Durchlauf über den
  DATA-DIVISION-Ausschnitt des Token-Stroms erkennt Level-Nummern (01-49,
  66, 77, 88), `FD`/`SD`-Köpfe sowie PIC/REDEFINES/OCCURS [DEPENDING ON]/
  VALUE-Klauseln. Gruppenhierarchie über einen Stack von (Level, Name): ein
  neues Item schließt alle Stack-Einträge mit gleicher oder größerer
  Level-Nummer, sein `parent` ist danach der Stack-Top (oder die aktuelle
  FD/SD, wenn der Stack leer ist — Records in der FILE SECTION hängen so
  ohne Sonderfall an ihrer FD). Level 88 hängt sich an den Stack-Top, ohne
  selbst auf den Stack zu kommen (Condition-Name); 66 und 77 bleiben
  `parent=None` (laut COBOL-Grammatik ohne Kinder bzw. immer Top-Level).
  Der Stack (und die aktuelle FD/SD) werden bei jedem Section-Wechsel
  zurückgesetzt (über `program.sections` aus `divisions.py`).
  **Bug gefunden und behoben:** die PIC-Rekonstruktion (dazu gleich mehr)
  hat anfangs den abschließenden Satzpunkt mitgezogen, wenn er ohne
  Leerzeichen direkt an eine Klammer anschloss (`PIC X(30).`) — das hat den
  gesamten weiteren Scan verschoben und nachfolgende Items verschluckt.
  Jetzt bricht die PIC-Konsumierung explizit vor einem `PERIOD`-Token ab
  (Test: `test_pic_clause_does_not_swallow_trailing_period`).
- **Lexer-Erweiterung nötig:** `lexer.py` hat bisher `(`/`)` stillschweigend
  verschluckt (die Token-Regex kennt nur Wörter/Zahlen/Literale/Punkt), weil
  bisher kein Modul PIC-Klauseln brauchte. Neuer Token-Kind `SYMBOL` deckt
  jetzt genau diese beiden Zeichen ab; `data_division.py` rekonstruiert eine
  PIC-Klausel wie `X(10)V99` durch lückenloses Aneinanderhängen der
  Token-Werte anhand von Zeile+Spalte (`_contiguous`). Keine Regression in
  den bestehenden Lexer-Tests (die prüfen nur Teilmengen der Token-Liste,
  keine davon enthält Klammern).
- `xref.py` (F-025): `scan(program, tokens, items) -> (list[ParsedEdge],
  errors)`. Wort-Match jedes WORD-Tokens der PROCEDURE DIVISION gegen den
  Namensindex der übergebenen `DataItem`s — kein Verb-Filter nötig, weil
  COBOL reservierte Wörter nie gleichzeitig gültige Datennamen sein können.
  Paragraphen-/Section-Namen werden explizit ausgeschlossen (sonst würden
  PERFORM-/GO-TO-Ziele als Datenfeld-Nutzung gezählt). Mehrdeutige Treffer
  (derselbe Feldname in zwei Gruppen) werden über ein direkt folgendes
  `OF`/`IN <Gruppe>` aufgelöst; bleibt es mehrdeutig, `resolution=
  "unresolved"` statt geraten — dieselbe „kein Raten"-Regel wie bei
  `COPY … REPLACING` in docs/ENTSCHEIDUNGEN.md E-2.
  **Bewusste Einschränkung dieser ersten Fassung:** der Namensindex ist nur
  programmlokal (aus den `DataItem`s dieses Parse-Durchlaufs). E-2 verlangt
  einen quellenweiten Index über Copybook-Grenzen hinweg — das braucht
  `copybook.py`/`parse.py`, die es noch nicht gibt, und ist explizit „offen
  bis AP-2" laut Entscheidungslog, kein Blocker für dieses Teilstück.

**Testkorpus erweitert:** `06_data_qualified.cbl` — FD/SD mit Record-Parent,
zwei gleichnamige Felder in unterschiedlichen Gruppen (OF/IN-Qualifizierung),
REDEFINES, OCCURS ... DEPENDING ON über eine Zeilengrenze hinweg, und ein
Level-88-Condition-Name.

**Verifiziert:** `test_cobol_data_division.py` (11 Tests) und
`test_cobol_xref.py` (8 Tests) neu. `python -m pytest tests/` im `parser`-
Package: 76 Tests gesammelt, 67 grün, 2 übersprungen, 7 rot (dieselben
vorbestehenden DB-Tests wie zuvor, brauchen Docker-Netz). `python3 -m
compileall parser` weiterhin fehlerfrei.

---

## AP-2 — Copybooks (copybook)

**Stand 31.07.2026.** F-022: `COPY name [OF|IN lib] [REPLACING operand BY
operand …]` als `ParsedEdge` (`type="COPY"`). Kein neues Dataclass in
`model.py` nötig — `COPY` stand als `EdgeType` schon seit divisions.py/
procedure.py fest.

- `copybook.py`: `scan(program, tokens, index) -> (list[ParsedEdge], errors)`.
  Scannt bewusst den **gesamten** Token-Strom, nicht auf eine Division
  beschränkt — COPY ist ein Bibliotheksstatement, das laut COBOL-Grammatik
  überall stehen darf (meistens DATA DIVISION, aber auch FILE-CONTROL oder
  PROCEDURE DIVISION), und läuft deshalb unabhängig von divisions.py/
  data_division.py/procedure.py.
- `index` ist ein `CopybookIndex` (`dict[str, list[str]]`, Name → Pfade) —
  entspricht Plan §6.4 Pass 0 ("alle *.cpy/*.copy scannen, nur Namen"), wird
  hier nur als Parameter entgegengenommen; der eigentliche Repo-Scan ist
  Sache von `parse.py`, das es noch nicht gibt. Auflösung: genau ein Pfad →
  `resolved`. Mehrere Pfade (derselbe Copybook-Name in mehreren
  Bibliotheks-Verzeichnissen) nur über ein passendes `OF`/`IN lib` eindeutig
  (Verzeichnisname des Pfads gegen `lib` verglichen), sonst `unresolved` —
  kein Raten, dieselbe Regel wie bei `REPLACING` in E-2.
- `REPLACING`-Paare (Pseudo-Text `==...==` oder einfache Wörter/Literale,
  beliebig viele hintereinander ohne Trennzeichen nötig) landen roh in
  `meta["replacing"]` als Liste von `{"from": ..., "to": ...}` — die
  Anwendung auf geerbte Feldnamen ist Sache der XREF-Nachauflösung, sobald
  der quellenweite Feldindex existiert (E-2, weiterhin offen bis
  `copybook`-Entities in `parse.py` gebaut werden).
- Bewusst **keine** Expansion des Copybook-Inhalts (Plan §6.1 Regel 1) — nur
  die Kante wird gespeichert, das Copybook selbst wird später als eigene
  Entity mit eigenen Zeilennummern separat geparst.

**Testkorpus erweitert:** `04_copy_replacing.cbl` (COPY … REPLACING mit
Pseudo-Text) und `05_copy_missing.cbl` (nicht indiziertes Copybook →
`unresolved`, kein Crash) — beide waren im Plan (§6.5) bereits für diesen
Schritt vorgesehen.

**Verifiziert:** `test_cobol_copybook.py` (8 Tests) neu, deckt zusätzlich zu
den Fixtures auch OF/IN-Disambiguierung zwischen mehreren Pfaden, mehrere
REPLACING-Paare ohne Trennzeichen und COPY innerhalb eines Paragraphen
(`src_name` = umschließender Paragraph statt Programmname) über Inline-Text
ab. `python -m pytest tests/`: 84 Tests gesammelt, 75 grün, 2 übersprungen,
7 rot (dieselben vorbestehenden DB-Tests wie zuvor). `python3 -m compileall
parser` weiterhin fehlerfrei.

---

## AP-2 — SQL (sql)

**Stand 31.07.2026.** F-027: leichtgewichtiger EXEC-SQL-Klassifikator. Neues
Dataclass `SqlBlock` in `model.py` (Entity-Typ `sql_block`, E-4).

- `sql.py`: `scan(program, blocks, items) -> (list[SqlBlock], list[ParsedEdge],
  errors)`. Arbeitet auf den `EmbeddedBlock`s aus `embedded.mask()` (F-034),
  nicht auf dem Lexer-Token-Strom — SQL-Syntax (`:`, `,`, `()`) passt nicht in
  COBOLs WORD/LITERAL-Grammatik. Nur Blöcke mit `dialect == "SQL"` werden
  ausgewertet, andere Dialekte (z. B. CICS) werden übersprungen.
- Klassifikation ist reine Wort-/Regex-Extraktion über den von `EXEC SQL`/
  `END-EXEC` befreiten Blocktext, kein SQL-Parser, kein Katalogabgleich:
  Statement-Typ aus dem ersten Schlüsselwort (`SELECT`/`INSERT`/`UPDATE`/
  `DELETE`/`OPEN`/`FETCH`/`CLOSE`/`COMMIT`/`ROLLBACK`/`INCLUDE`/`WHENEVER`/
  `CALL`/`EXECUTE`/`SET`, `DECLARE … CURSOR` → `DECLARE_CURSOR`, sonst
  `OTHER`); Tabellen/Views aus dem Wort nach `FROM`/`JOIN`/`INTO` (nur wenn
  das folgende Wort **kein** Host-Variablen-Präfix `:` trägt — sonst wäre z. B.
  `FETCH … INTO :WS-FELD` fälschlich eine Tabelle) sowie nach `UPDATE` am
  Statement-Anfang; Cursor-Name aus dem Wort nach `DECLARE`/`OPEN`/`FETCH`/
  `CLOSE`.
- `SqlBlock.name` ist synthetisch (`SQL-BLOCK@<start_line>`) — ein anonymer
  EXEC-SQL-Block hat kein COBOL-eigenes Bezeichnerwort, die Zeilennummer ist
  die einzige stabile Identität und macht ihn trotzdem als Kantenendpunkt für
  `USES` adressierbar (E-4 verlangt `SQL-Block → Datenfeld`).
- Host-Variablen (`:WS-FELD`) werden gegen den von `xref.build_index()`
  gebauten Datenfeld-Index aufgelöst (gleiche Funktion, wiederverwendet statt
  dupliziert) — genau ein Treffer → `resolved`, sonst `unresolved`. Anders als
  bei COBOL-Text selbst gibt es in SQL kein `OF`/`IN` zur Disambiguierung,
  Mehrdeutigkeit bleibt hier also immer `unresolved` (E-2-Regel: kein Raten).

**Testkorpus erweitert:** `07_exec_sql.cbl` (DECLARE CURSOR FOR SELECT, OPEN,
FETCH INTO mit zwei Host-Variablen, CLOSE) — im Plan (§6.5) bereits für diesen
Schritt vorgesehen.

**Verifiziert:** `test_cobol_sql.py` (9 Tests) neu, deckt zusätzlich zur
Fixture INSERT INTO (Tabellen- vs. Host-Variablen-Disambiguierung bei `INTO`),
nicht auflösbare und mehrdeutige Host-Variablen sowie das Überspringen von
Nicht-SQL-Dialekten (CICS) über Inline-Text/vorhandene Fixtures ab. `python -m
pytest tests/`: 93 Tests gesammelt, 84 grün, 2 übersprungen, 7 rot (dieselben
vorbestehenden DB-Tests wie zuvor, unabhängig vom COBOL-Parser). `python3 -m
compileall parser` weiterhin fehlerfrei.

---

## AP-4 (vorgezogen) — Chunking (chunking)

**Stand 31.07.2026.** F-041: COBOL-bewusstes Chunking entlang Paragraph-/
Section-Grenzen für den RAG-Index. Neues Dataclass `Chunk` in `model.py`
(`content`, `start_line`, `end_line`, `meta` — `meta` landet 1:1 in
`DocumentChunk.metadata_json`).

**Gehört formal zu AP-4, nicht AP-2** (docs/ENTSCHEIDUNGEN.md E-6): §6.2 zeigt
`chunking.py` zwar im Package-Layout neben den AP-2-Modulen, aber §6.6
(Aufwandsschätzung AP-2) und §13 (Arbeitspakete-Tabelle) ordnen F-041 explizit
AP-4 zu. Vorgezogen gebaut, weil es nur von `CobolProgram`/`Paragraph`/
`Section` abhängt, keine DB-Anbindung braucht — reine Reihenfolge-Optimierung,
kein Scope-Fehler. **Für den AP-2-Fortschritt zählt dieser Abschnitt nicht.**

- `chunking.py`: `chunk(program, source_lines, source_format, chunk_size=1000,
  min_chunk_size=200) -> list[Chunk]`. Arbeitet auf den physischen
  Quellzeilen (nicht auf LogicalLines/Tokens) — Chunk-Text ist für
  Embedding/Anzeige gedacht. Nur PROCEDURE-DIVISION-Paragraphen; DATA/
  IDENTIFICATION DIVISION sind über ihre eigenen Entities (DataItem,
  FileDescriptor) bereits strukturiert durchsuchbar.
- Regelfall: ein Chunk je Paragraph, `meta["paragraph"]` (str) gesetzt.
- **Split bei Übergröße** (`len(text) > chunk_size`): zeilenweises,
  nicht-überlappendes Packen (nie mitten in einer Zeile), mehrere Chunks mit
  gleichem `meta["paragraph"]`-Namen plus `"part"`/`"parts"` (1-basiert). Eine
  einzelne Zeile, die für sich schon größer als `chunk_size` ist, wird trotzdem
  komplett übernommen statt eine Endlosschleife zu riskieren (Plan §6.1 Regel 2).
- **Merge bei Winzlingen** (`len(text) < min_chunk_size`): aufeinanderfolgende
  Paragraphen puffern, bis die kombinierte Länge die Schwelle erreicht oder
  ein Paragraph mit anderer Section folgt — Merge bleibt **innerhalb einer
  Section**. `meta["paragraphs"]` (Liste) ersetzt dann `meta["paragraph"]`
  (Singular), weil ein Chunk mehr als einen Paragraphen abdeckt. Ein einzelner
  zu kleiner Paragraph ohne gleich-tiny-en Nachbarn in derselben Section wird
  beim Flush trotzdem zu einem normalen Einzel-Chunk (nicht verworfen, nicht
  über die Section-Grenze hinweg zwangsverschmolzen).
- Größen-Heuristik ist Zeichenlänge des rekonstruierten Paragraphtexts, nicht
  Tokenanzahl — bewusst so einfach wie der Rest der "leichtgewichtigen"
  AP-2-Module.

**Verifiziert:** `test_cobol_chunking.py` (6 Tests) neu — normale Paragraphen,
Merge innerhalb einer Section, kein Merge über Section-Grenzen, Split eines
übergroßen Paragraphen (mit Rekonstruktions-Check: Verkettung der Chunk-Inhalte
ergibt exakt den Originaltext, keine verlorene/duplizierte Zeile), Split direkt
nach einem gepufferten Winzling (Puffer wird vor dem Split geleert) sowie ein
Programm ohne PROCEDURE-DIVISION-Paragraphen (leere Liste, kein Crash). `python
-m pytest tests/`: 99 Tests gesammelt, 90 grün, 2 übersprungen, 7 rot (dieselben
vorbestehenden DB-Tests wie zuvor). `python3 -m compileall parser` weiterhin
fehlerfrei.

---

## AP-2 — Orchestrierung und Testkorpus (parse.py) — AP-2 fertig

**Stand 31.07.2026.** Letztes Teilstück von AP-2 (§6.6, 1,5 PW): `parse.py`
mit der In-Memory-Funktion `parse_program(text, path, copybook_index) ->
ParseResult` (kein DB-Zugriff, docs/ENTSCHEIDUNGEN.md E-6) plus zwei neue
Dataclasses in `model.py`: `Entity` und `ParseResult`.

- `parse.py`: ruft die neun bisherigen Module in Pipeline-Reihenfolge auf
  (source_format → embedded → lexer → divisions → data_division →
  procedure → copybook → sql → xref → chunking, Plan §6.3) und fasst
  Ergebnisse zu `ParseResult{entities[], edges[], chunks[], errors[]}`
  zusammen. `chunking.chunk()` wird hier schon aufgerufen (gehört formal zu
  AP-4, braucht aber wie schon beim Vorziehen selbst keine DB-Anbindung).
- **`Entity`** (neu in `model.py`) ist die parse-time-Vorstufe von
  `CodeEntity` — alle Felder außer den DB-Zuweisungen (`id`/`project_id`/
  `source_id`/`parent_id`/`content_hash`, die erst beim Persistieren in AP-4
  entstehen). Statt `parent_id` trägt sie `parent_name` (Name der
  Eltern-Entity **derselben Datei** — AP-4 löst daraus beim Schreiben die
  echte `parent_id` auf). `qualified_name` wird schon hier gebaut (z.B.
  `"XAAOA.MAIN-SECTION.INIT-PARA"` bzw. `"XAAOA.EMPLOYEE-FILE.
  EMPLOYEE-RECORD.EMP-ID"` für Datenfeld-Hierarchien) — alle nötigen
  Vorfahren sind beim Parsen einer einzelnen Datei bereits vollständig
  bekannt.
- `_build_entities()` erzeugt aus `CobolProgram`/`DataItem`/
  `FileDescriptor`/`SqlBlock` eine flache `Entity`-Liste: `program` (Wurzel,
  `parent_name=None`), `section`/`paragraph` (Eltern = Programm bzw.
  Section — es gibt bewusst **keinen** `division`-Entity-Typ, Divisions
  selbst werden nicht persistiert), `file_fd`, `data_item` (Eltern-Kette
  über `DataItem.parent`, das wahlweise eine FD/SD oder ein Gruppenfeld
  benennt — zwei getrennte Name→Qualified-Name-Verzeichnisse
  (`section_qnames`/`field_qnames`) vermeiden dabei eine Namenskollision
  zwischen Section- und Datenfeld-Namensräumen), `sql_block` (Eltern immer
  das Programm). `copybook`- und `sql_table`-Entities entstehen hier
  bewusst **nicht** — Copybook-Dateien werden erst in AP-4 als eigene
  Entities geparst (E-2), `sql_table` ist kein Ergebnis dieses Parse-Laufs.
- **F-029-Fallback:** `chunking.chunk()` liefert `[]`, wenn das Programm
  keinen einzigen PROCEDURE-DIVISION-Paragraphen hat (kaputte/unvollständige
  Datei). Damit die Datei trotzdem durchsuchbar bleibt (Plan §6.1 Regel 2,
  "generisches Text-Chunking"), springt dann `_fallback_chunks()` ein:
  dieselbe zeilenweise Packstrategie wie `chunking._split_paragraph()`, nur
  über die gesamte Datei statt über einen Paragraphen, `meta["fallback"] =
  True` markiert den Unterschied zum Regelfall.

**Testkorpus (F-033, abnahmerelevant):** `99_garbage.cbl` neu — vorsätzlich
kaputt (kein IDENTIFICATION/PROGRAM-ID, ein EXEC-SQL-Block ohne END-EXEC,
der bis Dateiende offen bleibt, undefinierbare Host-Variable) und beweist
den F-029-Pfad: kein Crash, `errors` gefüllt, `chunks` über den
Fallback-Pfad trotzdem nicht leer. `tests/cobol_corpus/golden/*.json` (elf
Dateien, eine je Fixture) sind die erwartete `ParseResult`-Serialisierung
über `dataclasses.asdict()` — reproduzierbar über
`scripts/regenerate_cobol_golden.py` (Repo-Root), nie von Hand editiert.
CI-Job `parser-golden` (`.github/workflows/ci.yml`) läuft `pytest tests/ -k
cobol` — bewusst ohne DB/Redis-Service, weil die gesamte COBOL-Parser-
Testsuite (inkl. Golden Files) keinen braucht.

**Verifiziert:** `test_cobol_parse.py` (7 gezielte Unit-Tests: Entity-/
Qualified-Name-Aufbau, Copybook-Index-Auflösung, kombinierte Kantenarten,
beide Fallback-Fälle) und `test_cobol_golden.py` (11 parametrisierte
Golden-File-Vergleiche + ein Vollständigkeits-Check Fixture↔Golden) neu.
`python -m pytest tests/` im `parser`-Package: 118 Tests gesammelt, 109
grün, 2 übersprungen, 7 rot (dieselben vorbestehenden DB-Tests wie zuvor,
unabhängig vom COBOL-Parser). `python -m pytest tests/ -k cobol`: 103/103
grün, kein DB-Zugriff nötig. `python3 -m compileall parser` weiterhin
fehlerfrei.

**AP-2 ist damit fertig** (docs/ENTSCHEIDUNGEN.md E-6: alle zehn Module
plus `parse_program()` plus Testkorpus). Offen bleibt weiterhin nur der
schon dokumentierte Nachzieh-Punkt (kein Blocker): `EdgeType` "GOTO" fehlt
noch im `CodeEdge.type`-Kommentar in `backend/models/database.py` (und der
gespiegelten Kopie in `parser/models/database.py`) — wird ergänzt, sobald
AP-4 `parse_program()`-Ergebnisse an die DB-Schicht anbindet.

---

## AP-3 — Monorepo-Git-Konnektor (Bare-Mirror + Worktree)

**Erledigt am 31.07.2026.** Neu: `parser/git_utils.py` (reine Bare-Mirror-/
Worktree-Primitiven über `subprocess`, kein DB-Zugriff, F-019/§7.1/§7.2) und
kompletter Neubau von `parser/connectors/git.py` (F-010/016/019/NF-004).
`parser/utils.py` verlor die alten Flat-Clone-Helfer (`clone_repository`,
`clone_repository_sparse`, `list_files_iter`, `EXCLUDE_DIRS`) — tot, sobald
nichts mehr Vollklone macht.

**Physisches Layout wie Plan §7.1:** `/repos/bare/<fingerprint>.git` (sha1
der normalisierten Repo-URL, geteilt über alle Wissensquellen desselben
Repos) + `/repos/wt/ks_<source_id>/` (ein Worktree je Quelle = je Branch).
`repo_fingerprint` setzt der Connector selbst beim ersten Sync, nicht das
Backend bei der Quellenanlage — vermeidet doppelte Fingerprint-Logik über
zwei getrennte Docker-Images hinweg.

**Zwei reale Abweichungen vom Plan-Pseudocode**, beide durch Ausprobieren an
einem echten lokalen Repo gefunden (nicht aus git-Doku ersichtlich, siehe
Kommentare in `git_utils.py` und die Notiz unter Plan §7):
1. `git -C <worktree> reset --hard FETCH_HEAD` schlägt fehl — FETCH_HEAD ist
   aus einem angehängten Worktree heraus nicht auflösbar, obwohl die Datei im
   gemeinsamen Bare-Gitdir liegt. Umgangen über `refs/heads/<branch>` als
   Zwischenstation (`fetch_branch()` zieht ihn per `branch -f` auf
   FETCH_HEAD nach; Worktrees resetten gegen den Branch-Namen).
2. `git branch -f` verweigert das Verschieben eines Branches, solange
   irgendein Worktree ihn nicht-losgelöst ausgecheckt hat — bricht, sobald
   zwei Wissensquellen (verschiedene Projekte, F-019 erlaubt das
   ausdrücklich) denselben Branch desselben Repos referenzieren. Alle
   Worktrees werden daher mit `--detach` angelegt (kein benannter Checkout,
   also auch keine Exklusivsperre auf den Branch).

**Resumability (NF-004):** `SourceScanFile.content_hash` trägt den
Git-Blob-SHA (gekürzt auf 32 Zeichen, passend zur `VARCHAR(32)`-Spalte) statt
eines separat berechneten md5 — git kennt den Content-Hash über den Blob-SHA
bereits, kein zusätzliches Lesen+Hashen nötig. Vor jedem Embedding wird der
aktuelle Blob-SHA gegen den zuletzt gespeicherten geprüft; unverändert seit
dem letzten (ggf. abgebrochenen) Sync = überspringen. Nach jedem
persistierten Dokument werden `DocumentChunk` und `SourceScanFile` im selben
`db.commit()` aktualisiert. `sync_cursor` trägt nur `{"last_commit": …}` —
der granulare Resume läuft über den Content-Hash-Check pro Datei, nicht über
einen zusätzlichen Cursor-Zeiger.

**Dateiklassifikation (F-016):** `COBOL_EXT`/`COPYBOOK_EXT`/`JCL_EXT` ersetzen
die alte sprachfeingranulare `EXT_LANG_MAP` (JS/Java/Go/…) — sinnvoll, weil
`CodeParser.chunk_file()` ohnehin komplett sprachagnostisch chunked (siehe
Docstring dort, PARSER_REGISTRY war laut `docs/TECH_DEBT_CLEANUP_PLAN.md`
immer leer) und das Feld nur informativ in `metadata_json` landet.
Konfigurierbar über `DOCTUS_COBOL_EXTENSIONS` (Env, Worker-weit) und
optional `spaces.cobol_extensions` pro Wissensquelle (überschreibt den Env-
Default).

**Zwei-stufiges Locking:** `lock:sync_source:<id>` (bestehend, ganzer Sync)
+ neu `lock:git_fetch:<fingerprint>` (nur um Bare-Mirror-Fetch/Worktree-Setup,
verhindert paralleles Fetch auf denselben Bare-Store bei zwei Quellen mit
demselben Repo). Der engere Lock wird vor dem — deutlich längeren —
Embedding-Schritt wieder freigegeben.

**Backend-Anpassungen:** `POST /knowledge_sources/git` schreibt `branch` jetzt
in die eigene Spalte statt in `spaces` (Modell-Kommentar sah das schon vor);
`serialize_source()` gibt `branch` mit aus. `GET /knowledge_sources/{id}/content`
sowie `GET /projects/{id}/files` und `/projects/{id}/stats` lasen Git-Dateien
noch am alten Flat-Pfad `REPOS_ROOT/ks_<id>` — auf `REPOS_ROOT/wt/ks_<id>`
korrigiert, sonst wären Dateivorschau/Repo-Stats für jede neue Git-Quelle
leer geblieben. `frontend/.../SourcesTab.tsx` liest den Branch-Badge jetzt
aus `inst.branch` (mit Fallback auf `inst.spaces?.branch` für Zeilen aus vor
dieser Migration).

**Nebenbei entdeckt, bewusst nicht mitgefixt:** `backend/api/projects.py::delete_project`
liest `proj.repository` — das `Project`-Modell hat aber gar kein
`repository`-Attribut/keine solche Relationship. Ein Aufruf von
`DELETE /projects/{id}` würfe dort einen `AttributeError`. Vorbestehender
Bug, unabhängig vom AP-3-Layoutwechsel (der Pfad, den der Code danach bauen
würde, wäre ohnehin falsch — kein `ks_`-Präfix). Nicht mitgefixt, um AP-3 auf
den Git-Konnektor beschränkt zu halten; separat nachziehen.

**Verifiziert:** `parser/tests/test_git_utils.py` (11 Tests, kein DB-Zugriff,
echte lokale Git-Repos über `tmp_path` — Fingerprint-Normalisierung,
geteilter Bare-Mirror über zwei Branches *und* über zwei Quellen auf
demselben Branch, Rename-Erkennung, Sparse-Checkout-Cone-Semantik) und
`parser/tests/test_git_connector.py` (4 Tests, brauchen einen erreichbaren
DB-Host wie die übrigen Connector-Tests — Erstsync, Delta-Sync mit
Add/Modify/Delete, Resume-Skip über `content_hash`, zwei Quellen teilen sich
den Bare-Mirror). Beide Suiten liefen grün im laufenden `parser-worker`-
Container (pytest dort nur für diesen Testlauf nachinstalliert, nicht im
Image persistiert — die schon dokumentierte Lücke "kein pytest im Image"
bleibt bestehen). `pytest tests/ -k cobol`: weiterhin 103/103 grün,
unberührt. `npx tsc --noEmit` (frontend) und `pytest tests/` (backend, 75
grün + 1 skip) sauber. Zwei echte Bugs beim Implementieren gefunden und
korrigiert (siehe oben) — nicht nur angenommen, sondern an einem echten
lokalen Repo nachgestellt, bevor der Fix geschrieben wurde.

---

## AP-4 — Entity-/Kanten-Persistenz + Nachauflösung + Retrieval (fertig)

**Stand 31.07.2026 (Abend), Teilschritt 1/N.** Zwei Vorarbeiten in
`parser/cobol/`, bevor die eigentliche DB-Anbindung (Pass 0-2, Plan §6.4)
beginnt:

- **`xref.py`:** `ParsedEdge.meta["parent"]` wird jetzt gesetzt, wenn
  `_resolve()` ein Ziel-`DataItem` gefunden hat (auch im disambiguierten
  Fall über OF/IN). **Grund:** ohne das trägt eine `USES`-Kante nur den
  plainen Feldnamen (`dst_name`) — bei zwei gleichnamigen Feldern in
  unterschiedlichen Gruppen im selben Programm (06_data_qualified.cbl) kann
  die spätere Persistenz (Pass 1) dann nicht mehr rekonstruieren, welches
  der beiden xref zur Parse-Zeit tatsächlich gemeint hat. Ohne den Fix wäre
  die zur Parse-Zeit getroffene Disambiguierung beim Schreiben in
  `code_edges` verloren gegangen — kein Crash, aber eine still falsch
  verdrahtete Kante, genau das, was E-2 („kein Raten") verhindern soll.
  **Nebenwirkung:** die Golden Files für Fixtures mit disambiguierten
  USES-Kanten ändern sich (zusätzliches `meta.parent`) — Regenerierung über
  `scripts/regenerate_cobol_golden.py` steht noch aus, siehe unten.
- **`parse.py::parse_copybook(text, path) -> ParseResult`** (neu, E-2):
  Copybook-Dateien haben laut COBOL-Grammatik meist keine DIVISION-Header,
  `data_division.parse()` braucht aber ein `CobolProgram` mit einer
  DATA-Division, um deren Zeilenbereich zu kennen — hier synthetisch über
  die gesamte Datei aufgespannt (`CobolProgram(divisions=[Division("DATA",
  start, end)])`). Baut eine `copybook`-Wurzel-Entity plus `file_fd`/
  `data_item`-Kinder über eine neue gemeinsame Hilfsfunktion
  `_build_field_entities()` (aus `_build_entities()` extrahiert, jetzt von
  Programmen UND Copybooks genutzt — beide brauchen exakt dieselbe
  Qualified-Name-Form, sonst funktioniert die XREF-Vererbung über
  COPY-Grenzen hinweg nicht). Chunking: da Copybooks keine
  PROCEDURE-DIVISION-Paragraphen haben, an denen `chunking.chunk()` entlang
  chunken könnte, chunkt `parse_copybook()` die gesamte Datei als
  Ganzes (`meta["copybook"]` statt `"program"`/`"paragraph"`) über eine neu
  extrahierte `_pack_whole_file()`-Hilfsfunktion, die sich `_fallback_chunks()`
  (F-029) und `parse_copybook()` jetzt teilen (vorher war das Packen nur in
  `_fallback_chunks()` inline vorhanden).
  Name der Copybook-Entity: Dateiname ohne Endung, uppercased (so
  referenzieren `COPY`-Statements sie auch, siehe `copybook.py`s
  `CopybookIndex`).

**`parser/cobol_persist.py`** (neu, Pass 1, Plan §6.4): schreibt ein
`ParseResult` einer Datei nach `code_entities`/`code_edges`. Bewusst
**außerhalb** von `parser/cobol/` — das Paket bleibt komplett DB-frei (E-6),
genauso wie `chunk_reindex.py` neben dem generischen `code_parser.py` sitzt.

- **Entities: UPSERT per (source_id, file_path, qualified_name), nicht
  Löschen+Neueinfügen.** Grund: `CodeEdge.dst_entity_id`/`.scope_entity_id`
  stehen auf `ON DELETE CASCADE`. Würde eine reparste Datei ihre Entities
  einfach löschen und neu anlegen, rissen dabei auch Kanten aus
  UNVERÄNDERTEN anderen Dateien mit, die auf eine Entity dieser Datei zeigen
  (z.B. ein `CALL` aus Programm C auf ein Programm A, das gerade
  reindexiert wird) — obwohl C selbst in diesem Sync gar nicht neu geparst
  wird (Resume-Skip über `content_hash`, NF-004) und die Kante bis zum
  nächsten vollständigen Sync von C verloren bliebe. Nur wirklich
  verschwundene Entities (z.B. ein gelöschter Paragraph) werden gezielt per
  `qualified_name` entfernt, CASCADE greift dann zu Recht. **Das ist der
  dritte real gefundene Bug bei der AP-4-Umsetzung** (nach den zwei
  Git-Worktree-Bugs aus AP-3) — beim Durchdenken des Reparse-Falls
  entdeckt, nicht erst beim Testen.
- **Eltern-Auflösung ohne Namens-Mehrdeutigkeit:** `qualified_name` wird in
  `parse.py` ausschließlich über `f"{parent_qname}.{name}"` gebaut — ein
  `rsplit(".", 1)` liefert deshalb exakt den Eltern-`qualified_name`, ganz
  ohne über den (mehrdeutigen) Klartext-`parent_name` suchen zu müssen.
- **Kanten dieser Datei werden vollständig ersetzt** (anders als Entities —
  hier gibt es keine Fremdreferenz von außen auf eine einzelne Kantenzeile).
  Lokale Kantenarten (PERFORM/GOTO/USES, `scope` gesetzt) werden sofort
  gegen Entities derselben Datei aufgelöst — bei USES zusätzlich über
  `meta["parent"]` disambiguiert (siehe xref.py-Fix oben). Globale
  Kantenarten (CALL/COPY) bleiben unresolved/dynamic; ihre Auflösung ist
  Pass 2.

**Pass 0 + Anbindung an `GitConnector`** (`parser/connectors/git.py`):
`_build_copybook_index()` listet bei **jedem** Sync über `git_utils.
list_tracked_files()` den gesamten Baum (nicht nur das Delta) nach
Copybook-Erweiterungen ab. Für E-2 werden zusätzlich die Felddefinitionen
jedes lesbaren Copybooks einmal in-memory geparst. Grund
für „gesamter Baum, nicht nur Delta": ein in diesem Sync geändertes
Programm kann ein Copybook COPYen, das selbst unverändert (und damit gar
nicht Teil des Diffs) ist. `_embed_document()`/`_save_document_chunks()`
verzweigen jetzt für `lang in {"cobol", "copybook"}` auf
`parse_program()`/`parse_copybook()` statt auf den generischen
`CodeParser` — Chunks kommen aus `ParseResult.chunks` (inkl. `meta`, das
jetzt zusätzlich in `DocumentChunk.metadata_json` einfließt), Entities/
Kanten gehen über `persist_parse_result()` in die DB.
`SourceScanFile.parse_status` wird dabei mitgesetzt (`'ok'` /
`'fallback_text'` bei `ParseResult.errors != []`, F-029). Bei gelöschten
Dateien werden jetzt zusätzlich zum `SourceScanFile`-Eintrag auch die
`CodeEntity`-Zeilen dieser Datei entfernt — hier ist Löschen (mit
CASCADE auf eingehende Kanten) korrekt, weil die Datei wirklich weg ist,
anders als beim Reparse-Fall in `cobol_persist.py`.

**Pass 2** (`parser/tasks/edge_resolver.py::resolve_global_edges()`, neu):
löst offene `CALL`/`COPY`-Kanten (`scope_entity_id IS NULL`) über `dst_name`
gegen `code_entities(type IN ('program','copybook'))` derselben Quelle auf —
getrennte Namensindizes für Programme/Copybooks, damit ein Programm und ein
gleichnamiges Copybook sich nicht verdecken können. Nur bei genau einem
Treffer (E-1/E-2 „kein Raten"). Läuft synchron am Ende von
`GitConnector.sync()` (kein eigener Celery-Task — ein einzelner
beschränkter Query+UPDATE, kein Hintergrundlauf wie `link_builder.py`).

**GOTO-Nachzug erledigt:** `EdgeType`-Kommentar an `CodeEdge.type` in
`backend/models/database.py` **und** `parser/models/database.py` (weiterhin
byte-identisch) listet jetzt `GOTO` — der seit AP-2 dokumentierte offene
Punkt.

**Golden-Files regeneriert** (`scripts/regenerate_cobol_golden.py`) — nur
`06_data_qualified.json` ändert sich (das neue `meta["parent"]` aus dem
xref.py-Fix), alle anderen zehn unverändert. `pytest tests/ -k cobol`:
weiterhin 103/103 grün nach der Regenerierung, plus vier neue
No-DB-Unit-Tests für `parse_copybook()` (`test_cobol_parse_copybook.py`) —
Copybook-Entity-Hierarchie, Namensableitung aus dem Dateinamen, Ganze-Datei-
Chunking mit Rekonstruktions-Check, leere Datei ohne Crash → 107/107.

**Vierter real gefundener Bug** (nach den zwei Git-Worktree-Bugs aus AP-3
und dem ID-Erhalt-Bug oben) — von `tests/test_ap4_persistence.py` beim
ersten Lauf gefangen, nicht nur angenommen: `copybook.py` setzt
`ParsedEdge.resolution="resolved"` schon zur Parse-Zeit, sobald der
Pass-0-Namensindex GENAU EINEN Pfad zu `dst_name` kennt — eine reine
Namensauflösung, keine DB-Auflösung (die Ziel-Entity existiert zu diesem
Zeitpunkt evtl. noch gar nicht in `code_entities`). `cobol_persist.py` gab
diesen Wert ursprünglich unverändert an `CodeEdge.resolution` weiter, ohne
`dst_entity_id` zu setzen (das ist explizit Pass 2s Aufgabe) — Pass 2s
Filter `WHERE resolution = 'unresolved'` überging die Kante dadurch für
immer, obwohl sie nie tatsächlich verlinkt war. **Fix:** `_build_edge()`
erzwingt für alle globalen Kanten (CALL/COPY) `resolution="unresolved"`
(außer `"dynamic"`) unabhängig vom Parser-Wert — DB-seitig gilt "resolved"
erst, wenn Pass 2 wirklich eine Entity gefunden und `dst_entity_id` gesetzt
hat. Details im Docstring von `cobol_persist.py`.

**DB-Tests** (`parser/tests/test_ap4_persistence.py`, 3 Tests, laufen wie
bei AP-3 im `parser-worker`-Container mit temporär nachinstalliertem
pytest — kein bind-mount, `pip uninstall pytest` danach wieder rückgängig
gemacht): End-to-End-Sync eines Repos mit zwei Programmen (CALL/PERFORM)
und einem Copybook (COPY) verifiziert Entity-Hierarchie, lokale
Sofort-Auflösung (PERFORM) und globale Pass-2-Auflösung (CALL, COPY);
Reparse-Test verifiziert ID-Erhalt UND dass eine Kante aus einer
UNVERÄNDERTEN anderen Datei beim Reparse ihres Ziels nicht verloren geht
(Regressionstest für den oben dokumentierten dritten Bug); Lösch-Test
verifiziert, dass ein aus dem Quelltext entfernter Paragraph seine Entity
verliert, während Geschwister-Entities erhalten bleiben. Alle drei grün,
zusammen mit den 107 cobol-Tests: **110/110**. `pytest tests/ -k cobol`
lokal (`.venv-parser`, ohne DB) ebenfalls weiterhin grün.

**E-2 abgeschlossen:** Pass 0 trägt neben den Namen die Felddefinitionen der
Copybooks. `parse_program()` erbt die Felder jedes eindeutig aufgelösten COPY,
wendet `REPLACING` case-insensitiv auf Feld- und Gruppennamen an und erzeugt
USES-Kanten mit `copybook_path` + `target_qualified_name`. Pass 2 verbindet
diese pfadgenau mit der Copybook-Entity; mehrdeutige COPYs/Felder bleiben
unresolved („kein Raten"). Der End-to-End-Test prüft die Kante vom Paragraphen
in `MAIN.CBL` auf `FIELDS.SHARED-RECORD.SHARED-FIELD`. Gesamtsuite im
Parser-Container: **139/139 grün**.

**Abschluss 31.07.2026.** `backend/services/graph_retrieval.py` erweitert die
Vektor-Top-k deterministisch um Definition-Chunks von COPY-Zielen und CALL-
Aufrufern. Die Zuordnung läuft über Quelle, Pfad und Zeilenüberlappung auf allen
passenden Entity-Hierarchieebenen; ein hartes, konfigurierbares Tokenbudget
(deterministische 4-Zeichen-Näherung) begrenzt ausschließlich die Ergänzungen.
`backend/api/entities.py` liefert Fokusobjekt, Definition, gruppierte 1-Hop-
Nachbarschaft und Datei→Top-Level-Auflösung. `backend/api/callgraph.py` liefert
einen auf drei Hops und 500 Knoten begrenzten Graph sowie JSON-, CSV- und
GraphML-Export. Beide Router erzwingen Team- und Projektsichtbarkeit.

Zwei neue DB-Tests decken Resolve/Definition/Neighbor, Callgraph und alle drei
Exportpfade sowie Graph-Erweiterung und Budgetgrenze ab. Vollständige Backend-
Suite: **77 bestanden, 1 Ollama-abhängiger Test übersprungen**. `/jobs` gehört
zu NF-014 und ist kein Bestandteil der AP-4-Anforderungen F-030…032/F-041/F-043.

---

## Offene Punkte

**Erledigt am 31.07.2026** (siehe Abnahme-Session oben): Docker und pip stehen,
Erststart abgenommen, beide Testsuiten laufen, die Baseline ist gegen eine echte DB
per Autogenerate gegengeprüft (Delta leer).

**Weiterhin offen:**
- Ollama in der CI (siehe `@requires_ollama` oben) — Entscheidung steht aus.
- Der Erststart wurde auf dieser Maschine geprüft, nicht auf Kundenhardware; die
  Lasttests aus NF-010/AP-9 sind davon unberührt.
- `backend/api/projects.py::delete_project` liest das nicht existierende
  `Project.repository`-Attribut (`AttributeError` bei `DELETE /projects/{id}`) —
  vorbestehender Bug, bei AP-3 entdeckt, nicht mitgefixt (siehe AP-3-Abschnitt oben).
- E-3-Repack-Nachlauf (`git repack -a -d` + `fetch --refetch` nach der
  Erstindexierung) bleibt unimplementiert, bis ein echter großer Bestand zum
  Messen verfügbar ist.

**Testabdeckung, die beim Entkernen verloren ging** (neu zu schreiben, AP-8):
- Orphan-Schutz bei unvollständigem Scan (war `test_incomplete_scan_safety.py`,
  hing an Autodesk/Dalux) — die Logik existiert unverändert in `webdav.py`/`folder.py`
- Chunked-Download großer Dateien (war `test_large_file_streaming.py`) — Pfad existiert
  nur noch in `webdav.py`
- Re-Index-Link-Stabilität wurde auf den WebDAV-Connector portiert und ist erhalten

**Fachlich offen:**
- Realer COBOL-Beispielbestand fehlt (Plan §1.3, Punkt 4) — der Parser wird vorerst
  gegen selbst gebaute Fixtures entwickelt, die Erkennungsquote am echten Bestand
  bleibt bis dahin unbekannt
- Früherer COBOL-Parser-Ansatz ist nicht verfügbar → AP-2 rechnet mit dem oberen Ende
  der Schätzung
- Fujitsu-CI-Werte fehlen (NF-006) → Design-Tokens werden mit Platzhaltern gebaut
- BITV-Umfang nicht verbindlich (NF-012)

---

## Nächste Schritte

1. ~~**AP-2 starten**~~ — Fundament erledigt am 31.07.2026: `source_format.py` +
   `embedded.py` + `lexer.py`, siehe Abschnitt „AP-2 — Fundament" oben.
2. ~~**AP-2 weiter — Struktur**~~ — erledigt am 31.07.2026: `divisions.py` +
   `procedure.py` + `model.py`-Erweiterung, siehe Abschnitt „AP-2 — Struktur
   (divisions/procedure)" oben. Fixtures 09/10 angelegt.
3. ~~**AP-2 weiter**~~ — erledigt am 31.07.2026: `data_division.py` + `xref.py`
   + `model.py`-Erweiterung, siehe Abschnitt „AP-2 — Datenfelder
   (data_division/xref)" oben. Fixture 06 angelegt. Der quellenweite Feldindex
   über Copybook-Grenzen (E-2) bleibt bewusst offen, bis `copybook.py`/
   `parse.py` existieren — `xref.py` indiziert bisher nur programmlokal.
4. ~~**AP-2 weiter**~~ — erledigt am 31.07.2026: `copybook.py`, siehe Abschnitt
   „AP-2 — Copybooks (copybook)" oben. Fixtures 04/05 angelegt. Liefert nur
   die COPY-Kante + rohe REPLACING-Paare; der quellenweite Feldindex aus E-2
   bleibt weiterhin offen, bis `parse.py` Copybook-Dateien selbst als
   Entities parst (copybook.py selbst braucht das nicht, nur die spätere
   XREF-Nachauflösung).
5. ~~**AP-2 weiter**~~ — erledigt am 31.07.2026: `sql.py`, siehe Abschnitt
   „AP-2 — SQL (sql)" oben. Fixture 07 angelegt. Liefert `SqlBlock` (Typ,
   Tabellen/Views, Host-Variablen, Cursor-Name) + USES-Kanten gegen den
   programmlokalen Datenfeld-Index; quellenweite Auflösung über Copybook-
   Grenzen bleibt wie bei xref.py bis `parse.py` offen (E-2).
6. ~~**AP-4 vorgezogen**~~ — erledigt am 31.07.2026: `chunking.py`, siehe
   Abschnitt „AP-4 (vorgezogen) — Chunking (chunking)" oben. **Korrektur:**
   gehört laut §6.6/§13 zu AP-4, nicht AP-2 (§6.2 legt nahe, es sei Teil des
   Parser-Package-Layouts — das ist ein Widerspruch im Plan, aufgelöst in
   docs/ENTSCHEIDUNGEN.md E-6). Für AP-2 zählt dieser Schritt nicht mit.
7. ~~**AP-2 letzter Schritt**~~ — erledigt am 31.07.2026: `parse.py`
   (`parse_program()`) + Golden-File-Testkorpus (`99_garbage.cbl`,
   `golden/*.json`, CI-Job `parser-golden`), siehe Abschnitt „AP-2 —
   Orchestrierung und Testkorpus (parse.py)" oben. **AP-2 ist damit fertig.**
8. ~~**AP-3**~~ — erledigt am 31.07.2026: `parser/git_utils.py` (Bare-Mirror +
   Worktrees) + Neubau `parser/connectors/git.py`, `SourceScanFile` als
   Wiederaufsetz-Journal (NF-004), siehe Abschnitt „AP-3 — Monorepo-Git-
   Konnektor" oben. **AP-3 ist damit fertig.**
9. ~~**AP-4 Pass 0-2**~~ — erledigt am 31.07.2026: Copybook-Index
   (`connectors/git.py::_build_copybook_index`), Entity-/Kanten-Persistenz
   (`parser/cobol_persist.py`, neu, UPSERT mit ID-Erhalt), globale
   Nachauflösung (`parser/tasks/edge_resolver.py`, neu), `parse_copybook()`
   für eigenständige Copybook-Entities (E-2) — siehe Abschnitt „AP-4 —
   Entity-/Kanten-Persistenz + Nachauflösung + Retrieval" oben. GOTO-
   Kommentar-Nachzug mitgezogen (`backend/models/database.py` +
   `parser/models/database.py`, weiterhin byte-identisch).
10. ~~**AP-4 abschließen**~~ — erledigt am 31.07.2026: quellenweite
    XREF-Vererbung über COPY-Grenzen, F-043 (graph-erweitertes Retrieval)
    und die Backend-Router `/entities`, `/callgraph`.
11. **AP-5 abgeschlossen** — Code-Dateien werden über `/entities/resolve` einem
    Fokusobjekt (`program`/`copybook`) zugeordnet; der Fokus liegt getrennt je
    Panel. Ein Klick auf eine Monaco-Entity wechselt nur den Fokus und springt
    nicht mehr zur Definitionszeile. Das Referenzen-Menü liest
    `/entities/{id}/neighbors`, gruppiert CALL/COPY/READS/WRITES/PERFORM/GOTO/USES
    semantisch und zeigt bei ungeparsten Dateien einen Hinweis. Der Gutter-Klick
    erzeugt außerdem eine strukturierte Zeilenreferenz (Datei, Zeile, Quelle,
    Programm/Section/Paragraph), übernimmt den Zeilentext in den RAG-Kontext und
    persistiert sie beim Senden in `metadata_json.refs[]`. Der Chip in der
    Chat-Historie öffnet Datei und Zeile wieder. TypeScript und Vitest grün;
    AP-5 ist damit abgeschlossen.

    **Deployment-Verifikation:** Images für Backend, Parser und Frontend wurden
    nach dem AP-5-Schnitt mit `docker compose up -d --build` neu gebaut. Alle
    sieben Services waren anschließend healthy; `/health` meldete DB, Redis und
    Ollama `ok`, das Frontend antwortete mit HTTP 200.

12. **AP-6 abgeschlossen** — `frontend/components/CallGraphView.tsx` ist als
    eigener Workspace-Paneltyp angebunden. Die Ansicht lädt den vorhandenen,
    sichtbarkeitsgeschützten Backend-Fokusgraphen inkrementell mit 1–3 Hops,
    filtert CALL/PERFORM/GOTO/COPY, markiert unaufgelöste und dynamische Kanten
    gestrichelt und navigiert von Knoten zurück in den Code. JSON-, CSV- und
    GraphML-Export verwenden `/callgraph/export`; die 500-Knoten-Grenze wird
    angezeigt. `npx tsc --noEmit`, Vitest und der produktive Next-Build sind grün;
    der gezielte Backend-Test `test_ap4_graph_api.py` für Fokus und alle drei
    Exportformate ist ebenfalls grün. Als Nächstes: **AP-7 Design-Tokens,
    Job-Center und i18n-Nachzug**.

13. **Parser-Bugfix für wiederholte COBOL-FILLER** — mehrere `FILLER` unter
    derselben Gruppe erzeugten denselben `qualified_name` und brachen den
    Repository-Erstsync an `uq_code_entities_source_qname`; der danach gemeldete
    Pending-Rollback war nur der Folgefehler des fehlgeschlagenen Flushs.
    `_build_field_entities()` vergibt nun einen internen, zeilenstabilen Schlüssel
    (`…FILLER@<start_line>`, bei mehreren Einträgen derselben Zeile zusätzlich
    `#<n>`), während der sichtbare Name `FILLER` bleibt. XREF ignoriert FILLER
    weiterhin fachlich. Ein Regressionstest bildet zwei FILLER in
    `WS-REPORT-HEADER` nach; die COBOL-Suite bleibt mit 110/110 ausgewählten Tests
    grün.

14. **Codeöffnung aus der globalen Suche korrigiert** — Entity-Suchtreffer
    enthielten bisher keine `source_id`. Bei Code aus einer eigenständigen
    Git-Wissensquelle fiel das Frontend deshalb fälschlich auf den alten
    projektgebundenen Repository-Endpunkt zurück und zeigte „Datei konnte nicht
    geladen werden“. `services/search.py` liefert die Quellen-ID nun im
    `node_meta`; die Entity-Navigation reicht sie an
    `/knowledge-sources/{id}/content` durch. Der alte `repo_id`-Pfad bleibt als
    Fallback für klassische Projekt-Repositories erhalten. Der Backend-Test prüft
    Dateipfad und Quellen-ID im Suchtreffer; TypeScript und Vitest sind grün.

15. **Editor-Ruler und Referenzsprung korrigiert** — die fünf Monaco-Ruler an
    den COBOL-Grenzen 6/7/11/72/80 liefen als vertikale Linien durch den Code
    und sind entfernt; die COBOL-Zonen bleiben im kompakten Lineal oberhalb des
    Editors sichtbar. Beim Sprung aus dem Referenzen-Menü verwendet der lokale
    Code-Panel-Lader nun die `source_id` der Ziel-Entity und liest CBL-Dateien
    aus dem richtigen Git-Worktree. Auch die ältere Projekt-Referenzantwort
    liefert und übergibt die Quellen-ID für Entity- und Dokumentziele.
    TypeScript und Vitest sind grün.

16. **AP-7 begonnen — Job-Center (NF-014)** — der persistente Activity-Button
    im Workspace-Header pollt alle drei Sekunden `/jobs`, zeigt die Zahl laufender
    Vorgänge per Badge und bündelt sichtbare Quellen-Syncs, Link-Builder- und (nur
    für Superuser) Diagnose-Läufe. Fehlerdetails sind aufklappbar; fehlgeschlagene
    Vorgänge lassen sich wiederaufnehmen. Run-basierte Jobs erzeugen dabei einen
    neuen Run, damit die Fehlerhistorie erhalten bleibt. Ausgabe und Wiederaufnahme
    respektieren Team-/Projekt-Sichtbarkeit. Die Oberfläche ist deutsch/englisch
    nachgezogen und meldet die aktive Anzahl per `aria-live`. TypeScript und Vitest
    sind grün. Der Produktions-Build scheitert in der abgeschotteten Umgebung nur
    am bestehenden Online-Abruf der drei Google-Fonts. In AP-7 verbleibt die
    Design-Token-Migration samt CI-Verbot harter Farbwerte.
