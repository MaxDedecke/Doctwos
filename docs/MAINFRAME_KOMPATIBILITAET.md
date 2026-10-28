# Mainframe-COBOL: Kompatibilität und Ausbauplan

Stand: 14.09.2026. Zugehörige Arbeitspunkte: O-117 bis O-156 in
[TODO.md](TODO.md).

## Ziel und Grenzen

Doctus soll einen Kundenbestand anhand seiner tatsächlichen Compiler-, Build-,
Bibliotheks- und Betriebsumgebung analysieren können. Eine erfolgreich importierte
Datei ist noch kein Beleg für vollständige Strukturanalyse. Unterstützung wird
pro Compilerfamilie, Version, Buildprofil und geprüftem Sprachmerkmal ausgewiesen.

Die Liste ist ein priorisierter Backlog, keine Zusage, alle Mainframes oder Dialekte
bereits zu unterstützen. Native Zugriffe, proprietäre Werkzeuge und Kundenbestände
setzen verfügbare Schnittstellen, Rechte und einen konkreten Zielumfang voraus.
EBCDIC-Verarbeitung und JCL-Strukturanalyse erweitern den bisherigen v1-Umfang
(F-028/F-026); ihre Aufnahme in den Backlog ändert diese Abgrenzung noch nicht.
Die Festlegungen in E-1/E-2/E-11 gelten weiter: Originalzeilen bleiben maßgeblich,
Copybooks werden nicht in den angezeigten Programmtext expandiert, zusätzliche
Parsertechnik wird nur mit einem tatsächlich genutzten Verbraucher eingeführt.

## Gesicherter Ist-Stand

| Befund im Repository | Bedeutung für Kundenbestände |
|---|---|
| `parser/cobol/parse.py::parse_program` hat kein Dialekt-/Buildprofil; die Pipeline kombiniert COBOL85-ANTLR-Grammatik und eigene Scanner. | Kein verifizierter Compiler-Kompatibilitätsmodus. Einzelne Erweiterungen können funktionieren, ohne dass eine Compilerfamilie insgesamt unterstützt wäre. |
| **O-123 erledigt (14.09.2026):** `source_format.py` folgt `>>SOURCE [FORMAT] [IS] FIXED|FREE|VARIABLE|EXTENDED` je Originalzeile, auch bei Einrückung, und kennt profilierte Spaltengrenzen. | Formatwechsel zerstören keine Struktur mehr; bedingte Kompilierung bleibt O-124. |
| Gegenprobe mit vollständiger DATA-/PROCEDURE-DIVISION und `>>IF 1 = 1`: CALLs aus aktivem und inaktivem Zweig, `errors == []`. | Ein fachlich falscher Aufrufgraph kann als fehlerfrei erscheinen. O-119/O-120/O-124. |
| Gegenprobe mit eingerücktem `>>SOURCE FORMAT FREE`: als Free erkannt, Programmstruktur vorhanden. | Explizite Formatvorgaben haben Vorrang; ohne sie bleibt die Heuristik sichtbar gekennzeichnet. |
| **O-120 erledigt (14.09.2026):** `AnalysisStatus` klassifiziert `complete`/`partial`/`text_fallback`/`skipped` anhand von `errors`, strukturierten O-119-Diagnosen und F-029-Fallbacks. `GitConnector` persistiert den Status je Datei und macht auch übersprungene Binär-, Größenlimit- und Nicht-UTF-8-Dateien sichtbar; API, Editor, Graph, Chat-Zitate und Diagnosebericht reichen ihn durch. | Unvollständige Analyse wird nicht mehr als uneingeschränkt vollständig dargestellt. Der Graph weist Status bewusst auf Datei-Ebene aus; belastbare Herkunft und Unsicherheit einzelner Entities/Kanten bleiben O-150. |
| **O-122 erledigt (14.09.2026):** `GitConnector` speichert pro Datei einen Analyse-Fingerprint aus Git-Blob, effektivem Buildprofil, Parser-/Grammatikstand und Copybook-Bibliotheksstand. Derselbe Commit wird damit nur dann erneut analysiert, wenn eine dieser Eingaben abweicht; unveränderte Chunk-Texte behalten ihren Vektor. | Profil- oder Bibliothekswechsel vermischen keine alten und neuen Strukturergebnisse mehr. Der Bibliotheksstand ist zunächst bewusst konservativ je COBOL-Datei enthalten; eine noch feinere Entity-/Kanten-Herkunft bleibt O-150. |
| **O-305 teilweise umgesetzt (22.09.2026):** ANTLR-Recovery maskiert `EXEC SQL`/`EXEC CICS`/`EXEC DLI` in DATA DIVISION und eigenständigen Copybooks jetzt mit einem gültigen Datenplatzhalter statt mit dem PROCEDURE-`CONTINUE`. Mehrzeilige `DATE-WRITTEN`-/`DATE-COMPILED`-Metadaten werden lokal verworfen, ohne DATA/PROCEDURE-Strukturen zu verlieren. Regressionen decken beide Fälle ab; reale Stichproben aus CardDemo, Z Open Editor und Bank of Z liefern wieder strukturierte Chunks statt Volltext-Fallbacks. | Drei Reindex-Läufe wurden mit dem aktuellen Worker gestartet. Z Open Editor ist abgeschlossen; CardDemo/Bank of Z müssen nach Behebung des aktiven RunPod-Embedding-Endpunkts (`/api/embed` liefert 404) erneut vollständig abgenommen werden. Nicht unterstützte JCL-/Nicht-COBOL-Dateien bleiben begründeter Text-Fallback. |
| `GitConnector` klassifiziert primär über Endungen; JCL ist ausdrücklich nur Text. O-074 überspringt Nicht-UTF-8 im regulären Import; der Copybook-Vorlauf verwendet dagegen Textlesen mit `errors="ignore"`. | Member ohne Endung sowie konvertierte oder rekordbasierte Exporte brauchen einen gemeinsamen Importvertrag. Kein stiller Zeichenverlust im Copybook-Vorlauf. |
| `copybook.py` löst Namen anhand quellenweiter Pfade bzw. Verzeichnisnamen auf; unterstützt bereits COPY/REPLACING und transitive Feldvererbung. | Vorhandene Funktion ausbauen: echte Suchreihenfolge, Versions-/Bibliothekskontext und Compileroptionen fehlen als Eingabe. Nicht als vollständig fehlende COPY-Unterstützung beschreiben. |
| `embedded.py` maskiert EXEC-Blöcke; `sql.py` analysiert SQL separat, `procedure.py` sucht CALL/PERFORM/GO TO. | Maskierung von CICS ist keine vollständige CICS-Programm-/Ressourcenanalyse. Weitere Subsysteme einzeln nachweisen. |

## Stand 28.10.2026: Ausbau für Kundenumgebungen mit Git

Aufhebung des Feature-Stopps für den COBOL-Parser (siehe `CLAUDE.md`). Quellsystem-Flexibilität
(Endevor, PDS u. ä.) bleibt zurückgestellt.

| Bereich | Stand |
|---|---|
| Kodierung | COBOL, Copybook und JCL fallen ohne Profil-`encoding` von UTF-8 auf cp1252 zurück (Diagnose `SOURCE_ENCODING_FALLBACK`, gespeicherte Kodierung). Ergibt der Rückfall überwiegend Nicht-ASCII (EBCDIC), wird die Datei weiter übersprungen. Ein gesetztes Profil-`encoding` bleibt strikt. |
| Klassifikation | Endungslose Dateien werden am Inhalt als `cobol`/`copybook` erkannt (`core/language_detection.py::sniff_cobol_family`). `spaces.language_paths` ordnet Verzeichnispräfixe zu, deren Endung nichts aussagt. Eine Vorab-Klassifikation je Sync speist Profil, Copybook-Index, Fingerprint und Parser. |
| Profil und Preflight | `GET/PUT /knowledge-sources/{id}/build-profile` (Schreiben nur Admin) prüft `build_profile` und `language_paths`. `GET /knowledge-sources/{id}/preflight` zeigt Dateien nach Sprache und Status, Kodierungen, die häufigsten Grammatikfehler mit Beispielstelle, offene COPY-Namen (mehrdeutig/fehlend) und Hinweise. Die Bedienoberfläche dafür fehlt noch. |
| COPY-Suchfolge | `copy_search_order` entscheidet gleichnamige Copybooks (erstes Verzeichnis mit genau einem Treffer; kein Raten innerhalb eines Verzeichnisses). Das gewählte Ziel steht als `meta.target_path` an der Kante, damit der globale Resolver die richtige Entity findet. |
| Fingerprint | Ein nicht auflösbarer COPY-Name (Systemmember wie `DFHAID`) macht den Fingerprint nicht mehr bestandsweit: fehlende und mehrdeutige Namen stehen als `?NAME` in `copybook_dependencies`. Am CardDemo hatten vorher 24 von 106 Dateien einen bestandsweiten Fingerprint, jetzt keine. |
| Grammatik | SLL scheiterte an jedem Subskript und jeder Referenzmodifikation; das ganze Programm wurde dann in LL(*) wiederholt (`COACTUPC.cbl`, 4.236 Zeilen: 130 s). Die Grammatik-Sicht blendet Klammern direkt hinter Datennamen aus (`antlr_bridge._blank_subscripts`), Länge und Zeilen bleiben gleich: 9 s, bei 76 verglichenen CardDemo-Dateien identische Entities und Kanten (einzige Abweichung: ein kaputtes Makro-Copybook mit weniger Müll-Sections). `JSON`/`XML GENERATE|PARSE` werden maskiert. |

Offen: Bedienoberfläche für Profil und Preflight, BMS-Parser (die 17 BMS-Dateien von CardDemo sind
`text_fallback`), Copybooks mit Prozedur-Code (`CSSETATY.cpy` bleibt `partial`), die Kante für
`XML PARSE … PROCESSING PROCEDURE`, EBCDIC-Autoerkennung (O-330) und ein konfigurierbares
Größenlimit (derzeit 2 MiB je Datei).

Reproduzierbare Minimalprobe für O-124 (als Test-Fixture zu übernehmen):

```cobol
identification division.
program-id. DIALECTTEST.
data division.
working-storage section.
01 FLAG PIC X.
procedure division.
MAIN-PARA.
>>IF 1 = 1
    call "ACTIVE".
>>ELSE
    call "INACTIVE".
>>END-IF
    goback.
```

Aufruf: `parse_program(text, "dialect-probe.cbl")`. Ist: beide CALL-Ziele,
keine gemeldeten Fehler. Soll bei diesem bekannten Ausdruck: nur `ACTIVE`.
Bei unbekannten Defines dürfen mehrere Möglichkeiten bestehen bleiben, müssen
aber als bedingt und mit dem jeweiligen Ausdruck gekennzeichnet werden.

## Kundenprofil aufnehmen

O-117 erfasst mindestens:

- Betriebssystem und Version: z/OS, BS2000 oder konkret benanntes anderes System;
  Entwicklungs-/Rehosting-Umgebung separat erfassen.
- Compilerfamilie, Version und Optionen: beispielsweise IBM Enterprise COBOL,
  Fujitsu COBOL2000, Micro Focus/OpenText; weitere Familien nur bei Bedarf.
  GnuCOBOL kann eine zusätzliche Testumgebung sein, ersetzt keine Herstellerabnahme.
- Quellformate, Codeseiten/CCSID, Transfer-Konvertierung und Satzformat;
  Optionen können je Member, Bibliothek und Buildziel abweichen.
- Quellenverwaltung und Transport: Git/Bridge, Endevor/ChangeMan, PDS/PDSE/USS,
  BS2000-Dateien/Bibliothekselemente oder versionierte Offline-Exporte.
- COPY-/Include-Bibliotheken samt Reihenfolge, Varianten, Präprozessoren,
  bedingten Defines, Compiler-/Binder-Listings und Modulnamen.
- Batch-/Online-Verarbeitung: JCL/PROCs bzw. BS2000-Prozeduren, Scheduler,
  CICS/IMS/openUTM, Datenbanken, Dateien, Messaging und aufgerufene Fremdsprachen.
- Erlaubte Importwege, Netzwerk-/Authentifizierungsbedingungen, Datenvolumen,
  Änderungsrate sowie eine kleine repräsentative und freigegebene Teststichprobe.

Diese Beispiele sind Auswahlfelder für die Bestandsaufnahme, keine Behauptung,
dass der Kunde sie alle einsetzt oder dass Doctus sie schon unterstützt.

## Reihenfolge

P0 = bekannte Korrektheitslücke oder notwendige Grundlage für belastbare Aussagen.
P1 = allgemeine Flexibilität für einen bestätigten Zielbestand.
P2 = bedarfsabhängige Erweiterung; Priorität erst nach Kundenprofil festlegen.

1. O-117/O-118/O-119: Zielumgebung, Testmatrix und Diagnosevertrag festlegen.
   Die beiden reproduzierten Lücken sofort als Regressionen festhalten.
2. O-120/O-121/O-150: Qualität, Profile und Evidenz durchgehend transportieren;
   O-123/O-124 korrigieren Format-/Variantenbehandlung auf dieser Grundlage.
3. O-122/O-125–O-129/O-134–O-137: Import und Copybooks reproduzierbar machen.
4. O-130–O-133 und O-138–O-149: nur die benötigten Quellwege und
   Sprach-/Subsystem-Erweiterungen implementieren. Kein pauschales Plattformframework.
5. O-151–O-156 begleiten Einführung und Erweiterungen: Einrichtung, Betrieb,
   Skalierung, Abnahme, Erweiterungsleitfaden und Provenienz.

## Gemeinsame Abnahmeregeln

- Jeder unterstützte Fall prüft Entities, Kanten, Originalzeilen und Diagnosen,
  einschließlich absichtlich nicht unterstützter bzw. mehrdeutiger Gegenfälle.
- Originalquelle, Codepage-/Rekorddekodierung, aktive Buildvariante und verwendete
  Bibliotheksversion sind nachvollziehbar. Konvertierung verändert nicht still
  Bezeichner, Literale oder Zeilenreferenzen.
- Strukturfehler dürfen Textsuche ermöglichen, aber nicht vollständige Analyse
  vortäuschen. Chat und Graph unterscheiden Quellbeleg, Konfigurationsbeleg,
  Compilerlisting-Beleg, Bedingung und bloße Kandidatenauflösung.
- Unbekannte dynamische Ziele bleiben unbekannt; Compileroptionen und Datenlayout
  werden nicht ohne Beleg interpretiert. Native Binärdaten werden nicht allein
  wegen einer konfigurierten EBCDIC-Codepage als Quelltext angenommen.
- Gleiche Quelle plus gleiches Profil ergibt reproduzierbare Analyse. Profil-,
  Parser- oder Bibliotheksänderungen invalidieren betroffene Ergebnisse. Alte und
  neue Varianten dürfen nicht unbemerkt im selben Graphen vermischt werden.
- Tests mit Herstellercompilern sind optional bereitgestellte Integrationsprüfungen;
  im Produkt wird dadurch kein Compiler, Java-Service oder proprietäres SDK nötig.
  Fixtures und Grammatiken erhalten überprüfte Nutzungsrechte/Lizenznachweise.

## Abgrenzung zum bestehenden Backlog

| Bestehender Punkt | Verhältnis zu den neuen Aufgaben |
|---|---|
| O-001 | Lasttest-/Kundenabnahme bleibt bestehen; O-154 ergänzt die Dialekt-/Variantenmatrix. |
| O-042 | Führender Punkt für Auswahl einer Mainframe-Anbindung. O-130–O-133 konkretisieren Vertrag und mögliche Zielwege; keinen zweiten identischen Konnektorauftrag eröffnen. |
| O-074 | Binärfilter bleibt Schutzmechanismus. O-127/O-128 erweitern kontrolliert auf explizit deklarierte Quelltextformate. |
| O-077–O-081 | Mehrsprachen-Refactoring ist kein Muss für Dialektprofile. O-149/O-155 greifen es erst bei einem echten weiteren Strukturparser auf. |
| O-063/O-078 | Bestehende Typverträge berücksichtigen, wenn O-119/O-120/O-150 Diagnose-/Graphmetadaten erweitern. |
| O-064/O-065 | Ruff und aktive Grammatikquellen sind vorhanden. O-156 baut auf deren Provenienz und Regenerierungsanleitung auf. |

## Herstellerquellen zur Einordnung

Die folgenden Quellen belegen Umgebungsunterschiede; sie sind kein Nachweis für
Doctus-Unterstützung. Weitere, versionsgenaue Nachweise gehören in O-118.

- [IBM: bedingte Kompilierung](https://www.ibm.com/docs/en/cobol-zos/6.5.0?topic=directives-conditional-compilation)
  erklärt DEFINE/IF/EVALUATE und die Verarbeitung gegenüber COPY/REPLACE.
- [Micro Focus: Quellformate](https://www.microfocus.com/documentation/reuze/60d/lhintr.htm)
  unterscheidet Fixed, Free und Variable; Hersteller-/Versionsregeln deshalb explizit erfassen.
- [GnuCOBOL-Handbuch](https://gnucobol.sourceforge.io/doc/gnucobol.html)
  dokumentiert Dialekt-/Konfigurationsoptionen; deren Existenz ist keine Garantie
  vollständiger Kompatibilität zu einem Herstellercompiler.
- [Fujitsu: COBOL2000-Referenzhandbuch](https://bs2manuals.ts.fujitsu.com/download/manual/21133)
  und [BS2IDE Compiler Notes](https://bs2000.ts.fujitsu.com/bs2ide/help/topic/com.fujitsu.ts.bs2000ide.rse.doc.user/html/remoteCompilation/compilerNotes.html)
  liefern den Ausgangspunkt für eine BS2000-spezifische Bestandsaufnahme.
- [IBM: z/OSMF Data Set/File REST](https://www.ibm.com/docs/en/zos/3.1.0?topic=services-zos-data-set-file-rest-interface)
  dokumentiert unter anderem das Auflisten von Dataset-Membern.
- [IBM: CICS XCTL](https://www.ibm.com/docs/en/cics-ts/5.5.0?topic=summary-xctl)
  zeigt einen Programmtransfer außerhalb eines normalen COBOL-CALL.
- [IBM: IMS DL/I aus COBOL](https://www.ibm.com/docs/en/ims/15.6.0?topic=db-establishing-dli-interface-from-cobol-pli)
  beschreibt die DL/I-Schnittstelle, die nicht bloß als gewöhnliches Anwendungsziel behandelt werden sollte.
- [IBM: JCL-Prozeduren](https://www.ibm.com/docs/en/zos-basic-skills?topic=do-jcl-exec-statements-what-are-jcl-procedures)
  und [JCL-Symbole](https://www.ibm.com/docs/en/zos/2.5.0?topic=symbols-defining-nullifying-jcl)
  begründen separate Aufgaben für Prozedurkontext und symbolische Auflösung.
- [Fujitsu: openUTM-Dokumentation](https://bs2manuals.ts.fujitsu.com/psOPENUTMV70de/openutm-v7-0-de-3013844.html)
  führt COBOL/KDCS als eigenen, bei Kundenbedarf zu prüfenden Integrationsbereich.
