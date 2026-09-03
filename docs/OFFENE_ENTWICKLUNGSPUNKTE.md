# Doctwos — Offene Entwicklungspunkte

**Stand:** 03.09.2026
**Zweck:** Zentrale Liste für noch offene Änderungen, Abnahmen und Entscheidungen.

O-029 bis O-036 stammen aus einem Abgleich des [Anforderungskatalogs](ANFORDERUNGSKATALOG.md)
gegen den tatsächlichen Codestand (03.09.2026, Ground Truth `ff4c864`): für jede dort als
TEILWEISE geführte Anforderung wurde am Code geprüft, ob die Lücke noch besteht.

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
| O-007 | Fachliche Anforderungen | Klären, ob CSV-Unterstützung aus Plan §13 / F-018 tatsächlich erforderlich ist. | Anforderung bestätigen oder als veraltet markieren; bei Bestätigung Umfang und betroffene Upload-/Connector-Flächen festlegen. | Fachliche Entscheidung |
| O-008 | Test-/Entwicklungsumgebung | Entscheidung treffen, ob Ollama in CI verbindlich getestet werden soll. | CI-Strategie festlegen: echter Ollama-Service, dedizierter optionaler Job oder bewusstes Ausnehmen mit dokumentierter Begründung. | Teamentscheidung / CI-Ressourcen |
| O-029 | Frontend-Layout | 3-Spalten-Layout (`3-col`) hat keinen ziehbaren Teiler. O-021 hat nur `split` (2 Panels, bestand schon vorher) und `4-grid` (neuer Kreuzgriff) resizable gemacht; `3-col` rendert in `WorkspaceShell.tsx` weiterhin starr zu gleichen Dritteln — keine der beiden Resize-Branches (`handleDividerMouseDown`/`handleGridResizePointerDown`) greift für diesen Layoutmodus. | Kreuzgriff- bzw. Divider-Mechanik aus O-021 auf `3-col` übertragen (zwei Teiler statt einem/einer Kreuzung). | O-021 (technische Basis vorhanden) |
| O-030 | Backend / Ingestion | `POST /knowledge-sources/upload` (`backend/api/knowledge_sources.py`) hat keine serverseitige Extension-Allowlist — nur die UI begrenzt die Dateiauswahl auf `.pdf`/`.md`/`.txt`; ein direkter API-Call nimmt jede Datei entgegen und schickt sie in die Verarbeitungs-Pipeline. | **Erledigt 03.09.2026:** serverseitige Allowlist `_ALLOWED_UPLOAD_EXTENSIONS` (`.pdf`/`.md`/`.txt`, synchron zur UI-`accept`-Liste) prüft die Dateiendung vor dem Anlegen der Knowledge-Source und lehnt Abweichungen mit HTTP 400 ab. Neuer Testfall `test_upload_local_document_rejects_disallowed_extension`; bestehender Traversal-Test auf eine erlaubte Endung (`passwd.txt`) umgestellt, da er zuvor ohne Endung lief. | Keine |
| O-031 | Backend / Ingestion | Lokaler Upload-Pfad (`parser/tasks/document.py::process_local_document_async`) hat keinen OCR-Fallback für Bild-PDFs. Folder-/WebDAV-Connectoren teilen sich dafür bereits `connectors/folder.py::_extract_text` (inkl. OCR); `document.py` extrahiert PDF-Text separat und dupliziert die Logik ohne OCR. | **Erledigt 03.09.2026:** neue geteilte Funktion `connectors/folder.py::extract_pdf_pages` (seitenweise Extraktion inkl. OCR-Fallback bei fehlendem Text-Layer, Seitenzuordnung geht dabei auf `page_no=None` zurück). `_extract_text` (Folder-/WebDAV-Pfad) baut jetzt darauf auf; `document.py` ruft dieselbe Funktion statt eigener `pypdf`-Logik auf und erhält damit den OCR-Fallback für lokale Uploads. Bestehende Tests (`test_folder_connector.py`, `test_document_reindex_link_stability.py`, volle Parser-Suite: 175 von 176 grün, ein vorbestehender, unabhängiger Fehlschlag in `test_ap4_persistence.py` reproduzierbar auf unverändertem Code) verifiziert; kein neuer Test ergänzt (siehe Doku-/Test-Aufschub-Regel). Parser-Worker neu gebaut und ausgerollt. | Keine |
| O-032 | Backend / Sicherheit | Chat-Share-Mechanik war schwächer geschützt als beabsichtigt: `GET /chat/sessions/by-uuid/{uuid}` und `.../messages` prüften `ChatSession.is_public` nicht und verlangten keine Authentifizierung — jede Session war über ihre UUID lesbar, auch wenn sie nie geteilt wurde. `PATCH /chat/sessions/{id}/snapshot` und `PATCH /chat/messages/{id}/feedback` waren zusätzlich über eine fortlaufende Integer-`session_id`/`message_id` statt UUID adressiert und (Snapshot komplett, Feedback ohne Owner-/Public-Prüfung) ohne echte Zugriffskontrolle erreichbar. | **Erledigt 03.09.2026 (`de2c9c1`):** neue Zugriffsregel `owner_id == user.id or is_public` (`_session_accessible` in `backend/api/chat.py`) jetzt einheitlich durchgesetzt auf den `by-uuid`-Leserouten, dem Snapshot-/Feedback-Update, dem `/chat`-Fortsetzen einer fremden `session_id` sowie zusätzlich auf `GET /chat/sessions/{id}/messages` (dieselbe Lücke — sequentielle ID, bislang komplett ohne Auth/Owner-Check, war im Audit nicht extra erfasst, aber derselbe Fall). Da nichts `is_public` je auf `True` setzte, war die Freigabe-Funktion faktisch nie benutzbar (siehe DOC-F-070); neuer Endpunkt `POST /chat/sessions/{id}/share` (Owner-only) setzt es jetzt explizit beim Klick auf „Chat teilen" (`useChatController.ts::handleShareChat`). 8 neue Testfälle in `backend/tests/test_chat_sessions.py` (15 gesamt grün), `tsc --noEmit` grün, Backend+Frontend neu gebaut und ausgerollt. | Keine |
| O-033 | Backend / Verschlüsselung | `ChatMessage.metadata_json` (u. a. `refs`) und `feedback` liegen unverschlüsselt in der DB; nur `content` ist als `EncryptedString` modelliert. | Fachlich klären, ob Metadaten/Refs schutzwürdige Auszüge enthalten können; falls ja, Verschlüsselung erweitern. | Fachliche Einschätzung nötig |
| O-034 | Backend / Knowledge Graph | Der Knowledge-Graph-Endpunkt (`backend/api/graph.py`) bietet nur `/export/neo4j` (Cypher); anders als der Callgraph (JSON/CSV/GraphML) gibt es keinen neutralen CSV-/GraphML-Export. | CSV-/GraphML-Export analog zum Callgraph-Export ergänzen; Legacy-Neo4j-Endpunkt danach zur Entfernung vorschlagen. | Keine |
| O-035 | Backend / LLM-Konfiguration | `POST /model-info` (`backend/api/system.py`) verändert weiterhin `cfg.OLLAMA_LLM_MODEL` global im laufenden Prozess statt request-/profilgebunden zu bleiben. | Modellwahl request- bzw. profilgebunden umsetzen, falls Mehrmandantenbetrieb mit unterschiedlichen lokalen Modellen relevant wird. | Fachliche Priorität klären |
| O-036 | Frontend / Performance | Datei-/Entitätslisten in der Seitenleiste sind bei sehr großen Beständen nicht virtualisiert — die volle Liste wird gerendert, keine Virtualisierungsbibliothek im Frontend vorhanden. | Virtualisierung einführen, sobald ein Bestand das in der Praxis spürbar zeigt. | Kein aktueller Release-Blocker, aber Ziel-Skalierung laut CLAUDE.md Prinzip 4 |
| O-037 | Backend / Ingestion | Bei O-030 entdeckt: `POST /knowledge-sources/upload` liefert bei Erfolg einen leeren Response-Body (`{}`) statt der neuen Knowledge-Source. Ursache: `send_tracked_task()` committet nach dem `return`-relevanten letzten Attributzugriff erneut (`record.celery_task_id = task_id; db.commit()`), SQLAlchemy expired danach alle Instanzattribute (`expire_on_commit=True`, Default), und der Endpunkt gibt das ORM-Objekt direkt zurück statt es zu serialisieren — `jsonable_encoder` sieht dadurch ein leeres `__dict__`. Das Frontend (`SourcesSetupTab.tsx::handleFileUpload`) hängt dieses leere Objekt direkt an die Quellenliste an. Zusätzlich rot in der CI (unabhängig davon): `PermissionError: [Errno 13] Permission denied: '/repos'` beim lokalen Datei-Upload-Test — der CI-Runner hat keinen Schreibzugriff auf `UPLOADS_DIR`. Beide Fehlschläge sind vorbestehend (reproduzierbar mit unverändertem `ff4c864`, nicht durch O-030 verursacht) und lassen `test_upload_local_document_creates_source_and_saves_file` sowie `test_upload_local_document_sanitizes_path_traversal_in_filename` weiterhin fehlschlagen. | **Erledigt 03.09.2026 (`d798e3d`):** `upload_local_document` gibt jetzt `serialize_source(db_source)` zurück statt des rohen ORM-Objekts — identisches Muster zu `create_knowledge_source`/`create_git_source`/`create_folder_watch_source`. CI-Workflow (`backend`-Job) legt `/repos/uploads` vor dem Testlauf an und übergibt es dem Runner-User, da dieser Job bare auf `ubuntu-latest` läuft (kein Docker-Compose-Mount für `/repos`). Beide Upload-Tests lokal im neu gebauten `backend-api`-Container grün (`131 passed`; die 3 unabhängig fehlschlagenden `test_chat_llm_provider_guard.py`-Fälle liegen an `ALLOW_CLOUD_LLM=true` in dieser lokalen Compose-Umgebung, nicht an dieser Änderung). Backend neu gebaut und ausgerollt. | Keine |

## Noch zu evaluieren

- O-006 (Git-Performance) — bewusst aus den aktuell offenen
  Implementierungsaufträgen herausgenommen. Nach der providerübergreifenden
  Kompatibilitätsabsicherung für GitHub und Bitbucket soll anhand eines großen,
  repräsentativen Bestands gemessen werden, ob `git repack -a -d` und
  `git fetch --refetch` nach der Ersteinindexierung sinnvoll sind. Zu erfassen
  sind Erst-/Folgesync, Mirror-/Worktree-Größe, Netzwerktraffic sowie CPU-/IO-
  Aufwand. Kein aktueller Release-Blocker.

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

- O-009 (quellenweiter Copybook-Feldindex / XREF) — 02.09.2026 umgesetzt;
  Copybooks werden als eigene Entities geparst, verschachtelte COPYs transitiv
  vererbt, `REPLACING` vollständig angewendet und USES-Kanten pfadgenau auf
  Copybook-Felder nachaufgelöst. COPYs aus der PROCEDURE DIVISION erzeugen
  keine Datenfeldvererbung. Mit Parser-, Persistenz- und Connector-Regressionen
  verifiziert.

- O-022 (MCP-Audit) — 02.09.2026 umgesetzt; MCP-Tool-Aufrufe werden pro Chat-Turn
  mit Nutzer, Session, Projekt/Quelle, Tool, Status und Dauer protokolliert.
  Argumente und Fehlermeldungen werden vor der Speicherung datensparsam bereinigt;
  eine konfigurierbare Aufbewahrung von standardmäßig 90 Tagen sowie eine
  admin-only Einsicht im Logs-Tab sind umgesetzt. Fünf neue Backend-Audit-Tests,
  32 Frontend-Tests, Typecheck, ESLint und Produktions-Build grün.
- O-020 (Link Manager / Layout) — 02.09.2026 umgesetzt; Link-Manager-Header,
  Filterleiste, manuelle Picker und Linkkarten reagieren jetzt auf die tatsächliche
  Panelbreite. In schmalen Zellen werden Inhalte container-basiert gestapelt oder
  gekürzt, sodass der Link Manager auch im Vier-Panel-Layout ohne horizontales
  Überlaufen nutzbar bleibt. 30 Frontend-Tests, Typecheck, ESLint und
  Produktions-Build grün.
- O-021 (View-Layout) — 02.09.2026 umgesetzt; im Vier-Panel-Layout steuert ein
  gemeinsamer Kreuzgriff das horizontale und vertikale Verhältnis per Pointer-Drag.
  Die Mindestgrößen werden bei Maus- und Touch-Eingaben eingehalten, die Werte im
  Workspace-Snapshot gespeichert und beim Wiederherstellen validiert. 32 Frontend-
  Tests, Typecheck, ESLint und Produktions-Build grün.
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
