# Link Manager: Steuerung und Analyse-Dialog

Auftrag vom 27.10.2026: Analysekonfiguration aus der Kopfzeile auslagern,
Code↔Code als Beziehungsfilter ergänzen und Desktop-Mehrpanel-Layouts prüfen.

Die Kopfzeile enthält Projektkontext und Icons für Analyse, manuelles Verknüpfen,
Aktualisieren und den Wechsel zu Topics. Ein Klick auf „Analyse starten“ öffnet
einen Dialog mit Modell, Mindest-Wahrscheinlichkeit, Budget, Quellen und
erweiterten Laufoptionen. Der Klick allein startet keinen Job. Die bestehende
Aufwandsschätzung und ihre Bestätigung bleiben vor dem tatsächlichen Start.
Abbrechen erhält die Einstellungen; Escape und Schließen geben den Fokus an
das Start-Icon zurück. Bei Projektwechsel wird auch der Dialog zurückgesetzt.

Status und Beziehungsart passen sich an die Breite des Panels an, statt an die
Browserbreite. In schmalen Panels werden Auswahllisten verwendet. Der Dialog
liegt über der gesamten Arbeitsfläche; sein Inhalt scrollt bei Bedarf, während
die Aktionsleiste sichtbar bleibt. Mobile Layouts sind nicht Teil der Abnahme.

Die Beziehungsfilter sind „Alle“, „Code↔Code“, „Code↔Doc“ und „Doc↔Doc“.
Entscheidend sind Endpunkttyp und konkrete Code-Referenz, nicht der API-Endpunkt:
Auch gemischte Knowledge-Links landen bei Code↔Doc. Bestehende Navigation,
Bewertungsaktionen, Projektisolation und absteigende Score-Reihenfolge bleiben.

## Prüfung

- TypeScript, ESLint und Design-Token-Prüfung bestehen (bestehende Warnung des
  TanStack-Virtualizers bleibt).
- 950 Frontend-Tests, 731 Backend-Tests (2 übersprungen), 733 Parser-Tests
  (5 übersprungen) bestanden auf getrennten Testdatenbanken.
- 10 Browserfälle prüfen 1280/1440/1920 Pixel breite Desktop-Fenster, ein bis
  vier Panels, einen 25-Prozent-Split, Größenänderungen, beide Themes,
  englische Labels, größere Schrift, Tastaturfokus und tatsächlichen Analyse-Start.
- Sämtliche API-Antworten der Layout-Browserfälle werden ersetzt; es werden
  keine Analysejobs oder Quellen in der laufenden Anwendung angelegt.
- Die Browserfälle sind im E2E-Job der CI enthalten.

Ansichten: [vier Panels](evidence/link-manager-layout-2026-10-27/four-panels.png),
[Analyse-Dialog](evidence/link-manager-layout-2026-10-27/analysis-dialog.png),
[größere englische Schrift / helles Theme](evidence/link-manager-layout-2026-10-27/english-large-text.png).

## Eingeschränkter Lauf: zwei Mengen gegeneinander (Auftrag 06.11.2026)

Der Analyse-Dialog grenzt einen Code↔Doc-Lauf auf zwei Mengen ein: Code-Entitäten
gewählter Typen und Dokumentation gewählter Wissensquellen, etwa COBOL-Programme und
Sections gegen ein PDF-Handbuch oder Jira. Die Typen stehen je Sprache gruppiert
(`services/link_run_scope.py::language_of_type`: Sprachprofil, sonst Typ-Zuordnung, sonst
„Weitere“), mit Anzahl; je Sprache lassen sich alle Typen an- und abwählen. Quellen
erscheinen nur, wenn sie Dokumentation tragen (bei Git nur AsciiDoc/Markdown/Text).
Ohne Auswahl gilt die ganze Seite.

- API: `GET /projects/{id}/link-recommendations/scope-options` (Typen je Sprache,
  Quellen mit Abschnittszahl, Auswahl des letzten von einer Person gestarteten Laufs);
  `estimate` und `compute` nehmen `entity_types` und `doc_source_ids` (wiederholbar).
  Dokumentations-Typen und projektfremde Quellen werden mit 422 abgelehnt.
- Die Auswahl steht in `LinkBuilderRun.scope_json["filter"]`; Fortsetzen im Job Center
  übernimmt sie. Der Dialog schlägt je Projekt die Auswahl des letzten Laufs vor.
- Ein eingeschränkter Lauf prüft alle gewählten Entitäten gegen die gesamte gewählte
  Dokumentation, nicht nur Geändertes. Er arbeitet die Änderungs-Warteschlange nicht ab
  und zählt nicht als Erstlauf: Ein späterer Lauf ohne Einschränkung macht den Backfill
  bzw. den inkrementellen Lauf wie zuvor (`parser/tasks/link_run_scope.py`).
- Budget und erweiterte Optionen (u. a. Kandidaten je Modellaufruf) gelten unverändert.
