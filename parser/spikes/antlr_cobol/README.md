# Spike: ANTLR4-Migration des COBOL-Parsers

Isolierter Spike zu `docs/ENTSCHEIDUNGEN.md` E-11. Nichts hier ist an
`cobol_persist.py`/`git.py`/`edge_resolver.py` angebunden, nichts unter
`parser/cobol/` wurde verändert, nichts davon läuft im Produktivimage. Dieser
Ordner ist das Kernartefakt für die Phase-2-Entscheidung (Go/No-Go).

## Ziel

Belegen oder widerlegen, ob eine ANTLR4-Grammatik (statt eines zweiten
handgeschriebenen Parsers) die Basis für COBOL **und** eine künftige
Zweitsprache sein kann — anhand der 6 Kernfragen aus dem Plan
„Spike: ANTLR4-Migration des COBOL-Parsers" (`~/.claude/plans/rippling-baking-pretzel.md`
zum Zeitpunkt der Beauftragung, hier inhaltlich vollständig übernommen).

## Vorgehen

1. COBOL85-Grammatik aus `grammars-v4/cobol85/` auf gepinntem Commit bezogen
   (siehe „Grammatik-Provenienz" unten).
2. Mit ANTLR 4.13.2 (Java, nur Entwicklungszeit) nach `generated/` als
   Python3-Ziel generiert — Lexer, Parser, Listener, Visitor für beide
   Grammatiken (Preprocessor + Haupt).
3. `compare.py` parst alle 12 Fixtures aus `parser/tests/cobol_corpus/fixtures/`,
   sowohl roh als auch nach Vorschaltung von `parser/cobol/source_format.py`
   (read-only importiert, nicht verändert), und beantwortet die Kernfragen
   anhand konkreter Messwerte — kein Abgleich gegen Golden-JSONs (falsche
   Messlatte, siehe Plan).

### Ausführen

```bash
cd parser/spikes/antlr_cobol
python3 -m venv .venv-spike
.venv-spike/bin/pip install -r requirements-spike.txt
.venv-spike/bin/python compare.py
```

### Grammatik neu generieren (falls `Cobol85.g4`/`Cobol85Preprocessor.g4` geändert werden)

Braucht ein JRE nur zur Entwicklungszeit (z.B. `apt-get install default-jre-headless`,
läuft **nicht** im Laufzeit-Image):

```bash
curl -sL -o /tmp/antlr.jar https://www.antlr.org/download/antlr-4.13.2-complete.jar
cd parser/spikes/antlr_cobol/grammar
java -jar /tmp/antlr.jar -Dlanguage=Python3 -visitor -o ../generated Cobol85Preprocessor.g4
java -jar /tmp/antlr.jar -Dlanguage=Python3 -visitor -o ../generated Cobol85.g4
```

## Grammatik-Provenienz

- **Quelle:** `github.com/antlr/grammars-v4`, Pfad `cobol85/`
- **Gepinnter Commit:** `e1c222f3f0e7c1b2fec799e94e34fc388b03f887` (2026-08-08),
  bezogen am 11.08.2026 (nicht `master` — reproduzierbar)
- **Lizenz:** MIT. `grammars-v4` selbst hat kein Root-`LICENSE`, das den
  Cobol85-Ordner abdeckt; die Grammatik-Header verweisen stattdessen auf
  `github.com/uwol/cobol85parser` als Ursprung. Dessen `LICENSE` (MIT,
  Copyright (c) 2017 Ulrich Wolffgang) wurde direkt eingesehen und liegt
  unter `grammar/LICENSE-upstream-cobol85parser`. Details:
  `docs/OSS-CLEARING.md` Abschnitt 6.
- **ANTLR-Runtime:** `antlr4-python3-runtime==4.13.2` (BSD-3-Clause), isoliert
  in `requirements-spike.txt` — bewusst **nicht** in `parser/requirements.txt`.

## Ergebnis (Stand 11.08.2026)

### Kernfrage 1 — Fixed/Free-Preprocessing

**`source_format.py` bleibt nötig, konfliktfrei vorgeschaltet.** Die
ANTLR-Hauptgrammatik selbst hat keine Spaltenlogik (Area A/B, Sequenznummern
1-6, Continuation über Spalte 7) — mit dem rohen Fixed-Format-File gefüttert,
scheitert sie an Sequenznummern (`02_fixed_edge.cbl`: `extraneous input
'000100' expecting {ID, IDENTIFICATION}`). Nach Rekonstruktion des
Code-Texts über `source_format.detect_format()` +
`source_format.split_logical_lines()` (read-only genutzt, keine Änderung an
der Datei) parst genau dieses Fixture sauber durch. **Ergebnis: kein
Widerspruch, kein Ersatz — die 144 Zeilen `source_format.py` bleiben
Vorstufe.** Erfüllt die Go-Schwelle „source_format.py bleibt konfliktfrei
vorgeschaltet".

### Kernfrage 2 — COPY ohne Expansion

**Bestätigt: keine automatische Textexpansion.** Die Preprocessor-Grammatik
erkennt `COPY ... REPLACING ...` als eigenen `copyStatement`-Knoten im
Parse-Tree, greift dafür aber nicht auf das Dateisystem zu — sie kann
`04_copy_replacing.cbl` fehlerfrei parsen, obwohl das referenzierte Copybook
`WSFIELDS` nicht existiert. Prinzip 5 ist damit **nicht** in Gefahr, solange
kein Visitor nachträglich eine Expansion vornimmt (das ist explizit nicht
Teil dieses Spikes).

**Aber:** Die Hauptgrammatik (`Cobol85.g4`) selbst akzeptiert eine
nicht-expandierte `COPY`-Zeile nicht (`mismatched input 'COPY' expecting
<EOF>` in beiden Fixtures `04`/`05`, roh wie rekonstruiert) — sie erwartet
offenbar, mit dem Output eines Preprocessing-Schritts gefüttert zu werden,
der `COPY`-Zeilen bereits entfernt/ersetzt hat. Für eine spätere
Vollmigration heißt das: `COPY`-Zeilen müssen vor der Hauptgrammatik
herausgefiltert werden (analog zum bestehenden Muster in
`embedded.py::mask()` für EXEC-Blöcke) und **separat** über den bestehenden
`CopybookIndex`-Mechanismus als Referenz/Kante behandelt werden — keine
Grammatik-Expansion, sondern dieselbe Nicht-Expansions-Architektur wie heute,
nur mit einem zusätzlichen Filterschritt. Aufwand: klein, gleiche
Größenordnung wie der bestehende `embedded.py`-Präzedenzfall.

### Kernfrage 3 — Eingebettetes SQL/CICS

**Wichtiger Fund, kein Blocker, aber Aufwand nötig.** Die Hauptgrammatik hat
zwar eigene Regeln `execSqlStatement`/`execCicsStatement`, deren Lexer-Token
(`EXECSQLLINE`/`EXECCICSLINE`) erwarten aber ein **Tag-Format**
(`*>EXECSQL ...` / `*>EXECCICS ...`) — offensichtlich die Konvention eines
vorgelagerten Fremd-Precompilers, **nicht** die literale COBOL-Syntax `EXEC
SQL ... END-EXEC.`/`EXEC CICS ... END-EXEC.`, wie sie in
`07_exec_sql.cbl`/`08_exec_cics.cbl` und in echtem COBOL-Code steht. Mit
echtem `EXEC SQL`-Text gefüttert, scheitert die Hauptgrammatik
(`mismatched input 'SQL' expecting SECTION` — der Lexer erkennt `EXEC` als
gewöhnliches Token, nicht als Beginn eines EXECSQLLINE-Blocks).

Zwei Optionen für eine Vollmigration: (a) die Grammatik um eine Regel für die
literale `EXEC SQL ... END-EXEC`-Syntax erweitern (Lexer-Mode-Wechsel nach
dem Vorbild der bestehenden `EXECSQLLINE`-Regel), grob 1-2 PT; oder (b) wie
heute mit `embedded.py::mask()` arbeiten und EXEC-Blöcke vor der
ANTLR-Hauptgrammatik maskieren, dann separat mit dem bestehenden
`sql.py::scan()` auswerten — kein Blocker, aber definitiv **kein**
Selbstläufer, wie man beim Lesen von „hat eine execSqlStatement-Regel"
zunächst annehmen könnte.

### Kernfrage 4 — Line/Column-Granularität

**Bestätigt.** Alle 12 Fixtures liefern Token mit korrekt gesetzten
`line`/`column`-Attributen (verifiziert über `CommonTokenStream.tokens`).
Verlustfrei bis auf Entity-Ebene durchreichbar — passt zu
`Entity.start_line`/`end_line` (Prinzip 5).

### Kernfrage 5 — Lizenz der Grammatik

Siehe „Grammatik-Provenienz" oben und `docs/OSS-CLEARING.md` Abschnitt 6.
MIT, eindeutig geklärt, nicht nur angenommen — Go.

### Kernfrage 6 — Aufwandsindikator für Lücken

| Konstrukt | Fixture | Status | Aufwand |
|---|---|---|---|
| Fixed-Format-Spalten | `02` | Gelöst durch vorgeschaltetes `source_format.py` | keiner (bereits vorhanden) |
| `COPY` ohne Expansion | `04`, `05` | Grammatik lehnt unexpandiertes `COPY` ab | klein — Filterschritt analog `embedded.py`, < 1 PT |
| `EXEC SQL`/`EXEC CICS` | `07`, `08` | Grammatik erwartet Fremd-Precompiler-Tag-Format, nicht literale Syntax | mittel — Grammatik-Erweiterung ODER Weiterverwendung von `embedded.py::mask()`, 1-2 PT |
| `CALL` dynamisch (Variable) | `09` | **Kein Problem** — parst direkt, auch nach Rekonstruktion | keiner |
| `PERFORM ... THRU` inkl. unbekanntem Ziel | `10` | **Kein Problem** | keiner |
| Bare-Verb-Statements (`GOBACK`, `EXIT` ohne Operanden) | `11` | **Kein Problem** | keiner |
| Garbage/Nicht-COBOL | `99` | Schlägt korrekt fehl (soll es auch) | — (kein Gap, das ist der Zweck des Fixtures) |

**Gesamt:** 7 von 11 fachlich gültigen Fixtures (99 ausgenommen, da bewusst
ungültig) parsen bereits sauber. Die verbleibenden 4 Lücken (`02`, `04`,
`05`, `07`/`08` teilen sich zwei Ursachen) sind alle **konkret benannt und
mit ≤3 PT geschätzt** — Fixture-02-Lücke ist mit dem bereits vorhandenen
`source_format.py` sogar kostenlos gelöst. Erfüllt die Go-Schwelle „Lücken
mit ≤3 PT Grammatik-Erweiterung schließbar".

### Performance

Erster wichtiger Fund: ANTLRs **Default-Prediction-Mode (Full-LL)** ist auf
dieser Grammatik ~15-40x langsamer als nötig (927-Zeilen-Testprogramm: 1.2-1.4s
Full-LL vs. 0.035-0.09s mit `PredictionMode.SLL`). SLL ist Standard-ANTLR-Praxis
für Grammatiken ohne echten Bedarf an Full-LL-Ambiguitätsauflösung und ändert
das Fehlerverhalten auf allen 12 Fixtures nachweislich nicht. `compare.py`
nutzt SLL durchgängig.

Mit SLL, auf einem synthetisch generierten 303-Zeilen-COBOL-Programm
(`scripts/generate_synthetic_cobol_corpus.py`, read-only importiert):
**ANTLR 0.023s vs. Altparser 0.003s → Faktor ~7.4x langsamer.**

Eine Einzelkonstruktion (`OCCURS ... DEPENDING ON`, Fixture `06`) triggert
beim **ersten** Auftreten in einem Prozess einen einmaligen
Full-Context-Fallback (~0.25-1.3s je nach Kontextgröße) — ANTLRs adaptive
LL(*)-Prediction eskaliert dort einmalig von SLL auf vollen Kontext, cached
die Entscheidung danach aber auf ATN-Ebene (prozessweit, über
Parser-Instanzen hinweg). Für den Celery-Worker (langlebiger Prozess, viele
Dateien nacheinander) heißt das: dieser Preis wird **einmal pro
Worker-Lebenszeit** gezahlt, nicht pro Datei — für die 100-GB-Monorepo-Skala
(Prinzip 4) relevant, aber kein Showstopper. Bei einer Vollmigration lohnt
sich ein gezielter Vorab-„Warmup"-Parse eines repräsentativen Programms beim
Worker-Start, um diesen Erstkosten aus dem kritischen Pfad zu nehmen.

**Verdict Performance:** mit SLL grob in derselben Größenordnung wie der
Altparser (einstelliger Faktor, nicht zwei Zehnerpotenzen) — Go, aber mit
der Auflage, SLL **und** einen Worker-Warmup in einer Vollmigration explizit
zu übernehmen, nicht implizit vorauszusetzen.

### Zweitsprachen-Tauglichkeit (qualitativ)

Nicht vertieft getestet (kein zweites Grammatik-Beispiel im Rahmen dieses
Spikes generiert), aber strukturell einordbar: `grammars-v4` deckt >200
Sprachen im selben Muster ab (Lexer/Parser/Visitor-Trias, Python3 als
Zielsprache wählbar) — das Visitor-Pattern selbst ist nicht COBOL-spezifisch
verdrahtet, sondern eine generische ANTLR-Eigenschaft. Qualitatives Go, ohne
Zahlen.

## Go/No-Go-Zusammenfassung

| Kriterium | Ergebnis | Bewertung |
|---|---|---|
| Fixture-Abdeckung | 7/11 gültige Fixtures direkt OK, Rest mit ≤3 PT lösbar | **Go** |
| Preprocessing | `source_format.py` bleibt konfliktfrei vorgeschaltet | **Go** |
| COPY ohne Expansion | Nachgewiesen keine automatische Expansion | **Go** |
| Line/Column | Verlustfrei auf Entity-Ebene durchreichbar | **Go** |
| Performance | ~7.4x langsamer mit SLL (vs. ~130x ohne) + einmaliger Warmup-Kosten | **Go, mit Auflage SLL+Warmup** |
| Lizenz | MIT, eindeutig direkt an der Quelle verifiziert | **Go** |
| Zweitsprachen-Tauglichkeit | Strukturell plausibel, nicht empirisch getestet | **Go (qualitativ)** |

**Empfehlung: Go für Phase 3 (Vollmigration COBOL, Parallelbetrieb über
Engine-Flag), unter drei expliziten Auflagen**, die alle aus diesem Spike
stammen und in einer Phase-3-Beauftragung mit aufgenommen werden sollten:

1. `PredictionMode.SLL` ist Pflicht, nicht optional (Faktor 15-40x).
2. Worker-Warmup-Parse beim Start, um den einmaligen Full-Context-Fallback
   aus dem Antwortzeit-kritischen Pfad zu nehmen.
3. `COPY`- und `EXEC SQL`/`EXEC CICS`-Filterung vor der Hauptgrammatik ist
   ein eigener, kleiner Engineering-Schritt (kein Selbstläufer der
   Grammatik) — analog zum bestehenden `embedded.py`-Muster.

## Explizit nicht Teil dieses Spikes

Keine Anbindung an `cobol_persist.py`/`git.py`/`edge_resolver.py`, kein
Feature-Flag, keine Änderung an `parser/requirements.txt`/`parser/Dockerfile`,
keine Änderung unter `parser/cobol/`, kein Test einer zweiten Sprache, kein
Visitor, der tatsächlich `ParseResult` befüllt (das ist der Kern von Phase 3).
