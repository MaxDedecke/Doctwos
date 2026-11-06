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

## Analyse-Arbeitsfläche: Menge A gegen Menge B (Auftrag 06.11.2026)

„Analyse starten“ öffnet eine bildschirmbreite Arbeitsfläche (ersetzt den früheren
Analyse-Dialog). Oben wählt man die Analyseart, darunter stehen Menge A, Menge B und die
Laufeinstellungen nebeneinander; die Fußzeile zeigt laufend die Aufwandsschätzung. Die
frühere Bestätigung per Browser-Dialog entfällt, weil die Schätzung vor dem Start sichtbar ist.

**Mengen.** Jede Menge hat eine Art (Code oder Dokumentation) und ist entweder „Alle“ oder
eine „Eigene Auswahl“. Eine eigene Auswahl ist die Vereinigung aus
- Filtern (Facetten): Werte eines Filters gelten mit ODER, verschiedene Filter mit UND
  (Code: Typ je Sprache, Repository; Dokumentation: Wissensquelle, gruppiert nach Quelltyp);
- einzeln gesuchten und hinzugefügten Objekten (Code-Entitäten, Dokumente = Quelle + Datei/Seite/Ticket).

Sie darf leer beginnen; gestartet wird erst, wenn beide Mengen etwas enthalten. Jede Menge
zeigt ihre Größe und eine Stichprobe. Filter stehen vor der Suche und erscheinen, sobald sie einen Wert haben.

**Analysearten.** Code ↔ Dokumentation (Entity-Links, alle Nutzer) und Dokumentation ↔
Dokumentation (Knowledge-Links, nur Administratoren; ersetzt die frühere Quellen-Auswahl
„Cross-Source“). Code ↔ Code bietet die Arbeitsfläche nicht an; das ist der Aufrufgraph.
Code ↔ Dokumentation mit „Alle“ auf beiden Seiten bleibt der inkrementelle Lauf über die
Änderungs-Warteschlange (einmaliger Erstlauf, danach nur Geändertes). Jede Einschränkung macht
daraus einen gezielten Lauf: Er prüft jedes Objekt aus A gegen die ganze Menge B, lässt die
Warteschlange unberührt und zählt nicht als Erstlauf. Dokumentation ↔ Dokumentation prüft
jeden Abschnitt aus A gegen Abschnitte aus B aus anderen Quellen; beide Seiten enthalten nur
Dokumentation (bei Git nur AsciiDoc/Markdown/Text).

**Speicherung.** Die Mengen stehen in `LinkBuilderRun.scope_json["sets"]`
(`{"pairing", "a", "b"}`), das Fortsetzen im Job Center übernimmt sie. Die Arbeitsfläche schlägt
je Projekt und Analyseart die Auswahl des letzten von einer Person gestarteten Laufs vor.
Unlesbare Mengen lassen den Lauf fehlschlagen, statt still den ganzen Bestand zu prüfen.

**API** (`backend/api/link_runs.py`): `GET /projects/{id}/link-runs/options` (Analysearten,
Facetten mit Anzahlen, letzte Auswahl), `GET …/search?kind=code|docs&q=`, `POST …/preview`,
`POST …/estimate`, `POST /projects/{id}/link-runs` (Start). Die Einzel-Endpunkte
`/link-recommendations/compute` und `/knowledge-links/compute` bleiben unverändert erhalten.

### Erweitern

Das Mengenformat ist sprach- und quellenneutral (`packages/doctus-models/doctus_models/link_sets.py`).
Neue Sprachen und Quelltypen erscheinen ohne Codeänderung als neue Gruppe; bekannte Namen
bekommen nur einen Übersetzungseintrag (`linkManagerView.workspace.languages|sourceTypes`).
- Neue Facette: Bedingung in `link_sets.FACETS`, Werte in `services/link_set_options.py::_FACET_VALUES`,
  Bezeichnung `linkManagerView.workspace.facets.<art>.<name>`.
- Neue Objektart: Schlüsselfelder in `link_sets.ITEM_KINDS`, Bedingung in `_ITEM_CONDITIONS`,
  Suche/Stichprobe in `link_set_options._SEARCH`/`_SAMPLE`, Schlüssel in `frontend/lib/linkSets.ts::ITEM_KEY_FIELDS`.
- Neue Typzuordnung zu einer Sprache: `link_set_options._TYPE_LANGUAGES` (sonst Sprachprofil bzw. Präfix).
- Neue Analyseart: Eintrag in `link_sets.PAIRINGS` und ein Lauf, der A und B über `set_condition` liest.
