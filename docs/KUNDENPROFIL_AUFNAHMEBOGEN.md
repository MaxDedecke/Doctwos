# Kundenprofil-Aufnahmebogen (Mainframe/COBOL)

Zu [O-117](OFFENE_ENTWICKLUNGSPUNKTE.md) und den Feldern aus
[MAINFRAME_KOMPATIBILITAET.md](MAINFRAME_KOMPATIBILITAET.md#kundenprofil-aufnehmen).
Zweck: „COBOL“ allein ist keine ausreichende Spezifikation eines Kundenbestands.
Dieser Bogen macht die Zielumgebung explizit, **bevor** eine Aussage über
Kompatibilität getroffen wird — als Grundlage für O-118 (Testmatrix), O-121
(Buildprofile) und O-130–O-133 (Quellanbindung), nicht als Ersatz dafür.

## Wie benutzen

- Mit dem Kunden zusammen ausfüllen (Termin, Fragebogen per Mail oder Selbstauskunft).
- **Jedes Feld bekommt einen Wert oder ausdrücklich `❓ unbekannt / zu klären`.**
  Ein leeres Feld ist mehrdeutig (nicht gefragt? nicht zutreffend? Kunde weiß es
  nicht?) — das widerspricht der Abnahmeregel aus O-120/O-150, dass Unsicherheit
  sichtbar bleiben muss, nicht stillschweigend als „ok“ interpretiert wird.
- Ein ausgefüllter Bogen ist **keine** Kompatibilitätszusage. Er ist die
  Eingabe, gegen die O-118 eine Testmatrix aufbaut und O-121 ein Buildprofil
  ableitet.
- Pro Kunde eine Kopie dieses Bogens ablegen (z. B. im jeweiligen Kundenordner),
  nicht in diesem Repo — hier liegt nur die Vorlage plus ein fiktives Beispiel.

## Der Bogen

### 1. Betriebssystem

| Feld | Wert |
|---|---|
| Zielsystem (z/OS, BS2000, sonstiges — bitte konkret benennen) | |
| Version/Release | |
| Entwicklungs-/Rehosting-Umgebung, falls abweichend vom Produktivsystem | |

### 2. Compiler

| Feld | Wert |
|---|---|
| Compilerfamilie (z. B. IBM Enterprise COBOL, Fujitsu COBOL2000, Micro Focus/OpenText) | |
| Version | |
| Relevante Compileroptionen/Schalter (z. B. Dialektmodus, `ARITH`, `TRUNC`) | |
| Wird GnuCOBOL zusätzlich genutzt (nur als Testumgebung, kein Herstellerersatz)? | |

### 3. Quellformat, Codepage, Satzformat

| Feld | Wert |
|---|---|
| Quellformat (Fixed, Free, Variable) — einheitlich oder je Member/Bibliothek verschieden? | |
| Codeseite/CCSID der Quellen | |
| Transfer-Konvertierung (EBCDIC→ASCII o. ä.) — wo und womit passiert sie? | |
| Satzformat des Exports (RECFM/LRECL, RDW/BDW, oder bereits LF-normalisierter Text?) | |

### 4. Quellenverwaltung und Transport

| Feld | Wert |
|---|---|
| SCM (Git/Bridge, Endevor, ChangeMan, PDS/PDSE/USS, BS2000-Bibliothekselemente, versionierter Offline-Export) | |
| Stufen/Umgebungen (DEV/TEST/PROD) und wie sie im Export unterschieden werden | |
| Wer/was exportiert, wie oft, in welchem Format? | |

### 5. COPY-/Include-Bibliotheken

| Feld | Wert |
|---|---|
| Bibliotheken und ihre Suchreihenfolge (Verkettung) | |
| Varianten/Präprozessoren im Einsatz | |
| Bedingte Defines (`>>IF`/`>>DEFINE`/`EVALUATE`), die den Bestand beeinflussen | |
| Compiler-/Binder-Listings verfügbar? | |
| Modul-/Loadmodulnamen vs. PROGRAM-ID/ENTRY — weichen sie ab? | |

### 6. Batch-/Online-Verarbeitung

| Feld | Wert |
|---|---|
| JCL/PROCs bzw. BS2000-Prozeduren im Bestand? | |
| Scheduler (Name/Produkt) | |
| Online-Monitor (CICS, IMS, openUTM, sonstiges) | |
| Datenbanken (Db2, IMS DB, UDS/SQL, SESAM, Adabas, IDMS, sonstiges) | |
| Messaging (MQ o. ä.) | |
| Aufgerufene Fremdsprachen (Assembler, PL/I, C, sonstiges) | |

### 7. Importweg und Rahmenbedingungen

| Feld | Wert |
|---|---|
| Erlaubte Importwege (Offline-Export, z/OSMF-REST, sonstiges) | |
| Netzwerk-/Authentifizierungsbedingungen (Proxy, private CA, Auth-Verfahren) | |
| Datenvolumen (Anzahl Member, Gesamtgröße) | |
| Änderungsrate (wie oft ändert sich der Bestand relevant?) | |
| Kleine repräsentative, **freigegebene** Teststichprobe vorhanden? | |

Diese sieben Kategorien sind Auswahlfelder für die Bestandsaufnahme — nicht die
Behauptung, dass ein Kunde alle Ausprägungen einsetzt oder dass Doctus sie
bereits unterstützt (siehe MAINFRAME_KOMPATIBILITAET.md, Abschnitt „Ziel und
Grenzen“).

## Beispielhaft ausgefüllte Konfiguration (fiktiv)

Dient nur zum Zeigen, wie ein ausgefüllter Bogen aussieht, inklusive
Feldern, die beim Erstgespräch typischerweise noch offen sind. **Kein
realer Kunde**, keine Kompatibilitätszusage.

| Feld | Beispielwert |
|---|---|
| Zielsystem | z/OS 2.5 |
| Entwicklungsumgebung | dieselbe LPAR, kein separates Rehosting |
| Compilerfamilie/Version | IBM Enterprise COBOL 6.4 |
| Compileroptionen | `ARITH(EXTEND)`, sonstige Schalter — ❓ unbekannt / zu klären |
| GnuCOBOL zusätzlich genutzt | Nein |
| Quellformat | Fixed, laut Kunde einheitlich — ❓ unbekannt / zu klären, ob Ausnahmen existieren |
| Codeseite/CCSID | IBM-1141 |
| Transfer-Konvertierung | über vorhandenes FTP-Skript des Kunden, Details ❓ unbekannt / zu klären |
| Satzformat des Exports | RECFM=FB, LRECL=80 |
| SCM | Endevor, Stufen DEV/QA/PROD |
| Bibliotheken/Suchreihenfolge | drei Konkatenationsstufen, genaue Reihenfolge ❓ unbekannt / zu klären |
| Bedingte Defines | keine bekannten `>>IF`-Konstrukte im Kernbestand |
| Compiler-/Binder-Listings verfügbar | Ja, für Stichprobe zugesagt |
| JCL/PROCs im Bestand | Ja |
| Scheduler | ❓ unbekannt / zu klären |
| Online-Monitor | CICS TS |
| Datenbank | Db2 for z/OS |
| Messaging | ❓ unbekannt / zu klären |
| Fremdsprachen | keine bekannt |
| Importweg | Offline-Export (Kunde erstellt Dump), z/OSMF nicht verfügbar |
| Netzwerk/Auth | Air-Gapped-Übergabe, kein Netzwerkzugriff auf die Mainframe-Umgebung |
| Datenvolumen | ca. 4.000 Member, ❓ Gesamtgröße unbekannt / zu klären |
| Änderungsrate | monatliches Release |
| Teststichprobe freigegeben | Ja, 15 Programme + zugehörige Copybooks zugesagt |

## Priorisierte Kundenszenarien

Ohne konkreten Kundenbestand (siehe Abhängigkeit von O-117: „Kundenangaben für
reale Abnahme“) lässt sich noch keine reale Priorisierung vornehmen. Diese
Rangfolge legt fest, **welche Bogen-Antworten zuerst zu einer Codeänderung
führen**, sobald ein Kunde antwortet — sie ersetzt keine Einzelfallentscheidung:

1. **Blockierend für O-118/O-119/O-121 (P0).** Compilerfamilie+Version,
   Quellformat, Codepage/CCSID, bedingte Defines. Ohne diese Angaben lässt
   sich keine Testmatrix aufbauen und kein Buildprofil ableiten — höchste
   Priorität in jedem Erstgespräch.
2. **Bestimmt den Quellanbindungsweg (P0/P1 für O-130–O-133).** SCM/Transport,
   Importweg, Netzwerk-/Authentifizierungsbedingungen. Entscheidet, welcher
   der unter O-042 genannten Wege überhaupt zutrifft, bevor an einem Adapter
   gearbeitet wird.
3. **Bestimmt den Sprach-/Subsystem-Ausbau (P1/P2 für O-138–O-149).**
   Online-Monitor, Datenbank, Messaging, Fremdsprachen — nur die tatsächlich
   genutzten Subsysteme bekommen ein eigenes Folgeticket (kein pauschales
   Plattformframework, siehe MAINFRAME_KOMPATIBILITAET.md).
4. **Betrieb/Skalierung (P1 für O-151–O-154).** Datenvolumen, Änderungsrate,
   Teststichprobe — bestimmt, ob vor dem Vollimport ein Preflight sinnvoll ist
   und wie repräsentativ eine spätere Abnahme sein kann.

**Szenario-Typen**, um ein Erstgespräch schneller einzuordnen (grob nach
Aufwand für den bestehenden Backlog sortiert, keine Zusage):

- **A — reiner Batch, ein Compiler, ein Quellformat.** Deckt sich am ehesten
  mit dem heutigen Codepfad; P0-Punkte (O-118/O-119/O-121/O-123/O-124) reichen
  meist aus, um eine belastbare Aussage zu treffen.
  - Beispielbogen oben (Db2 statt reinem Batch) zeigt zusätzlich CICS —
    reduziert man Punkt „Online-Monitor“ auf „keiner“, ist das der A-Fall.
- **B — Batch + ein Online-Monitor (CICS/IMS/openUTM), eine Compilerfamilie.**
  Wie Beispielbogen oben: zusätzlich O-138–O-143 je nach Monitor.
- **C — mehrere Compilerfamilien, Bibliotheken oder Stufen im selben Bestand.**
  Zusätzlich O-122/O-125–O-137 (Reindexierung, Copybook-Kontext,
  Suchreihenfolge) vor jeder Sprachmerkmalsaussage nötig.
- **D — Mainframe-natives SCM ohne Git-Bridge (PDS/PDSE, BS2000-Bibliothek,
  Endevor/ChangeMan-Export).** Zusätzlich O-130–O-133 vor jedem Import.

## Weiterverwendung

Ein ausgefüllter Bogen fließt in:

- **O-118** — als Grundlage für Fixtures und die Kompatibilitätsmatrix.
- **O-121** — als Werte für ein versioniertes Buildprofil (Compilerfamilie/
  -version, Format, Encoding, Defines, Bibliotheksfolge).
- **O-130–O-133** — als Entscheidung für den Quellanbindungsweg.
- **O-151** — als Ausgangspunkt für den späteren Preflight, der dieselben
  Felder stichprobenartig technisch verifiziert statt sie nur abzufragen.
