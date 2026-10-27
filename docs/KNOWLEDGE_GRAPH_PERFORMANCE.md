# Wissensgraph: Performance

Auftrag vom 27.10.2026: Darstellung und Ladepfad bestehender Graphen optimieren,
mit 2.000 und 20.000 Knoten vergleichen; abgeschlossene Schritte auf `develop`
committen und pushen. Die bestehende Canvas-Darstellung wird beibehalten.

## Darstellung

- `knowledgeGraphRendering.ts` bereitet Farben, Radien, Bezeichnungen und
  Parallelkanten vor. Während des Zeichnens gibt es keine DOM-Farbabfragen.
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
Der Standarddeckel von 2.000 Knoten bleibt bis zur gesonderten Abnahme erhalten.

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
