# Doctwos — Offene Entwicklungspunkte

**Stand:** 01.09.2026
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
| O-004 | Frontend-Architektur | Domänen-State aus `frontend/app/page.tsx` in eigene Hooks bzw. Context-Provider auslagern. | Cluster für `useProjects`, `useChatSessions`, `useKnowledgeSources` und `useWorkspaceLayout` einzeln herauslösen und jeweils per Typecheck, Tests und Browserprüfung verifizieren. | Keine externe Abhängigkeit |
| O-005 | Frontend-Performance | Nach O-004 `useCallback`/`memo` gezielt ergänzen. | Nur für tatsächlich weitergereichte Handler und betroffene Kindkomponenten messen und umsetzen. | O-004 |
| O-006 | Git-Import | Repack-Nachlauf (`git repack -a -d` und `fetch --refetch`) nach der Erstindexierung bewerten und gegebenenfalls implementieren. | Entscheidung anhand eines echten großen Bestands treffen; anschließend Durchsatz und Speicherverbrauch vergleichen. | Großer Testbestand |
| O-007 | Fachliche Anforderungen | Klären, ob CSV-Unterstützung aus Plan §13 / F-018 tatsächlich erforderlich ist. | Anforderung bestätigen oder als veraltet markieren; bei Bestätigung Umfang und betroffene Upload-/Connector-Flächen festlegen. | Fachliche Entscheidung |
| O-008 | Test-/Entwicklungsumgebung | Entscheidung treffen, ob Ollama in CI verbindlich getestet werden soll. | CI-Strategie festlegen: echter Ollama-Service, dedizierter optionaler Job oder bewusstes Ausnehmen mit dokumentierter Begründung. | Teamentscheidung / CI-Ressourcen |
| O-009 | COBOL-Parser / XREF | Quellenweiten Feldindex über Copybook-Grenzen vollständig in `parse.py` integrieren. | Copybooks als eigene Entities parsen, geerbte Felder inklusive `REPLACING` auflösen und das Mengengerüst der `USES`-Kanten prüfen. | Repräsentativer COBOL-Bestand für die Mengenbewertung |
| O-011 | UI / Navigation | Teilen-Funktion aus der Chat-View in die Header-Bar verschieben. | Header-Aktion ergänzen und bestehende Chat-Funktion dort anbinden. | Keine externe Abhängigkeit |
| O-013 | Berechtigungen | Berechtigungskonzept auf Konsistenz prüfen. | Rollen, Projektzugriff, Quellenzugriff und Aktionen über Frontend und Backend hinweg abgleichen. | Fachliche Freigabe der Rollenregeln |
| O-014 | Chat / Fokus | Projekt-Badge im Chat per X schließbar machen; bei allgemeinem Kontext soll ebenfalls ein „Allgemein“-Badge angezeigt werden. | Badge-Zustand, Entfernen des Projektfokus und allgemeiner Kontext konsistent modellieren. | Keine externe Abhängigkeit |
| O-015 | Call Graph / Code View | Klicks in der Call-Graph-View dürfen die fixierte Code-View nicht unerwartet verändern. | Fixierungslogik und Navigationsevents entkoppeln; Verhalten mit fixierter und nicht fixierter View testen. | Keine externe Abhängigkeit |
| O-016 | Knoten-Icons | Dokumentknoten sollen ein Doku-Icon, Codeknoten ein `</>`-Icon und Webquellen ein Globus-Icon anzeigen. | Einheitliche Typzuordnung und Darstellung in allen Graph-/Listenansichten umsetzen. | Keine externe Abhängigkeit |
| O-017 | Fixierte Views / Historie | Wenn eine View fixiert ist, soll die Historie dieser View weiterhin über die Pfeile bedienbar sein. | Historiennavigation von der Fixierungslogik trennen und mit mehreren Views prüfen. | Keine externe Abhängigkeit |
| O-018 | Job Center | Job-Center-Einträge verschwinden nie und können nicht gelöscht werden. | Aufbewahrungs- und Löschkonzept definieren; Löschmöglichkeit oder automatische Bereinigung implementieren. | Fachliche Entscheidung zur Aufbewahrungsdauer |
| O-019 | Chat / LLM-Fokus | Der LLM-Fokus kann sich vom angepinnten Objekt im Chat lösen. | Fokuszustand zwischen UI, Request-Metadaten und Antwortkontext durchgängig synchronisieren und sichtbar machen. | Keine externe Abhängigkeit |
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
  Tabs ist erledigt. Offen bleiben dort nur die in O-004/O-005 genannten
  `page.tsx`-Nacharbeiten.
- Die frühere Testlücke bei Orphan-Schutz und Chunked-Downloads wurde in AP-8
  geschlossen.

## Erledigt, zuletzt verschoben

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
