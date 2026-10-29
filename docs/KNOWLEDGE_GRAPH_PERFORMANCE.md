# Wissensgraph: Performance

Auftrag vom 27.10.2026: Darstellung und Ladepfad bestehender Graphen optimieren,
mit 2.000 und 20.000 Knoten vergleichen; abgeschlossene Schritte auf `develop`
committen und pushen. Die bestehende Canvas-Darstellung wird beibehalten.

## Darstellung

- `knowledgeGraphRendering.ts` bereitet Farben, Radien, Bezeichnungen und
  Parallelkanten vor. Während des Zeichnens gibt es keine DOM-Farbabfragen.
- Änderungen der Root-Klasse oder ihrer Style-Tokens invalidieren den Farbcache
  über eine Subscription. Dadurch werden auch nachgelagert angewandte Theme-CSS-
  Änderungen übernommen, ohne pro Frame Styles abzufragen. Die abschließende
  Frontend-Suite besteht mit dieser Regression 945 Tests.
- Eine Auswahl besitzt einen statischen Ring. Der Graph kann auch mit Auswahl
  automatisch pausieren; Partikel und pulsierende Auswahlringe entfallen.
- Symbole erscheinen ab neun Pixeln Knotenradius; Beschriftungen abhängig vom
  Zoom, ausgewählte Knoten behalten ihre Beschriftung.
- Knoten außerhalb des Ausschnitts werden nicht gezeichnet. Kanten werden über
  konservative Begrenzungsrechtecke gefiltert; Verbindungen durch den Ausschnitt
  bleiben auch bei zwei außerhalb liegenden Endpunkten sichtbar.
- Filter, Richtungspfeile, Hervorhebung und Quellen-Navigation bleiben erhalten.

## Layout

- Die Übersicht berechnet ihre Kräfte in einem Web Worker. Die Canvas-Bibliothek
  führt keine eigenen Physikschritte mehr im Hauptthread aus.
- Ohne Worker-Unterstützung oder bei einem Worker-Fehler übernimmt dieselbe
  Berechnung in asynchronen Zeitabschnitten. Ein einzelner Physikschritt kann in
  diesem Ersatzpfad weiterhin den Hauptthread beanspruchen.
- Datasetwechsel und Unmount beenden alte Berechnungen. Verspätete Antworten
  werden ignoriert; manuell verschobene Knoten behalten ihre Position.
- Nur abgeschlossene Layouts werden als fertige Positionen wiederverwendet.
  Ein anfänglicher Filterreset darf Startpositionen nicht als fertiges Layout
  behandeln. Die Positionsdaten sind von Reacts API-Daten getrennt.
- Nachbarschaften verwenden einen einmal aufgebauten Kantenindex und eine
  iterative Breitensuche. Der Traversierungsanteil ist O(V + E); für die stabile
  Zeilenreihenfolge kommt die Sortierung der Knoten hinzu.

## Reproduzierbare Messung

`frontend/scripts/benchmark-knowledge-graph.cjs` verwendet Playwright und einen
separaten Frontend-Server. Sämtliche API-Antworten werden im Browser ersetzt;
es werden keine Daten in eine laufende Doctus-Instanz geschrieben.

```bash
cd frontend
GRAPH_BENCH_URL=http://localhost:3100 \
  node scripts/benchmark-knowledge-graph.cjs /tmp/graph-results.json
```

Optional: `GRAPH_BENCH_CHROMIUM` für einen vorhandenen Browser,
`GRAPH_BENCH_NODES=2000,20000` für den Umfang. Das Ergebnis enthält Umgebung,
Version, Knotenzahl und Kantenzahl sowie Zeichenaufrufe, CSS-Abfragen und
Frame-Abstände bei Ruhe, Auswahl und Zoom. `selectedVerified` kennzeichnet,
ob der Auswahlversuch tatsächlich eine Auswahl ausgelöst hat. Fehlgeschlagene
Auswahlproben und nicht abgeschlossene angeforderte Worker-Läufe brechen ab.

Der Korpus verwendet feste Gitterpositionen und zwei gerichtete Kanten pro
Knoten. Die Messung isoliert Darstellung und Interaktion; sie belegt weder
Layoutqualität noch Datenbankleistung oder Leistung auf Unternehmensclients.
Auf ausdrücklichen Folgeauftrag wurde die Standardgrenze auf 10.000 Knoten
erhöht. Das unabhängige Roh-Codebeziehungsbudget beträgt höchstens 100.000.

## Datenbank

- Die Übersicht lädt manuelle/Wissens-Verknüpfungen mit SQL-Projektvorauswahl
  und gebündelten Endpunkt-, Quellen- und Projektabfragen. Die Sichtbarkeit wird
  weiterhin pro Anfrage anhand von Team, Projekt und globaler Codefreigabe geprüft.
- Dokumenttext und Embedding-Vektoren werden für diese Darstellung nicht geladen;
  dasselbe gilt für die Dokument-Endpunkte von Entity-Dokument-Verbindungen.
- Die Regression misst bei 10 und bei 100 Verknüpfungen jeweils fünf SELECTs.
  Die Zahl der Abfragen wächst damit nicht pro Kante. Die Menge der geladenen
  Verknüpfungen und Metadaten wächst weiterhin mit dem ausgewählten Bestand;
  die abschließende Knotenauswahl ersetzt keine vollständige SQL-Aggregation.

## Prüfung

Die erste Stufe besteht TypeScript, Lint der geänderten Dateien und alle 935
Frontend-Tests. Backend (728 bestanden, 2 übersprungen) und Parser (733 bestanden,
5 übersprungen) wurden auf getrennten Testdatenbanken geprüft. Neue Regressionen
prüfen insbesondere DOM-freies Zeichnen, Themewechsel, Detailgrad und Kanten,
die den sichtbaren Ausschnitt kreuzen.

Nach der Layout-Stufe bestehen alle 944 Frontend-Tests sowie TypeScript und
ESLint (bestehende Warnungen bleiben). Der reale Chromium-Lauf mit 200 nicht
vorpositionierten Knoten bestätigt eine abgeschlossene Worker-Berechnung.
Regressionen decken Abbruch, verspätete Antworten, Dragging und den anfänglichen
Filterreset ab. Eine zyklische Nachbarschaft mit 20.000 Knoten prüft, dass jede
Kante nur einmal für den Traversierungsindex gelesen wird.

Die Backend-Stufe besteht 729 Tests (2 übersprungen), einschließlich Scope- und
Query-Budget-Regressionen. Eine vorhandene Testbereinigung wurde unabhängig von
zufälligem ORM-Nachladen gemacht: Der Link wird vor dem kaskadierenden Löschen
seiner Chunks explizit geflusht.

Bei der Kontrolle der GitHub-CI wurden zwei Fehler des Ausgangsstands behoben:
Alle drei CI-Datenbanken verwenden nun dasselbe gepinnte pgvector-Image wie der
Standard-Stack (`halfvec` wird benötigt). Der datenbankfreie Golden-Job wählt
explizit `test_cobol_*.py`, statt über `-k cobol` versehentlich einen Java-DB-Test
mit `not_cobol` im Namen auszuwählen. 250 Golden-/COBOL-Tests bestehen ohne Netz
oder Datenbank.

Der Parser-CI-Job erhält außerdem einen eigenen Redis-kompatiblen Valkey-Dienst.
Der E2E-Aufbau führt den vorgeschriebenen ersten Passwortwechsel aus, bevor
Login- und Accessibility-Smokes parallel dasselbe Testkonto verwenden. Damit
ist CI auf `6a53b4b` vollständig grün (11 Jobs).

Alle 13 Browser-Smokes (Login, Accessibility und Graph-Bedienung bei mehreren
Panelgrößen) bestehen lokal gegen eine isolierte Produktionsinstallation.
Der Opazitätstest liest die tatsächliche Knotenfüllung, statt von der
zoomabhängigen Sichtbarkeit einer Beschriftung abzuhängen. Der CI-E2E-Job
enthält diese Graph-Fälle und einen zusätzlichen funktionalen Worker-Smoke
mit 200 nicht vorpositionierten Knoten. Bildraten sind keine CI-Grenzwerte.

## Messergebnis vom 27.10.2026

Versionierte Ergebnisse: [vorher](evidence/knowledge-graph-performance-2026-10-27/before.json),
[nachher](evidence/knowledge-graph-performance-2026-10-27/after.json) und
[Produktions-Worker](evidence/knowledge-graph-performance-2026-10-27/production-worker.json).
Vergleich: `a49c9e3` gegen die Optimierung aus `ef8c398`, gleiche Browserprobe
nacheinander auf demselben Rechner (i7-14650HX, 8 für den Container sichtbare
CPUs, Headless Chromium, 1440 × 900, getrennte Next-Dev-Server). Einzelmessungen,
keine statistische Kapazitätsfreigabe; beide Auswahlproben wurden bestätigt.

| Knoten / Kanten | Auswahl vorher / nachher | Zoom vorher / nachher |
|---|---|---|
| 2.000 / 4.000 | 32,5 / 60,0 FPS | 36,3 / 59,5 FPS |
| 20.000 / 40.000 | 4,6 / 60,0 FPS | 4,4 / 58,9 FPS |

Nach der Optimierung fallen bei ruhender Auswahl keine Zeichenaufrufe mehr
an. Während der Zoomprobe gibt es keine `getComputedStyle`-Aufrufe. Der
Produktionslauf bestätigt den Abschluss einer echten Worker-Berechnung;
er verwendet einen gesonderten, nicht vorpositionierten 200-Knoten-Korpus.

Die Zahlen begründen vorerst keinen Wechsel zu WebGL. Canvas bleibt erhalten.
Sehr dichte Graphen, Layoutqualität bei 20.000 frei angeordneten Knoten und
abweichende Clienthardware brauchen weitere Messungen. Die Erhöhung auf 10.000 Knoten ist ein ausdrücklicher Folgeauftrag;
eine Freigabe beliebiger 20.000-Knoten-Bestände folgt daraus nicht.


## Höhere Standardgrenze

`KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES=10000` und
`KNOWLEDGE_GRAPH_OVERVIEW_MAX_CODE_EDGES=100000` werden im Standard-Compose
explizit ans Backend übergeben und sind in `.env.example` dokumentiert.
Request-Parameter dürfen die konfigurierte Knotengrenze nur verkleinern.
Eine höhere Knotengrenze vervielfacht die Dateikanten nicht unbegrenzt:
Es gilt das kleinere Budget aus 20 Dateikanten je Knoten und dem separaten
Maximum. Dokumentations-/manuelle Kanten haben weiterhin keinen separaten harten
Kantendeckel.

Seit dem 29.10.2026 bildet der Server die Dateikanten aus allen Parser-Beziehungen
statt aus einer Stichprobe von Roh-Beziehungen. Ab 1.000 Dateikanten zeigt die
Übersicht nur das Grundgerüst (je Datei die 3 gewichtigsten Kanten, je
Beziehungsart mindestens 3); die übrigen Kanten sind über `degree` als nicht
geladen erkennbar und im Frontend nachladbar. Das Grundgerüst berechnet der Parser
am Ende jedes Syncs je Projekt vor (`doctus_models/code_file_edges.py`, Tabelle
`code_file_edges`); die Übersicht liest nur diese Tabelle und rechnet nur dann direkt,
wenn für ein Projekt noch nichts berechnet ist. Die Abschnitte unten beschreiben den
Stand davor.

### Messung Dateikanten-Vorberechnung (29.10.2026)

Echte Bestände (Übersicht gesamt, aus der Tabelle):

| Projekt | Beziehungen | Dateikanten | Grundgerüst | Übersicht vorher (direkt) | Übersicht jetzt | Neuberechnung je Sync |
|---|---|---|---|---|---|---|
| CardDemo | 16.758 | 284 | 284 | 0,2 s | < 0,1 s | 1,7 s |
| Spring WS | 62.044 | 3.474 | 1.867 | 0,5 s | 0,3 s | 0,4 s |
| Apache Syncope | 325.594 | 25.654 | 7.934 | 2,9 s | 1,8 s | 2,0 s |

Synthetischer Bestand in einer Wegwerf-Datenbank (100.000 Dateien, 1 Mio. Entities,
10 Mio. Beziehungen, Postgres 16 mit `work_mem` = 4 MB): Die Ziele streuen stärker
als in echtem Code, 10 Mio. Beziehungen ergeben 8,8 Mio. Dateikanten (Syncope: im
Schnitt 13 Beziehungen je Dateikante). Die Zahlen sind daher eher ungünstig.

| Schritt | Zeit |
|---|---|
| Dateikanten bei jedem Öffnen direkt zusammenfassen (alter Weg) | 119–129 s |
| Grundgerüst am Sync-Ende neu berechnen | 142 s |
| Grundgerüst aus der Tabelle lesen (100.000 Kanten) | 1,9–2,0 s |
| Belegstellen der gelieferten Kanten laden | 1,2 s |

Die Tabelle speichert nur das Grundgerüst (183.346 Zeilen, 36 MB). Eine erste Fassung
mit allen Dateikanten war 1,36 GB groß und las sich langsamer (3,9–7,7 s).
Offen: Die Neuberechnung läuft bei jedem Sync für das ganze Projekt; bei solchen
Größen wäre eine Neuberechnung nur der betroffenen Dateien die nächste Stufe.

### Gewichtung bei Hubs (29.10.2026)

Befund an CardDemo: 87 % der Dateikanten führen von einem Programm zu einem Copybook, vier
Copybooks binden je 21 der 44 Programme ein. Eine Copybook-Kante sammelt Hunderte Lese- und
Schreibzugriffe, ein CALL zählt 1. Bei Gleichstand der Rolle gewann die Zahl, also verloren die
Aufrufe des Anmeldeprogramms ins Haupt- und Admin-Menü. Gruppen hießen nach dem Hub-Copybook.

Jetzt: innerhalb derselben Rolle gehen Kontrollfluss-Kanten vor Einbindungen, dann Kanten zu
Nachbarn mit wenig Verbindungen, zuletzt die Zahl. Der Mittelpunkt einer Gruppe (und damit ihr
Name) ist die Datei mit dem höchsten Gewicht unter denen, die selbst auf andere verweisen.
Mit `BACKBONE_MIN_FILE_EDGES = 0` verglichen:

| Projekt | Grundgerüst alt → neu | Zusammenhangskomponenten | Größter Hub, Kanten im Grundgerüst |
|---|---|---|---|
| CardDemo | 177 → 153 (CALL 4/6 → 6/6) | 6 → 9 (Anwendungsfamilien statt eine Masse) | COCOM01Y 16 → 3 |
| Spring WS | 1.867 → 1.731 | 27 → 27 | MessageContext 73 → 26 |
| Apache Syncope | 7.934 → 7.108 | 6 → 5 | Entity 67 → 29 |

Die Hubs behalten weniger Kanten, die übrigen sind über „+N“ erreichbar. Neue Gruppennamen bei
CardDemo: „app · CORPT00C“, „app · COCRDUPC“ statt „app · COCOM01Y“, „app · CSDAT01Y“.

### Gruppen-Knoten (29.10.2026)

Louvain auf dem vollständigen Dateigraphen, Topics gehen vor, Gruppen über 150 Dateien
unterteilt. „Innen“ = Anteil der Dateikanten innerhalb einer obersten Gruppe.

| Projekt | Gruppen (oberste) | Innen | Zeit |
|---|---|---|---|
| CardDemo | 17 (17) | 58 % | 0,3 s |
| Spring WS | 44 (44) | 59 % | 1,0 s |
| Apache Syncope | 98 (24, zwei Unterstufen) | 63 % | 1,2 s |

Zum Vergleich: Verzeichnisse als Gruppen erreichen bei CardDemo 2 % (Ablage nach
Dateiart), bei Syncope 30–36 %; Label Propagation hinterließ bei Syncope eine Gruppe mit
1.098 Dateien. Nur aus dem Grundgerüst gerechnet sinkt Syncope auf 23 %.

Skalierung (synthetisch, nur Gruppenbildung): 200.000 Dateikanten 3,5 s / 244 MB,
600.000 12,5 s / 651 MB, 1 Mio. 25,7 s / 1,06 GB. Darüber gruppiert Louvain Verzeichnisse.

Übersicht mit Gruppen (ab 1.000 Dateikanten; der Browser schickt die aufgeklappten Gruppen
mit, `GET /graph?expanded=…`): Syncope eingeklappt 42 Knoten (24 Gruppen, 21 Dokumente,
1 Erkenntnis) und 271 Kanten statt 3.425 Knoten und 8.054 Kanten, Antwort 0,05 s.
Aufklappen 0,03–0,28 s (Spring WS, Gruppe mit 117 Dateien: 0,28 s). CardDemo bleibt unter
der Schwelle bei Dateien.

Die Backend-Suite besteht mit zwei neuen Grenz-/Trunkierungsfällen 731 Tests
(2 übersprungen). Der Browsermesslauf kann über `GRAPH_BENCH_GRAPH=<json>`
zusätzlich einen lokalen `/graph`-Snapshot verwenden; dieser wird nicht ins
Repository übernommen. Nicht vorpositionierte Graphen warten auf einen
bestätigten Worker-Abschluss, statt eine feste Wartezeit als Abschluss zu werten.

### Lokale Bestandsprüfung

[`syncope-validation.json`](evidence/knowledge-graph-performance-2026-10-27/syncope-validation.json)
enthält die Prüfung am derzeit lokal indexierten Apache-Syncope-Bestand.
Die alte 2.000-/40.000-Auswahl lieferte 1.155 Knoten und 3.759 Dateikanten;
mit 10.000 Knoten und maximal 100.000 Roh-Codebeziehungen werden 2.493 Knoten
und 10.165 Kanten geliefert. Das Rohbeziehungsbudget bleibt ausgeschöpft und
`edges_sampled=true`; auch diese größere Ansicht ist keine Vollständigkeitszusage.

Die echte Browserprobe bestätigt Worker-Abschluss und Auswahl. Im dichteren,
frei angeordneten Bestand erreicht sie etwa 26 FPS beim Zoom und 60 FPS bei
ruhender Auswahl. Die 59 FPS des synthetischen Gitters sind daher keine
allgemeine Garantie. Der größere Backend-Aufbau benötigt mehr Zeit und Speicher;
die Messdatei dokumentiert Dauer, unkomprimierte Antwortgröße (rund 20 MB) und
Spitzen-RSS des separaten Probeprozesses. Daten wurden nur gelesen. Der
Quellgraph selbst wurde ausschließlich temporär lokal gespeichert.

Die erhöhte Grenze ist lokal im laufenden Backend aktiv; Backend und Frontend
sind gesund. CI für `a60e5dd` ist mit allen elf Jobs grün, einschließlich der
aufgenommenen Graph-Browserfälle und des Produktions-Worker-Smokes.
