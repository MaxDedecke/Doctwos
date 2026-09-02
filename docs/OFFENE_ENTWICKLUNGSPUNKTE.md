# Doctwos — Offene Entwicklungspunkte

**Stand:** 02.09.2026
**Zweck:** Zentrale Liste für noch offene Änderungen, Abnahmen und Entscheidungen.

Neue offene Punkte werden ausschließlich hier aufgenommen. Erledigte Punkte bleiben
zur Nachvollziehbarkeit mit Erledigungsdatum und Verweis dokumentiert. Die
Detailplanung einzelner Arbeiten kann weiterhin in den verlinkten Quelldokumenten
stehen.

## Aktuell offen

| ID | Bereich | Punkt | Status / nächste Aktion | Abhängigkeit |
|---|---|---|---|---|
| O-001 | Performance / Abnahme | Formale Lasttest-Abnahme mit einem echten oder repräsentativen DRV-COBOL-Bestand durchführen. | Bestand bereitstellen, anschließend Persistenz- und Embedding-Durchsatz messen und abnehmen. Der synthetische Lauf ist nur ein Vorab-Signal. | Fujitsu/DRV: Bestand und Abnahmekriterien |
| O-002 | Barrierefreiheit | Formale BITV-Abnahme durchführen. | Verbindlichen Prüfumfang festlegen und manuellen Prüfschritt organisieren. Der automatisierte axe-core-Basischeck ist vorhanden. | Auftraggeber / Prüfstelle |
| O-003 | Design | Farbkontrast der Fujitsu-Farbtöne prüfen und gegebenenfalls nachbessern. | Markenfreigabe für zulässige Farbabweichungen einholen; danach zentrale Design-Tokens anpassen. | Markenverantwortliche |
| O-004 | Frontend-Architektur | Domänen-State aus `frontend/app/page.tsx` in eigene Hooks bzw. Context-Provider auslagern. | **Erledigt 02.09.2026:** `useProjects`, `useChatSessions`, `useKnowledgeSources` und `useWorkspaceLayout` extrahieren jeweils ihren State sowie die zugehörigen Lade-/Navigationslogiken; Typecheck, Lint, 18 Tests und Produktions-Build grün. | Keine externe Abhängigkeit |
| O-005 | Frontend-Performance | Nach O-004 `useCallback`/`memo` gezielt ergänzen. | **Erledigt 02.09.2026:** weitergereichte Navigations-, Session-, Chat-, Projekt- und Layout-Handler stabilisiert; Settings-Context sowie Header-Suche und Sidebar memoisiert. `tsc`, ESLint, 18 Tests und Produktions-Build grün. | O-004 |
| O-006 | Git-Import | Repack-Nachlauf (`git repack -a -d` und `fetch --refetch`) nach der Erstindexierung bewerten und gegebenenfalls implementieren. | Entscheidung anhand eines echten großen Bestands treffen; anschließend Durchsatz und Speicherverbrauch vergleichen. | Großer Testbestand |
| O-007 | Fachliche Anforderungen | Klären, ob CSV-Unterstützung aus Plan §13 / F-018 tatsächlich erforderlich ist. | Anforderung bestätigen oder als veraltet markieren; bei Bestätigung Umfang und betroffene Upload-/Connector-Flächen festlegen. | Fachliche Entscheidung |
| O-008 | Test-/Entwicklungsumgebung | Entscheidung treffen, ob Ollama in CI verbindlich getestet werden soll. | CI-Strategie festlegen: echter Ollama-Service, dedizierter optionaler Job oder bewusstes Ausnehmen mit dokumentierter Begründung. | Teamentscheidung / CI-Ressourcen |
| O-009 | COBOL-Parser / XREF | Quellenweiten Feldindex über Copybook-Grenzen vollständig in `parse.py` integrieren. | Copybooks als eigene Entities parsen, geerbte Felder inklusive `REPLACING` auflösen und das Mengengerüst der `USES`-Kanten prüfen. | Repräsentativer COBOL-Bestand für die Mengenbewertung |
| O-020 | Link Manager / Layout | Link-Manager-View sieht fehlerhaft aus, wenn drei weitere Views geöffnet sind. | Responsive Layout, verfügbare Breite und Überlauf mit vier geöffneten Views prüfen und korrigieren. | Keine externe Abhängigkeit |
| O-021 | View-Layout | Das Verhältnis der Views soll per Drag-and-drop mit der Maus horizontal und vertikal veränderbar sein. Das Fadenkreuz aus horizontalem und vertikalem Abstand zwischen den Views soll als gemeinsamer Resize-Griff dienen. | Interaktiven Kreuz-/Trennlinien-Griff umsetzen, Größenänderung in beide Richtungen ermöglichen und Mindestgrößen sowie Verhalten bei mehreren Views testen. | Keine externe Abhängigkeit |
| O-022 | Beobachtbarkeit / Sicherheit | Serverseitig protokollieren, welche MCP-Werkzeuge mit welchen Argumenten pro Chat-Turn ausgeführt wurden. | Strukturierten, datensparsamen Audit-Log für Tool-Aufrufe ergänzen und Aufbewahrung sowie Einsicht durch Admins festlegen. | Fachliche Entscheidung zur Aufbewahrung |

## Umsetzungs- und Übergabestatus

Die Arbeitspakete AP-0 bis AP-9 sind technisch als abgeschlossen dokumentiert.
Drei Punkte sind Übergaben an Fujitsu/DRV: die formale Lasttest-Abnahme am
echten Bestand, die formale BITV-Abnahme sowie eine mögliche
Farbkontrast-Nachbesserung nach Markenfreigabe. Der synthetische Lasttest und
der automatisierte axe-core-Basischeck sind bereits vorhanden.

Die technischen Abschlussarbeiten (npm-CVE-Fix und Behebung des
Embedding-Timeout-Problems) sind erledigt; die zugehörigen Entscheidungen
stehen im [Entscheidungslog](ENTSCHEIDUNGEN.md).

## Bewusst nicht als offene Codeänderung geführt

Diese Punkte sind derzeit keine ungeklärten Implementierungsaufträge:

- Der Embedding-CPU-Timeout wurde durch Sub-Batches und einen konfigurierbaren
  Timeout behoben (E-8, 08.08.2026).
- Der frühere GPL-Fund `Unidecode` wurde durch das MIT-Shim ersetzt (E-7,
  08.08.2026); er ist kein Release-Blocker mehr.
- Die Refaktorierung des `SettingsModal` bis zur Shell und die Aufteilung der
  Tabs ist erledigt. Die verbliebenen `page.tsx`-Nacharbeiten aus O-004/O-005
  und O-027 sind ebenfalls abgeschlossen.
- Die frühere Testlücke bei Orphan-Schutz und Chunked-Downloads wurde in AP-8
  geschlossen.

## Erledigt, zuletzt verschoben

- O-004 (Frontend-Domänen-Hooks) — 02.09.2026 umgesetzt; Projekt-, Quellen-,
  Chat-Session- und Workspace-Layout-Zustände sind aus `app/page.tsx` in
  englisch dokumentierte Hooks ausgelagert. Typecheck, Lint, 18 Frontend-Tests
  und Produktions-Build grün.
- O-005 (gezielte Frontend-Performance) — 02.09.2026 umgesetzt; weitergereichte
  Handler verwenden stabile Callback-Identitäten, der Settings-Context erhält
  ein memoisiertes Value-Objekt und die unabhängig renderbaren Header-/Sidebar-
  Bereiche sind memoisiert. Typecheck, Lint, 18 Frontend-Tests und
  Produktions-Build grün.
- O-024 (Chat-Orchestrierung) — 02.09.2026 umgesetzt; Chat-Streaming, Senden,
  Retry/Regenerate, Session-Auswahl/-Löschung und Teilen in
  `useChatController` ausgelagert. URL-Synchronisierung und Workspace-Restore
  bleiben als App-weite Brücken erhalten. Mit drei gezielten Controller-
  Regressionstests sowie insgesamt 21 Frontend-Tests, Typecheck, ESLint und
  Produktions-Build verifiziert (Commit `bd0f3b9`).
- O-025 (Panel-/Datei-/Entity-Navigation) — 02.09.2026 umgesetzt; Routing,
  Fokusweitergabe, History-Navigation sowie Fixierung, Live-Panels und mobile
  Navigation in `usePanelNavigation` ausgelagert. Die gemeinsame Referenzauflösung
  liegt in `referenceTarget`. Mit sechs gezielten Regressionstests sowie insgesamt
  27 Frontend-Tests, Typecheck, ESLint und Produktions-Build verifiziert.
- O-026 (Workspace-Rendering) — 02.09.2026 umgesetzt; Panel-Chrome und Fokusleiste
  liegen in `PanelRenderer`, Mobile-Tabs sowie Desktop-Split/Grid-Layout in
  `WorkspaceShell`. Das Mapping über stabile Panel-Indizes, Panel-History und
  Layoutwechsel bleiben erhalten. 27 Frontend-Tests, Typecheck, ESLint und
  Produktions-Build grün.
- O-027 (AI-Settings) — 02.09.2026 umgesetzt; `useAiSettings` kapselt
  Profilmigration, aktives Profil, Profilparameter, Modellinformationen und
  verfügbare Modelle inklusive localStorage-/API-Lifecycle. `useDisplaySettings`
  kapselt Theme- und Editorpräferenzen inklusive Hydration-sicherer
  Wiederherstellung. Chat, Link Manager und Settings verwenden nun denselben
  Profilwechselpfad; 30 Frontend-Tests, Typecheck, ESLint und Produktions-Build
  grün.
- O-028 (Panel-Content-Rendering) — 02.09.2026 umgesetzt; Chat, Code-,
  Dokument-, Graph-, Web-, Call-Graph- und Link-Manager-Inhalte liegen in
  `PanelContentRenderer`. `page.tsx` ist dadurch von 1.096 auf 947 Zeilen
  reduziert; Panel-State und bereichsübergreifende Navigation bleiben im
  Orchestrator. Auf ausdrückliche Vorgabe wurde für diesen Entwicklungsschritt
  kein Test- oder Buildlauf gestartet.
- O-019 (Chat / LLM-Fokus) — 02.09.2026 umgesetzt; Projekt, Quelle und Pin
  werden pro Chat-Turn als kanonischer Fokus-Snapshot in Request und
  Nachrichtenmetadaten übernommen. Retry/Regenerate verwendet dadurch den
  ursprünglichen Turn-Fokus statt einer späteren UI-Auswahl; Legacy-Metadaten
  bleiben lesbar. Mit sechs gezielten Hook-Tests, Typecheck, ESLint und
  Produktions-Build verifiziert.
- O-018 (Job Center) — 02.09.2026 umgesetzt; abgeschlossene und fehlgeschlagene
  Vorgänge bleiben in der Job-Übersicht sichtbar. Admins können fehlgeschlagene
  Jobs aus der UI neu anstoßen; erfolgreiche Jobs bleiben schreibgeschützt und
  laufende Jobs werden gegen Doppelstarts geschützt. Erfolgreiche Einträge
  können per X aus dem Job-Center entfernt werden, ohne die zugrunde liegende
  Wissensquelle zu löschen; Run-basierte Wiederholungen erzeugen einen neuen
  Lauf und erhalten die Historie. Backend-Berechtigungs-, Queue- und
  Entfernen-Tests sind ergänzt; Frontend-Tests, Typecheck, ESLint,
  Produktions-Build und Service-Smokechecks sind grün.

- O-017 (Fixierte Views / Historie) — 02.09.2026 umgesetzt; die History-Transitionen
  sind jetzt unabhängig von der Fixierung gekapselt. Zurück-/Vorwärtsnavigation
  arbeitet in fixierten und live Panels gleich; beim Aufheben einer Fixierung wird
  die bisherige feste Auswahl als Verlaufseintrag erhalten. 14 Frontend-Tests,
  Typecheck und Produktions-Build grün.
- O-016 (Knoten-Icons) — 02.09.2026 umgesetzt; zentrale Icon-Zuordnung für
  Dokumente, Code-Entitäten und Webquellen in Graph-, Such-, Topic-, Link- und
  Referenzansichten ergänzt, einschließlich Canvas-Darstellung im Knowledge- und
  Call-Graph. Unit-Tests für die Typzuordnung sowie Frontend-Test, Typecheck und
  gezielter Lintlauf grün.
- O-015 (Call Graph / Code View) — 01.09.2026 umgesetzt; Call-Graph-Klicks navigieren bevorzugt in ein live/unfixiertes Code-Panel oder öffnen bei verfügbarem Platz ein neues Code-Panel. Fixierte Code-Views bleiben dabei unverändert; der Routingpfad ist durch Tests für live, fixiert und volle Panelbelegung abgesichert.
- O-011 (Teilen-Funktion) — 01.09.2026 umgesetzt; die Chat-Teilen-Aktion liegt jetzt in der globalen Header-Bar und verwendet weiterhin den bestehenden Link-/Clipboard-Mechanismus inklusive Rückmeldung bei fehlendem Chat.
- O-023 (Chat/Darstellung) — 01.09.2026 umgesetzt; die leere `refs`-Liste wurde nicht mehr als sichtbare `0` gerendert, sodass jede Nutzernachricht ohne Kontext sauber beginnt. Das „ME“-Label wurde durch ein lokales, originales Demo-Mitarbeiter-Avatarbild ersetzt; die Bildbeschreibung ist in Deutsch und Englisch hinterlegt.
- O-014 (Chat/Fokus) — 01.09.2026 umgesetzt; das Projekt-Badge kann über einen zugänglichen X-Button geschlossen werden, nutzt dabei den zentralen Projektwechselpfad und zeigt im allgemeinen Kontext ein „Allgemein“-Badge.
- O-013 (Berechtigungen) — 01.09.2026 umgesetzt; Projekt-, Quellen- und Graph-Zugriffe prüfen jetzt Team- und Projektmitgliedschaft konsistent, globale Modellumschaltung ist auf globale Admins begrenzt, Projektmitglieder können nur aus dem eigenen Team hinzugefügt werden und das Frontend lädt dafür eine projektbezogene Kandidatenliste. Regressionstests für Quellenzugriff, Modellumschaltung und Projektmitgliedschaft ergänzt.
- O-012 (UI-Standarddarstellung) — 01.09.2026 umgesetzt; zentrale Desktop-Skalierung auf 110 %, mobile Basis auf 100 % gesetzt und in den Design Guidelines dokumentiert.
- O-010 (Chat-View schließen und erneut öffnen) — 01.09.2026 umgesetzt; der Chat verwendet nun denselben Schließen-Button wie alle anderen Views und wird über „Ansicht hinzufügen“ mit frischem Panelzustand wieder geöffnet.
- E-7 (`Unidecode`/GPL) — 08.08.2026 durch das MIT-Shim gelöst.
- E-8 (Embedding-Batchgröße und CPU-only-Timeout) — 08.08.2026 umgesetzt.
- AP-8-Testlücken (Orphan-Schutz, Chunked-Download) — in AP-8 geschlossen.
- `SettingsModal`-Tab-Aufteilung — Schritt 2 abgeschlossen; die verbleibenden
  `page.tsx`-Arbeiten sind als O-004 und O-005 weitergeführt.

## Referenzen

- [Tech-Debt-Cleanup-Plan](TECH_DEBT_CLEANUP_PLAN.md) — Detailplanung für O-004/O-005
- [Entscheidungslog](ENTSCHEIDUNGEN.md) — fachliche und technische Entscheidungen

## Pflege

Beim Bearbeiten eines Punktes den Status, die nächste Aktion und das Datum direkt
in dieser Tabelle aktualisieren. Erledigte Punkte nicht löschen, sondern in den
Abschnitt „Erledigt“ verschieben und auf Commit, Testlauf oder Abnahme verweisen.
