# Doctus — Entscheidungslog

Fachliche/technische Festlegungen, die der Implementierungsplan offen gelassen hat.
Eine Zeile pro Entscheidung, mit Begründung und Fundstelle im Code. Wer eine
Entscheidung revidiert, ändert hier den Eintrag — nicht nur den Code.

| ID | Thema | Entscheidung | Status |
|----|-------|--------------|--------|
| E-1 | Kanten-Nachauflösung | `code_edges.scope_entity_id` eingeführt | umgesetzt |
| E-2 | XREF über Copybook-Grenzen | quellenweiter Feldindex, REPLACING wird mitgeführt | entschieden, offen in AP-2 |
| E-3 | Partial Clone vs. Offline | `--filter=blob:none` nur bei erreichbarem Remote | umgesetzt, Repack-Nachlauf offen |
| E-4 | `sql_block` als Entity-Typ | ja, achter Typ (D-1 aus dem Plan) | umgesetzt |
| E-5 | Login-Sperre bei Redis-Ausfall | zwei Zähler: Redis (Name+IP) und DB (Nutzer), der höhere gilt | umgesetzt |
| E-6 | AP-2/AP-4-Grenze (chunking.py, parse.py-Umfang) | §6.6/§13 verbindlich: chunking.py = AP-4, parse.py = nur `parse_program()` In-Memory, Pass 0-2 = AP-4 | umgesetzt |
| E-7 | GPL-Transitivabhängigkeit `Unidecode` (über `mcp-atlassian`) | Optionen dokumentiert, Freigabe/Entfernung steht beim Auftraggeber aus | **offen, Release-Blocker** |

---

## E-1 — Programmlokale Kanten dürfen nicht global aufgelöst werden

**Problem.** Der Plan (§5.4/§6.4) löst offene Kanten im Nachlauf-Pass über
`UPDATE code_edges SET dst_entity_id = … WHERE dst_name = code_entities.name` auf.
Das ist für `CALL` richtig (PROGRAM-IDs sind im Bestand eindeutig), aber falsch für
`PERFORM`, `GO TO` und `USES`: Paragraphennamen wie `INIT-PARA` oder Feldnamen wie
`WS-STATUS` existieren in hunderten Programmen. Ein globaler Join verdrahtet den
Call-Graph quer über Programmgrenzen — und zwar still, ohne Fehler.

**Entscheidung.** `code_edges` bekommt `scope_entity_id`: die Entity, innerhalb derer
ein Name aufgelöst werden darf (in der Regel das Programm). Der Nachlauf-Pass ist
zweigeteilt:

- **global** (`scope_entity_id IS NULL`): `CALL`, `COPY` → Auflösung über
  `source_id` + `dst_name`
- **lokal** (`scope_entity_id` gesetzt): `PERFORM`, `GO TO`, `USES`, `DEFINES` →
  Auflösung nur gegen Entities mit demselben `parent`-Baum

Programmlokale Kanten sind damit schon beim Parsen auflösbar und brauchen den
Nachlauf-Pass gar nicht — der bleibt für die echten Cross-Program-Kanten.

**Fundstelle.** `backend/models/database.py::CodeEdge.scope_entity_id`,
Index `ix_code_edges_scope_name`.

---

## E-2 — XREF endet nicht an der Copybook-Grenze

**Problem.** Regel 1 des Plans (§6.1) ist richtig: Copybooks werden nie in den
Programmtext expandiert, sonst verschieben sich alle Zeilennummern. Nur baut
`xref.py` seinen Namensindex aus den `DataItem`s **des Programms** — Felder, die
aus einem Copybook stammen (in COBOL-Beständen die Mehrheit), stehen nicht darin.
F-025 („Verwendungsstellen von Datenfeldern") wäre damit nur halb erfüllt.

**Entscheidung.** Der Namensindex wird quellenweit aufgebaut, nicht programmlokal:

1. Copybooks werden als eigene Entities mit eigenen `data_item`-Kindern geparst
   (Zeilennummern beziehen sich auf die **Copybook**-Datei — dort gehören sie hin).
2. Ein Programm mit `COPY X` erbt für die XREF-Auflösung den Feldindex von `X`,
   ohne dass Text expandiert wird. Die entstehende `USES`-Kante zeigt vom
   Paragraphen (im Programm, mit Programm-Zeilennummer) auf das `data_item`
   (im Copybook, mit Copybook-Zeilennummer). Genau dafür trägt jede Kante
   ihre eigene `src_start_line`.
3. `COPY … REPLACING` wird in `code_edges.meta_json.replacing` mitgeführt; die
   Auflösung wendet die Ersetzung auf die geerbten Feldnamen an, bevor sie matcht.
   Ist die Ersetzung nicht eindeutig anwendbar, bleibt die Kante `unresolved` —
   kein Raten.

**Offen bis AP-2.** Mengengerüst prüfen: XREF ist laut Risiko R5 die volumenstärkste
Kantenart; falls die Zeilenzahl explodiert, auf 01-Level-Gruppen aggregieren.

---

## E-3 — Partial Clone nur, solange der Remote erreichbar ist

**Problem.** §7.2 klont mit `--filter=blob:none`. Ein Partial Clone lädt Blobs erst
beim Zugriff nach — das braucht dauerhaft eine Verbindung zum Git-Server. In einer
abgeschotteten Umgebung (NF-002) oder wenn der Server wegfällt, brechen
Worktree-Operationen ohne offensichtlichen Zusammenhang zur Ursache.

**Entscheidung.** Der Filter wird konfigurierbar statt fest verdrahtet:

- `DOCTUS_GIT_PARTIAL_CLONE=1` (Default): `--filter=blob:none`, spart bei der
  Erstindexierung eines Monorepos den Großteil des Transfers.
- `DOCTUS_GIT_PARTIAL_CLONE=0`: vollständiger Blob-Transfer beim Klonen, danach
  ist der Bare-Store autark. Das ist die Einstellung für Deployments, in denen der
  Git-Server nach der Erstindexierung nicht mehr erreichbar ist.

Zusätzlich: nach Abschluss der Erstindexierung optional `git repack -a -d` +
`git fetch --refetch` zum „Auffüllen". Wird in AP-3 gemessen, nicht vorab entschieden.

**Stand 31.07.2026.** Der Schalter ist umgesetzt: `DOCTUS_GIT_PARTIAL_CLONE`
(Default `1`) steuert `--filter=blob:none` in `parser/git_utils.py`
(`ensure_bare_mirror`/`fetch_branch`). Der optionale Repack-Nachlauf bleibt
offen — er sollte laut diesem Eintrag selbst erst an einem echten großen
Bestand gemessen werden, und der fehlt weiterhin (Plan §1.3, Punkt 4).

**Fundstelle.** `parser/git_utils.py::PARTIAL_CLONE`, `ensure_bare_mirror()`, `fetch_branch()`.

---

## E-4 — `sql_block` ist ein Entity-Typ

Der Plan stellt die Frage in §5.3 (D-1) selbst: F-032 verlangt Kanten
`SQL-Block → Datenfeld (USES)`, eine Kante braucht auf beiden Seiten einen Knoten.

**Entscheidung.** `sql_block` wird als achter Entity-Typ geführt. Er ist nicht
fokussierbar im Sinne von F-067 (kein eigenes Fokus-Objekt im Editor), existiert
aber als Kantenendpunkt und als Kontext-Träger für F-027.

**Fundstelle.** Typ-Kommentar an `CodeEntity.type`.

---

## E-5 — Die Login-Sperre darf nicht an Redis hängen

**Problem.** §11 des Plans schreibt für das Rate-Limit einen „Redis-Zähler pro
(username, IP)" vor. Redis ist in dieser Architektur aber ein Cache-artiger Dienst:
er wird neu gestartet, geflusht, läuft in kleinen Deployments auch mal gar nicht.
Hängt die Sperre allein daran, ist sie mit einem Neustart des Containers aufgehoben —
und wer Passwörter durchprobiert, muss nur warten, bis jemand deployt.

**Entscheidung.** Zwei Zähler, deren höherer Wert gilt:

- **Redis, pro (Benutzername, IP)**, Zeitfenster 15 Minuten. Greift auch für
  *unbekannte* Benutzernamen — sonst bliebe das Durchprobieren von Namen ungebremst,
  und am unterschiedlichen Sperrverhalten wäre ablesbar, welche Konten existieren.
- **DB, pro Nutzer** (`users.failed_login_count` / `users.locked_until`). Dauerhaft,
  überlebt jeden Redis-Neustart, ist die Sperre, die ein Administrator im Users-Tab
  sieht.

Das Entsperren räumt **beide** Seiten ab (`login_throttle.clear_user()`, SCAN über alle
IP-Buckets dieses Namens). Nur die DB-Spalten zu leeren genügt nicht: die Redis-Sperre
liefe unabhängig weiter, der Nutzer bekäme bis zum Ablauf der TTL weiter 423 — und die
Verwaltung meldete „entsperrt". Genau so gefunden bei der Erststart-Abnahme.

Backoff: 5 Fehlversuche frei, ab dem 6. Sperre von 60 s mit Verdopplung je weiterem
Fehlversuch, **gedeckelt bei 1 h**. Der Deckel ist kein Komfort, sondern eine
Sicherheitsentscheidung: ohne ihn wäre ein Konto nach ~20 Versuchen praktisch
dauerhaft gesperrt — ein Denial-of-Service gegen jeden, dessen Benutzernamen man kennt.

Fällt Redis aus, bleibt die DB-Sperre allein wirksam: die Anmeldung wird dadurch nie
unmöglich, aber auch nie ungebremst.

**Fundstelle.** `backend/core/login_throttle.py`, Verwendung in `backend/api/auth.py::login`.

---

## E-6 — Wo AP-2 endet und AP-4 beginnt

**Problem.** Der Plan widerspricht sich an zwei Stellen darüber, was noch zu
AP-2 gehört und was schon AP-4 ist:

1. **`chunking.py` (F-041).** §6.2 (Package-Layout von `parser/cobol/`)
   zeichnet `chunking.py` als eines von elf Modulen direkt neben `sql.py`/
   `xref.py` — liest sich wie Teil des Parsers. §6.6 (Aufwandsschätzung AP-2,
   7,5 PW) listet die AP-2-Teilstücke einzeln auf (`source_format+lexer+
   embedded`, `divisions+procedure`, `data_division+xref`, `copybook`, `sql`,
   `Testkorpus+Golden Files+CI`) — `chunking` fehlt darin. §13 (Arbeitspakete-
   Tabelle) ordnet F-041 explizit **AP-4** zu („Entity-/Kanten-Persistenz +
   Nachauflösung + Retrieval", F-030…032/F-041/F-043), während AP-2 („COBOL-
   Parser + Testkorpus") nur F-020…034 exklusive F-041 trägt.
2. **`parse.py` / Pass 0-2.** §6.4 beschreibt Pass 1 als „pro Datei: parse →
   Entities/Kanten/Chunks **persistieren**" und Pass 2 als DB-`UPDATE` zur
   Kanten-Nachauflösung — beides deckungsgleich mit dem AP-4-Titel „Entity-/
   Kanten-Persistenz + Nachauflösung". §6.3 zeigt dagegen die Parser-Pipeline
   als reine In-Memory-Kette bis `ParseResult { entities[], edges[], chunks[],
   errors[] }` — kein DB-Zugriff im Diagramm. Auch die Signatur
   `parse_program(text, path, copybook_index) -> ParseResult` (§6.2-Kommentar)
   nimmt den Copybook-Index als fertigen Parameter entgegen, baut ihn also
   nicht selbst — Pass 0 (der Repo-weite `*.cpy`-Scan, der diesen Index
   erzeugt) ist damit schon durch die Signatur von `parse_program()`
   entkoppelt.

Punkt 1 fiel erst auf, nachdem `chunking.py` schon gebaut, getestet und
committet war (`fcaaba2`) — der Code selbst ist davon nicht betroffen, aber
„ist AP-2 abgeschlossen?" ließ sich ohne diese Klärung nicht sauber
beantworten.

**Entscheidung.** §6.6/§13 sind die verbindliche Quelle für AP-Grenzen (sie
sind die Aufwands-/Abhängigkeitsplanung; §6.2/§6.4 sind Architektur-Skizzen,
keine Scope-Definition). Damit gilt:

- `chunking.py` zählt zu **AP-4**, wurde aber vorgezogen gebaut, weil es
  ausschließlich von `CobolProgram`/`Paragraph`/`Section` aus `model.py`
  abhängt (keine DB-Anbindung nötig) — reine Reihenfolge-Optimierung, keine
  Scope-Änderung.
- `parse.py` gehört für AP-2 nur mit seiner **In-Memory-Funktion**
  `parse_program(text, path, copybook_index) -> ParseResult` dazu (eine
  Datei, kein DB-Zugriff) — testbar 1:1 gegen die Golden Files aus §6.6.
  Pass 0 (Repo-Scan für den Copybook-Index), Pass 1 (Persistieren) und
  Pass 2 (Nachauflösungs-`UPDATE`) sind **AP-4**-Orchestrierung, die
  `parse_program()` als Baustein aufruft, nicht umgekehrt.

AP-2 ist damit abgeschlossen, sobald `parse_program()` existiert **und** das
Testkorpus-Teilstück aus §6.6 steht (`99_garbage.cbl`, `golden/*.json`,
CI-Job `parser-golden`) — nicht erst mit Pass 0-2/DB-Anbindung.

**Fundstelle.** `docs/UMSETZUNGSSTAND.md`, Abschnitte „AP-4 (vorgezogen) —
Chunking (chunking)" und „Nächste Schritte" tragen einen Verweis hierher.

---

## E-7 — `Unidecode` ist GPL, verstößt gegen die „nur MIT/BSD/Apache-2.0"-Regel

**Problem.** Der AP-9-Lizenzbericht (`docs/OSS-CLEARING.md`) hat gezeigt: das
Paket `mcp-atlassian` (Confluence-/Jira-Konnektor, AP-3/AP-8) zieht
`Unidecode>=1.3.0` als Pflichtabhängigkeit nach — nicht Doctus-eigener Code,
aber jedes `pip install -r backend/requirements.txt` installiert es
automatisch mit. Das PyPI-Paket `Unidecode` steht unter GPL-2.0-or-later
(bestätigt über `Unidecode-1.4.0.dist-info/METADATA`, `License: GPL`). Das
ist Copyleft und verstößt gegen CLAUDE.md Architekturprinzip 2 („strikt Open
Source. Nur MIT/BSD/Apache-2.0"). `mcp-atlassian` selbst ist MIT-lizenziert
und unproblematisch — nur diese eine Transitivabhängigkeit ist es nicht.

**Was `Unidecode` innerhalb von `mcp-atlassian` tut:** Transliteration von
Nicht-ASCII-Zeichen (z.B. für Dateinamen/Slugs beim Export von
Confluence-/Jira-Inhalten) — keine Kernfunktion, aber ohne Fork/Patch von
`mcp-atlassian` nicht entfernbar, weil pip die Abhängigkeit erzwingt.

**Optionen (keine davon bisher umgesetzt):**

1. **Bei `mcp-atlassian` bleiben, GPL-Ausnahme akzeptieren.** Rechtlich wäre
   das für ein On-Premise-Produkt, das nicht selbst als abgeleitetes Werk von
   `Unidecode` weitergegeben wird, vermutlich vertretbar (reine
   Laufzeit-Abhängigkeit, kein verlinkter/kompilierter Code) — aber das ist
   eine Rechtsfrage, keine technische, und widerspricht der expliziten
   Auftraggeber-Vorgabe „nur MIT/BSD/Apache-2.0" wörtlich. Braucht Fujitsu/DRV-Freigabe.
2. **`mcp-atlassian` durch eine eigene, schlankere Confluence-/Jira-Anbindung
   ersetzen** (nur die tatsächlich genutzten REST-Endpunkte, `httpx` statt
   der fertigen Bibliothek) — vermeidet die Transitivabhängigkeit komplett,
   kostet aber Implementierungs- und Testaufwand (AP-3/AP-8 müssten die
   Confluence-/Jira-Konnektor-Tests neu gegen die eigene Anbindung fahren).
3. **Confluence-/Jira-Konnektor vorerst deaktivieren/als experimentell
   markieren**, bis Option 1 oder 2 entschieden ist — vermeidet den
   Lizenzverstoß im Auslieferungsumfang, nimmt aber F-011/F-012 aus dem
   Release.

**Entscheidung.** Noch offen — braucht eine Rückmeldung des Auftraggebers
(Fujitsu/DRV), da es eine Compliance-/Rechtsfrage ist, keine technische. Der
CI-Job `licenses` (`scripts/check_licenses_python.py`,
`scripts/license_exceptions_python.json`) markiert `Unidecode` deshalb bereits
jetzt als `"blocking": true` und lässt den Job bewusst rot, bis hier
entschieden ist — **Release-Blocker**.

**Fundstelle.** `docs/OSS-CLEARING.md` Abschnitt 1, `scripts/license_exceptions_python.json`.
