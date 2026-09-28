# COBOL-Analyseprüfung vom 28.09.2026

## Urteil und Prüfgrenze

Nein: Doctus extrahiert nicht alle statisch verfügbaren COBOL-Informationen.
Das vorhandene Fundament erkennt viele Strukturen, aber aus der vorhandenen
Grammatik werden nur ausgewählte Merkmale übernommen. Zusätzlich erzeugen
flache Token-/Regex-Scanner in nachgestellten Fällen falsche Beziehungen.
Eine erfolgreiche Syntaxanalyse bedeutet daher noch keine vollständige oder
fachlich richtige Analyse.

Geprüft wurden Vorverarbeitung, DATA-/PROCEDURE-Extraktion, COPY-Verarbeitung,
SQL-/EXEC-Auswertung, Chunking und relevante Persistenz-/MCP-Grenzen. Drei
vollständige kleine Programme wurden im Speicher geparst; hinzu kamen drei
SQL-Blöcke, zwei EXEC-Blöcke und ein Procedure-Copybook. CardDemo-Indexdaten
wurden ausschließlich gelesen. Kein Import, kein Reindex, keine Änderung am
Produktcode. Dies ist kein Nachweis vollständiger COBOL-Sprachkonformität und
keine erschöpfende Bestandsanalyse sämtlicher Dateien/Dialekte.

## Bereits vorhandenes Fundament

- Quellformatbehandlung einschließlich fester/freier Form, Fortsetzungen,
  Debug-/Profiloptionen und Erhaltung physischer Quellpositionen.
- Programme, Sections, Paragraphen, ENTRYs und grundlegende Datenhierarchien.
- PIC, grundlegendes REDEFINES/OCCURS, COPY-Abhängigkeiten, transitive
  Copybook-Feldvererbung und grundlegendes REPLACING.
- CALL/PERFORM/GOTO, Feldverwendungen, ausgewählte Datei-I/O-Beziehungen.
- SQL-Blöcke, CICS-/DLI-Blöcke und benannte Ressourcen; unbekannte Ziele können
  als unresolved/dynamic erhalten bleiben.

Diese Merkmale sind im Code vorhanden; die Liste ist keine pauschale Abnahme
aller Varianten. Die folgenden Fehler treten innerhalb dieses bestehenden
Funktionsumfangs auf.

## Reproduzierte Lücken

| Ticket | Probe / Bestandsbeleg | Ergebnis |
|---|---|---|
| O-360 | GO TO innerhalb IF/ELSE ohne trennenden Satzpunkt | Neben DONE-PARA entstehen GOTO-Ziele ELSE und DISPLAY. |
| O-360 | PERFORM TIMES-N TIMES | Zählvariable wird zum vermeintlichen Paragraphenziel. |
| O-360 | CardDemo-Live-Index | 12 GOTO-Kanten auf END-IF, 1 auf DISPLAY; jeweils keine tatsächlichen Paragraphenziele. |
| O-361 | LOCAL-STORAGE SECTION / LOCAL-AMOUNT | Keine Entity für das Feld, obwohl die Programmprobe keine Parserdiagnose liefert. |
| O-361 | 88 ACCEPTED VALUES 1 THRU 3, 7 | Nur value=1 gespeichert; Bereichsende und weiterer Wert fehlen. |
| O-361 | CardDemo RETRY-CONDITION | Quelle COPAUA0C.cbl:94 enthält BA, FH, TE; Index nur BA. |
| O-361 | PIC S9(7)V99 COMP-3 / Level 66 RENAMES | PIC und Name vorhanden, USAGE bzw. RENAMES-Bereich fehlen. |
| O-362 | SELECT ... INTO :RESULT-VALUE ... WHERE ID=:LOOKUP-ID | Beide Variablen werden WRITES; WHERE-Operand müsste als Eingabe erfasst werden. |
| O-362 | FROM BANK.ACCOUNTS | Nur BANK wird als Tabellenname extrahiert. |
| O-362 | SQL-Literal 'JOIN FAKE-TABLE' | Erfundene zusätzliche Tabelle FAKE-TABLE. |
| O-362 | INSERT INTO TARGET-TABLE SELECT VALUE FROM SOURCE-TABLE | Beide Tabellen als WRITES statt getrennter Ziel-/Quellrolle. |
| O-363 | Zwei WRITE-Anweisungen, nur zweite mit FROM | FROM-Puffer wird auch der ersten Anweisung zugeschrieben. |
| O-363 | CLOSE IN-FILE OUT-FILE | Nur IN-FILE hat eine operationsbezogene CLOSE-Kante. |
| O-364 | Procedure-Copybook mit CALL | Textchunk bleibt, Paragraph-/CALL-Struktur fehlt. |
| O-306/O-307 | CICS READ FILE INTO RESP / DLI ISRT SEGMENT FROM | Operation/Ressource vorhanden, Datenpuffer-/Statuszugriffe fehlen. |

Die drei vollständigen Programmproben erzeugten keine Parserdiagnosen.
Beim Procedure-Copybook wurde dagegen eine Parserdiagnose zu CALL gemeldet.
Die SQL-/EXEC-Proben prüfen die tatsächlich verwendeten Extraktoren unmittelbar.

## Ursachen im Code

- `parser/cobol/procedure.py`: Scanner verfolgt bei GO TO alle folgenden Wörter
  bis DEPENDING oder einem Nicht-Wort; Satzpunkt-basierte Endsuche. Kein
  vollständiges Modell von Verzweigungen, Schleifen und Ausführungsreihenfolge.
- `parser/cobol/data_division.py`: Visitor für FILE, WORKING-STORAGE, LINKAGE,
  aber keiner für LOCAL-STORAGE. VALUE speichert nur das erste Intervall-From;
  USAGE und RENAMES-Zielbereiche werden nicht in DataItem übernommen.
- `parser/cobol/sql.py`: Wortregex ohne Schutz für Literale/Kommentare oder
  Schema-Namen. SELECT-Hostvariablen nach INTO pauschal als WRITES; Tabellenrollen
  werden aus dem äußeren Statement-Typ statt einzelnen Klauseln abgeleitet.
- `parser/cobol/io.py`: FROM/INTO-Suche bis zum Punkt; normales CLOSE verarbeitet
  einen Operanden. SELECT/ASSIGN/FILE STATUS sind nicht im FD-Modell abgebildet.
- `parser/cobol/parse.py::parse_copybook`: synthetische DATA DIVISION;
  keine Procedure-/SQL-/EXEC-Extraktion für ausführbare Copybook-Fragmente.
- `parser/cobol/exec.py`: erste Operation und benannte Ressourcen;
  keine vollständigen Rollen für Datenpuffer, Response-Felder oder Fehlerpfade.
- `parser/cobol/xref.py`: USES-Wortreferenzen statt Read/Write-Zuweisungsmodell.
- `parser/cobol/parse.py`: Chunk-Fallback nur wenn keine Paragraphenchunks
  existieren. Bereits dokumentierter Verlust nach Zeile 825 unter O-359.

## Einordnung

Zuerst stillen Verlust und falsche Kanten beheben: O-359/O-305, O-360 und O-362.
Danach die fehlenden Deklarationen, I/O- und Datenflussrollen ergänzen. Weitere
Compiler-/Subsystemvarianten anhand konkreter Bestände priorisieren. Dynamische
Programmziele, tatsächliche I/O-Erfolge, Laufzeitwerte und externe Systemzustände
lassen sich durch statisches Parsing allein nicht allgemein bestimmen.

## Nachweise

Die Probe ist mit `PYTHONPATH=parser .venv/bin/python` ausführbar und verwendet
`cobol.parse.parse_program(..., profile=BuildProfile(source_format='free'))`.
Der genaue Probe-Quelltext und seine acht Ergebnisobjekte stehen neben diesem
Bericht unter `evidence/cobol_analysis_2026-09-28/`. Die Procedure-Copybook-Probe
wurde separat mit `parse_copybook("COPY-PARA.\n    CALL 'SUBPROG'.\n", "logic.cpy", ... )`
ausgeführt: eine copybook-Entity, keine Kanten, ein Chunk, Diagnose
`mismatched input 'CALL' expecting <EOF>`.

Die bekannten realen falschen GOTO-Ziele liegen u. a. in
`app/cbl/CBSTM03A.CBL:842` (DISPLAY) und `app/cbl/CBSTM03B.CBL:137,143,148` (END-IF).
Die Bestandswerte wurden am laufenden PostgreSQL-Index des Projekts 1247 gelesen.
