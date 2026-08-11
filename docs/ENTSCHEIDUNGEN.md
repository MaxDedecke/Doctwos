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
| E-7 | GPL-Transitivabhängigkeit `Unidecode` (über `mcp-atlassian`) | MIT-Shim-Paket ersetzt die GPL-Abhängigkeit vollständig (`backend/vendor/unidecode_shim/`) | umgesetzt (08.08.2026) |
| E-8 | Embedding-Batchgröße vs. CPU-only-Timeout (`ollama_client.py`) | Option 3: Sub-Batches + konfigurierbarer Timeout | umgesetzt |
| E-9 | AP-9-Abschluss ohne Kundenzugang | drei Punkte aus dem AP-9-Scope genommen, an Auftraggeber übergeben (siehe unten) | entschieden |
| E-10 | Confluence/Jira-MCP-Anbindung: Cloud-vs-Server/DC-Erkennung | eigene Domain-Suffix-Heuristik statt Import aus `mcp_atlassian.utils` | umgesetzt (08.08.2026) |

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

**Optionen (Stand vor der Lösung):**

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
4. **Ein eigenes MIT-Shim-Paket namens `unidecode` unterschieben, statt das
   echte PyPI-Paket zu installieren** — siehe „Entscheidung" unten. Kleiner
   Aufwand als Option 2 (kein Fork von `mcp-atlassian`, keine Neuimplementierung
   des Connectors), löst den Verstoß aber tatsächlich auf statt ihn wie
   Option 1 nur zu akzeptieren.

**Entscheidung (08.08.2026): Option 4 umgesetzt.** Recherche ergab: `Unidecode`
wird innerhalb von `mcp-atlassian` (geprüft gegen den gepinnten Stand
`0.22.1` **und** die aktuellste PyPI-Version `0.23.0` — die Abhängigkeit
besteht dort unverändert fort) an genau einer Stelle benutzt —
`mcp_atlassian/jira/users.py::normalize_text()`, ASCII-Transliteration für
den fuzzy Jira-Assignee-Namensabgleich, sonst nirgends im Paket, auch nicht
in den Confluence-Modulen. Diese eine Funktion wurde als eigenständiges,
MIT-lizenziertes Modul unter `backend/vendor/unidecode_shim/` nachgebaut (nur
Python-Stdlib, `unicodedata`-NFKD-Zerlegung + kleine Tabelle für die
Buchstaben ohne Kompatibilitätszerlegung wie „ł"/„ø"/„đ" — kein Code aus dem
GPL-Original eingesehen oder übernommen). Das Shim-Paket heißt bewusst exakt
`unidecode`, damit `pip` `mcp-atlassian`s `unidecode>=1.3.0`-Anforderung
dagegen auflöst, statt das echte Paket von PyPI zu laden — verifiziert per
isoliertem venv-Test: `pip install` von `mcp-atlassian==0.22.1` neben dem
Shim installiert das echte `Unidecode` nachweislich nicht, `pip-licenses`
meldet danach `unidecode`/MIT statt `Unidecode`/GPL-2.0-or-later, und
`mcp_atlassian.jira.users.normalize_text("Łódź")` liefert weiterhin korrekt
`"lodz"`. **Ergebnis: kein GPL-Code mehr in Abhängigkeitsbaum oder Image,
`mcp-atlassian` selbst bleibt unverändert/upgradebar, kein Fork nötig.**
Details, Fidelity-Trade-off (nur lateinische Diakritika abgedeckt, kein
Kyrillisch/CJK — irrelevant für den DRV-Piloten) und Vorgehen bei künftigen
`mcp-atlassian`-Versionsbumps: `backend/vendor/unidecode_shim/README.md`.
Der `Unidecode`-Eintrag in `scripts/license_exceptions_python.json` wurde
entfernt (nicht mehr nötig — das Shim-Paket erfüllt die normale Allowlist
direkt über `MIT`), CI-Job `licenses` ist damit **grün**, kein Release-Blocker
mehr. Diese Lösung brauchte keine Auftraggeber-Rückmeldung, weil sie den
GPL-Code komplett entfernt statt eine Ausnahme für ihn zu erbitten.

**Fundstelle.** `docs/OSS-CLEARING.md` Abschnitt 1, `scripts/license_exceptions_python.json`,
`backend/vendor/unidecode_shim/`.

---

## E-8 — Embedding-Batchgröße vs. CPU-only-Timeout

**Problem.** Der AP-9-Lasttest mit einem synthetischen Ersatzkorpus (1200
Programme + 250 Copybooks, `scripts/generate_synthetic_cobol_corpus.py`) hat
gezeigt: `ollama_client.get_embeddings_batch()` schickt alle Chunks eines
Dokuments in einem Request, mit einem fest verdrahteten 120-s-Timeout und
3 Retries. Ein Batch von 300 Chunks lief bei CPU-only-`bge-m3` (keine GPU in
dieser Testumgebung, aber auch bei kleineren On-Premise-Kunden ohne GPU
realistisch) in allen drei Versuchen in den Timeout. Ein Batch von 20 Chunks
lief durch, brauchte aber 18,34 s (≈1,1 Chunks/s) — bei einem großen
Copybook/Programm mit entsprechend vielen Chunks reicht auch das nicht immer.
CLAUDE.md verlangt „On-Premise per Default" und „Skalierung by Default" für
100-GB-Bestände — ein Sync, der bei großen Dateien in Timeout-Retry-Schleifen
hängen bleibt statt nur langsamer zu sein, verletzt beides stiller als ein
offensichtlicher Fehler.

**Optionen:**

1. **Batchgröße dynamisch klein halten** (z. B. an Chunk-Anzahl oder
   Zeichensumme gekoppelt, in mehrere Requests aufteilen) — löst das
   Timeout-Problem strukturell, kostet mehr Roundtrips bei kleinen
   Dokumenten.
2. **Timeout großzügiger/konfigurierbar machen** (z. B. über eine
   Umgebungsvariable, analog zu `COMPLIANCE_LLM_TIMEOUT`) — einfacher
   Eingriff, verschiebt das Problem nur (irgendein Dokument ist immer groß
   genug, den neuen Wert wieder zu reißen), macht aber den worst case
   konfigurierbar statt hart zu blockieren.
3. **Beides kombinieren** — sinnvolle Obergrenze für die Batchgröße plus ein
   Timeout, der zur tatsächlich gemessenen CPU-Embedding-Rate passt
   (≈1,1 Chunks/s in dieser Umgebung; variiert mit Kundenhardware).

**Entscheidung.** Option 3 umgesetzt (AP-9-Abschluss): `get_embeddings_batch()`
teilt Texte jetzt selbst in Sub-Batches von maximal `EMBED_BATCH_MAX_CHUNKS`
(Default 20, orientiert an der gemessenen sicheren Größe) auf und ruft für
jeden Sub-Batch einzeln `/api/embed` auf; der bisher fest verdrahtete
120-s-Timeout ist über `EMBED_BATCH_TIMEOUT` konfigurierbar. Beide Werte sind
env-steuerbar (Docker-Compose-kompatibel wie `COMPLIANCE_LLM_TIMEOUT`), damit
sie sich ohne Codeänderung an gemessene Kundenhardware anpassen lassen. Das
ist eine technische Entscheidung innerhalb bestehender Architekturprinzipien
(keine neue Abhängigkeit, keine Kundendaten nötig) — anders als die formale
Lasttest-Abnahme selbst, die einen echten Bestand braucht (siehe
`docs/UMSETZUNGSSTAND.md` Abschnitt „AP-9 — Abschluss").

**Fundstelle.** `parser/ollama_client.py::get_embeddings_batch`,
`parser/tests/test_ollama_client.py`, `docs/UMSETZUNGSSTAND.md` Abschnitt
„AP-9 — Härtung".

---

## E-9 — AP-9-Abschluss ohne Kundenzugang: was bleibt offen, was wird jetzt gefixt

**Problem.** AP-9 (Härtung) hatte laut `docs/UMSETZUNGSSTAND.md` vier offene
Punkte: formale Lasttest-Abnahme am echten DRV-Bestand, BITV-Abnahme,
Farbkontrast-Nachbesserung, Abschlussdokumentation. Drei davon lassen sich in
dieser Session nicht abschließend erledigen — nicht aus technischen Gründen,
sondern weil die dafür nötige Autorität/Datenlage außerhalb des
Implementierungsauftrags liegt:

1. **Formale Lasttest-Abnahme am echten Bestand.** Braucht Zugriff auf
   echte(n) DRV-COBOL-Bestand(e) — liegt nicht vor und kann nicht ad hoc
   beschafft werden (Plan §1.3 Punkt 4, seit AP-2 offen). Der synthetische
   Ersatzkorpus-Lauf (`scripts/generate_synthetic_cobol_corpus.py`, siehe
   AP-9-Lasttest-Abschnitt in `docs/UMSETZUNGSSTAND.md`) bleibt der bestmögliche
   Ersatz, ersetzt aber keine Abnahme.
2. **BITV-Abnahme.** Der automatisierte axe-core-Basis-Check (WCAG2A/AA,
   `frontend/e2e/accessibility.spec.ts`) ist fertig und deckt automatisiert
   prüfbare Regeln ab — eine *formale* BITV-Abnahme braucht aber einen vom
   Auftraggeber festgelegten, verbindlichen Prüfumfang (Plan-Risiko R6, NF-012)
   und typischerweise eine akkreditierte Prüfstelle für den manuellen Teil.
   Beides liegt außerhalb dessen, was in dieser Session festgelegt werden kann.
3. **Farbkontrast-Nachbesserung.** Bereits in `docs/UMSETZUNGSSTAND.md`
   („Bewusst nicht mitgefixt — Farbkontrast") als Design-Entscheidung
   eingestuft: welcher Fujitsu-Markenton wie weit verschoben wird, ohne den
   CI-Look zu brechen, braucht eine Freigabe der Markenverantwortlichen, ist
   nicht aus dem Code oder von einem Implementierungsagenten allein
   ableitbar.

**Was stattdessen jetzt umgesetzt wurde (kein Kundenzugang nötig, rein
technische Entscheidungen innerhalb bestehender Prinzipien):**
- npm-CVE-Fixes im Frontend (`next` 16.2.10→16.2.12, `sharp`-Override auf
  `^0.35.3`, `brace-expansion` über `npm audit fix`) — `npm audit` meldet
  danach 0 Vulnerabilities; TypeScript, Vitest (4/4) und Produktions-Build
  grün.
- E-8 (Embedding-Batchgröße/Timeout) umgesetzt, siehe oben.
- Abschlussdokumentation (`docs/ABSCHLUSS.md`) geschrieben.

**Entscheidung.** AP-9 gilt damit als für den Implementierungsauftrag
abgeschlossen. Die drei liegen gebliebenen Punkte sind keine Bugs und keine
vergessene Arbeit, sondern strukturell außerhalb dessen, was ohne
Auftraggeber-Zugriff (Kundendaten, formaler Prüfumfang, Markenfreigabe)
erledigt werden kann — sie werden als Übergabepunkte an Fujitsu/DRV
dokumentiert statt den Plan offen zu halten, bis sie irgendwann verfügbar
werden. E-7 (GPL-`Unidecode`) war unabhängig davon ein eigener,
dokumentierter Release-Blocker — inzwischen (08.08.2026) durch das
MIT-Shim-Paket gelöst, siehe oben, keine Auftraggeber-Rückmeldung mehr nötig.

**Fundstelle.** `docs/IMPLEMENTIERUNGSPLAN.md` §13 (AP-9-Zeile),
`docs/UMSETZUNGSSTAND.md` Abschnitt „AP-9 — Abschluss", `docs/ABSCHLUSS.md`.

## E-10 — Confluence/Jira-MCP-Anbindung: on-prem (Server/Data Center) nachgezogen

**Anlass.** Pilot-Vorbereitung (Confluence on-prem + Bitbucket-COBOL-Repo)
deckte auf: `backend/mcp_client.py`s `init_mcp_clients_for_sources` baute für
Confluence/Jira ausschließlich Cloud-Env-Vars (`*_USERNAME`+`*_API_TOKEN`) und
hängte an jede Confluence-URL bedingungslos `/wiki` an — der Code-Kommentar
sagte das explizit ("Cloud auth only"). `parser/connectors/confluence.py`
(REST-Indexierung) war davon nicht betroffen, war schon on-prem-tauglich.

**Problem.** `mcp-atlassian` unterstützt Server/Data Center längst (eigene
`from_env()`-Logik pro Produkt: `CONFLUENCE_PERSONAL_TOKEN`/
`JIRA_PERSONAL_TOKEN` ohne Username, oder Username+API-Token als Fallback;
kein `/wiki`-Zwang außerhalb von Cloud) — unser eigener Aufrufcode hat das nur
nie genutzt.

**Frage, die eine Entscheidung brauchte:** wie erkennen wir Cloud vs.
Server/DC aus der gespeicherten `KnowledgeSource.url`? Zwei Optionen:

1. `mcp_atlassian.utils.urls.is_atlassian_cloud_url` direkt importieren und
   wiederverwenden — garantiert exakte Übereinstimmung mit dem, was
   `mcp-atlassian` intern selbst entscheidet, aber koppelt uns an ein
   nicht-öffentliches Utility-Modul, das bei einem künftigen Versionsbump
   ohne Vorwarnung umgebaut/entfernt werden könnte.
2. Eigene, kleine Domain-Suffix-Heuristik nachbauen (`*.atlassian.net`,
   `*.jira.com`, `*.jira-dev.com`, `*.atlassian.com`, `api.atlassian.com` =
   Cloud, alles andere = Server/DC) — minimal abweichendes Risiko (verpasst
   z.B. `mcp-atlassian`s IP-/Localhost-Sonderfälle, die für unsere
   Kunden-URLs ohnehin irrelevant sind), aber unabhängig von
   `mcp-atlassian`s Interna.

**Entscheidung.** Option 2. Dieselbe Vorsicht wie beim `unidecode_shim`
(E-7): keine Abhängigkeit von undokumentierten Interna eines Fremdpakets,
wenn eine kleine eigene Implementierung genügt. Verifiziert, dass die
Heuristik in der Praxis mit `mcp-atlassian`s eigener Entscheidung
übereinstimmt: `JiraConfig.from_env()`/`ConfluenceConfig.from_env()` liefern
für dieselben Test-URLs dasselbe `is_cloud`.

**Auth-Präzedenz.** "Kein `username` gesetzt → Token ist ein PAT" — dieselbe
Konvention, die `backend/api/connectors.py::_bitbucket_server_auth` für
Bitbucket Server schon verwendet. Keine Datenmodelländerung nötig
(`KnowledgeSource.username` war schon `nullable=True`).

**Bewusst nicht mitgemacht.** SSL-Verify-Override für selbstsignierte
on-prem-Zertifikate (`CONFLUENCE_SSL_VERIFY`/`JIRA_SSL_VERIFY`, von
`mcp-atlassian` unterstützt) — unbekannt, ob DRVs Confluence-Instanz das
braucht, kein Datenmodellfeld dafür vorhanden. Bei Bedarf als globale
Backend-Env-Var (analog `ALLOW_CLOUD_LLM`) nachziehen, nicht pro
Wissensquelle (Backend soll zustandslos bleiben, CLAUDE.md).

**Fundstelle.** `backend/mcp_client.py` (`_is_atlassian_cloud_url`,
`_atlassian_auth_env`), `backend/tests/test_mcp_client.py`,
`docs/UMSETZUNGSSTAND.md` Punkt 23.

---

## E-11 — ANTLR4-Grammatik-Runtime für den COBOL-Parser: Ausnahme von Prinzip 3

**Anlass.** Eine zweite Programmiersprache ist beim Kunden konkret absehbar
(nicht mehr rein hypothetisch). Der heutige COBOL-Parser (`parser/cobol/`,
~2.230 Zeilen handgeschrieben) ist strikt COBOL-spezifisch — ein zweiter
handgeschriebener Parser wäre derselbe Aufwand ein zweites Mal. Zusätzlicher
Auslöser für den Zeitpunkt: Das Produkt ist laut Auftraggeber **noch nicht**
produktiv (die "AP-0…AP-9 abgeschlossen"-Dokumente spiegeln nicht den echten
Stand) — das ist der letzte Zeitpunkt, an dem ein Kernumbau des Parsers ohne
Blast-Radius auf echte Kundendaten/Deep-Links möglich ist.

**Problem.** CLAUDE.md Architekturprinzip 3 schließt ANTLR-/tree-sitter-
Runtimes explizit aus ("OSS-Clearing-Aufwand, Offline-Bundle-Aufwand,
Betriebsrisiko — bei null Anforderungsnutzen", `docs/IMPLEMENTIERUNGSPLAN.md:99`),
und `docs/ABSCHLUSS.md:31` bestätigt das im (veralteten) Abschlussbericht als
erfüllt. Die Prämisse "null Anforderungsnutzen" gilt nicht mehr.

**Abgrenzung zum tree-sitter-Präzedenzfall.** `tree-sitter` lag bereits einmal
ungenutzt in `parser/requirements.txt` und wurde als Tech-Debt wieder entfernt
(`docs/TECH_DEBT_CLEANUP_PLAN.md`) — Runtime importiert, aber nie von einem
Visitor/Consumer genutzt. Dieser Fehler wird hier nicht wiederholt: der
zugehörige Spike (Phase 1, siehe unten) muss vor einem Go belegen, dass ein
Visitor die Grammatik-Ausgabe aktiv in `ParseResult` überführt, nicht nur eine
Bibliothek auf Vorrat importiert.

**Entscheidung.** Prinzip 3 gilt für den Sprachparser-Fall als punktuell außer
Kraft gesetzt, unter drei Bedingungen:

1. Nur `antlr4-python3-runtime` (reines Python, kein JRE) kommt ins
   Laufzeit-Image — der ANTLR-Codegenerator (Java) läuft ausschließlich zur
   Entwicklungszeit, generierte `.py`-Dateien werden wie normaler Code
   committet.
2. Ein Visitor überführt die Grammatik-Ausgabe aktiv in `ParseResult`, keine
   Importierung auf Vorrat.
3. Die Lizenz der bezogenen Grammatik selbst (nicht nur der Pip-Runtime) wird
   separat geprüft und in `docs/OSS-CLEARING.md` dokumentiert.

Umgesetzt zunächst als isolierter Spike (`parser/spikes/antlr_cobol/`, siehe
Plan „Spike: ANTLR4-Migration des COBOL-Parsers"), der nichts Produktives
anfasst. Vollmigration und Zweitsprache brauchen ein separates, explizites Go
auf Basis der Spike-Ergebnisse (Go/No-Go-Kriterien dort dokumentiert). Bei
No-Go: Ergebnis als Ergänzung zu diesem Eintrag festhalten, CLAUDE.md
Prinzip 3 bleibt/wird wieder uneingeschränkt formuliert.

**Fundstelle.** CLAUDE.md Architekturprinzip 3, `parser/spikes/antlr_cobol/README.md`.

**Nachtrag Phase 3 (11.08.2026): umgesetzt, ohne Engine-Flag.** Der
ursprünglich skizzierte Parallelbetrieb mit Feature-Flag
(`DOCTUS_COBOL_PARSER_ENGINE=legacy|antlr`) wurde bewusst **nicht** gebaut:
das Produkt läuft noch nicht produktiv (siehe „Anlass" oben), es gibt keinen
Blast-Radius auf echte Kundendaten, den ein schrittweiser Rollout schützen
müsste. Ein dauerhafter Flag, der mangels Produktivbetrieb nie umgelegt
würde, wäre exakt das Muster, das dieser Eintrag selbst als Fehler benennt
(tree-sitter-Präzedenzfall — importiert, aber nie aktiv genutzt). Stattdessen
direkter Ersatz: `parser/cobol/divisions.py` und `parser/cobol/
data_division.py` laufen jetzt vollständig über einen ANTLR-Parse-Tree
(`parser/cobol/antlr_bridge.py`, generierte Grammatik unter `parser/cobol/
_antlr/`) statt über den handgeschriebenen Token-Scan. `lexer.py`,
`procedure.py`, `copybook.py`, `xref.py`, `sql.py`, `chunking.py`,
`embedded.py`, `source_format.py`, `model.py` blieben unverändert — sie
arbeiten weiterhin auf dem (unveränderten) flachen Token-Strom bzw. reiner
Geschäftslogik, unabhängig von der Grammatik. Alle 115 vorbestehenden
COBOL-Tests inkl. aller 12 Golden Files sind unverändert grün (Verhaltens-
parität, keine Golden-Neugenerierung nötig). `antlr4-python3-runtime` ist
jetzt regulärer Bestandteil von `parser/requirements.txt`
(docs/OSS-CLEARING.md Abschnitt 6). Die im Spike identifizierten Auflagen
sind umgesetzt: `PredictionMode.SLL` (`antlr_bridge.build_tree()`) und ein
Worker-Warmup beim Start jedes Celery-Prozesses (`worker.py::
_warmup_antlr_cobol_parser`, `cobol/antlr_bridge.py::warmup()`), damit der
einmalige ANTLR-Full-Context-Fallback nicht die erste echte Anfrage
verzögert. COPY- und EXEC-Block-Maskierung für die Grammatik (`antlr_bridge.
mask_for_grammar()`) sind der im Spike vorhergesagte kleine Zusatzschritt.
Phase 4 (Zweitsprache) bleibt unbeauftragt.
