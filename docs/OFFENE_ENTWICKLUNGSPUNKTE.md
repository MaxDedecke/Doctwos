# Doctwos — Offene Entwicklungspunkte

**Stand:** 05.09.2026 (O-044/O-036/O-053 erledigt, O-052/O-054 neu, O-055–O-062 neu — Regressionstest-Aufbau in Häppchen)
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
| O-029 | Frontend-Layout | 3-Spalten-Layout (`3-col`) hat keinen ziehbaren Teiler. O-021 hat nur `split` (2 Panels, bestand schon vorher) und `4-grid` (neuer Kreuzgriff) resizable gemacht; `3-col` rendert in `WorkspaceShell.tsx` weiterhin starr zu gleichen Dritteln — keine der beiden Resize-Branches (`handleDividerMouseDown`/`handleGridResizePointerDown`) greift für diesen Layoutmodus. | **Erledigt 03.09.2026:** zwei ziehbare Teiler für `3-col` ergänzt. Neuer Zustand `threeColLeftPercent`/`threeColRightPercent` (Grenzen zwischen Panel 0/1 bzw. 1/2) in `useWorkspaceLayout`, neue Helper `pointerToPercent`/`clampPercentBetween` in `lib/workspaceResize.ts` (Mindestbreite je Spalte `MIN_THREE_COL_PANEL_PERCENT = 15`, da drei statt zwei Spalten dieselben 100% teilen). `WorkspaceShell.tsx` rendert die Teiler über eine gemeinsame `WorkspaceDivider`-Komponente (auch vom bestehenden `split`-Teiler genutzt). Snapshot-Speichern/-Wiederherstellen sowie `resetWorkspace` ziehen die neuen Werte mit. Neue Tests `useWorkspaceLayout.test.ts` (Drag-Verhalten inkl. Grenzfälle) und ergänzte Fälle in `workspaceResize.test.ts`; `tsc --noEmit`, ESLint, volle Vitest-Suite (43 Tests) und Produktions-Build grün. | O-021 (technische Basis vorhanden) |
| O-039 | Frontend / Workspace | Der Chat-Panel-Einklapp-Mechanismus (Chevron-Button "Chat einklappen", Platzhalter-Leiste "Chat ausklappen") ist ein Relikt aus der Zeit vor der vollständigen Panel-Schließen-/Wiedereröffnen-Funktion; seit ein Panel komplett geschlossen und über die Header-Bar ("Ansicht hinzufügen") wieder geöffnet werden kann, ist Einklappen redundant. | **Erledigt 03.09.2026:** Einklapp-Mechanismus vollständig entfernt — `collapsedPanels`-State, `togglePanelCollapse`, `isPanelCollapsed` aus `useWorkspaceLayout.ts` gestrichen; `PanelRenderer.tsx` rendert Panel-Inhalte jetzt immer direkt (keine Platzhalter-Darstellung, kein Collapse-Button mehr, `collapsed`/`onExpand`/`onCollapse`-Props entfernt); `WorkspaceShell.tsx` wendet Panel-Breiten jetzt bedingungslos an (kein `flex-none w-12`-Sonderfall mehr); Übersetzungsschlüssel `collapseChat`/`expandChat` aus `de.json`/`en.json` entfernt. Neuer Test `PanelRenderer.test.tsx` sichert ab, dass kein Collapse-Button mehr existiert und `collapsed` als Prop nicht mehr akzeptiert wird. `tsc --noEmit`, ESLint, volle Vitest-Suite (46 Tests) und Produktions-Build grün. | Keine |
| O-040 | Frontend / Branding | Kein Browser-Tab-Favicon gesetzt — `app/layout.tsx` hatte kein `<link rel="icon">`, kein `app/icon.*`-Next.js-Konventionsfile vorhanden (nur `public/condo-c.svg`/`condo-schriftzug.svg`, Relikte des ursprünglichen Condo/BIM-Templates, aus dem Doctus hervorging). | **Erledigt 03.09.2026:** neues `app/icon.svg` — dieselben Pfade wie `components/Logo.tsx::DoctusIcon` ("strukturelles D"), Farben aus den Theme-CSS-Vars (`--ds-accent`/`--ds-background`/`--ds-on-accent`, Dark-Theme-Werte, da das App-Standard-Theme) als feste Hex-Werte übernommen — eine statische Favicon-Datei hat keinen Zugriff auf die CSS Custom Properties der Seite. Next.js erkennt die Datei automatisch über die `app/icon.*`-Konvention und setzt `<link rel="icon">` selbst; keine Änderung an `layout.tsx` nötig. Verifiziert: `next build` listet `/icon.svg` als eigene statische Route, `curl` gegen den ausgerollten Container liefert `200 image/svg+xml` und das gerenderte HTML enthält den `<link rel="icon" ...>`-Tag. **Folgefix noch am selben Tag:** trotz korrektem Server-Response blieb das Icon in Chrome unsichtbar (auch im Inkognito-Modus, schloss Browser-Caching aus) — Ursache war ungültiges XML im erklärenden SVG-Kommentar (doppelte Bindestriche wie `--ds-accent`, laut XML-Spezifikation innerhalb von Kommentaren verboten); Chrome parst ein direkt als Favicon geladenes SVG als striktes XML statt mit dem nachsichtigen HTML-Tokenizer und verwirft die ganze Datei bei einem solchen Fehler. Kommentar umformuliert (Gedankenstrich statt doppeltem Bindestrich); mit `xml.etree.ElementTree` gegen die ausgelieferte Datei verifiziert. | Keine |
| O-038 | Frontend / Chat-Sessions | Eine Chat-Session sollte nicht mehr nur mit der ersten Chat-Nachricht beginnen können, sondern auch, sobald eine zweite View geöffnet wird (z. B. Graph-View + Code-View), selbst wenn der Chat nie benutzt wurde. Vorher war ein Befund, der nur über mehrere Views ohne Chat-Nutzung entsteht, nicht teilbar oder konservierbar, weil ohne Chat-Nachricht keine Session existierte. | **Erledigt 03.09.2026:** neuer Endpunkt `POST /chat/sessions` (`ChatSessionCreate`-Schema: `title`, optional `project_id`/`source_id`/`snapshot`) legt eine Sitzung ohne Chat-Nachricht an — Gegenstück zur impliziten Erzeugung in `POST /chat`, die den Titel aus der ersten Nachricht ableitet. Frontend: neues Speicher-Icon in der Header-Bar (`GlobalSearch.tsx`), sichtbar nur wenn `chatMessages.length === 0 && panelConfigs.length >= 2`; Klick öffnet `SaveSessionDialog.tsx` (Namenseingabe, eigene schlanke Modal-Komponente statt Dialog-Library). Neuer Handler `useChatController.ts::handleSaveSessionWithoutChat` ruft den Endpunkt auf, reiht die neue Session vorne in die Sidebar-Liste ein und setzt `activeSessionId` — der bereits bestehende debounced Workspace-Snapshot-Autosave-Effekt (`useWorkspaceLayout.ts`, reagiert auf `activeSessionId`-Änderungen) übernimmt danach automatisch das Schreiben des Snapshots über den bestehenden `PATCH .../snapshot`-Pfad, ohne eine zweite Snapshot-Bau-Stelle zu brauchen. Neue Tests: 8 Backend-Fälle in `test_chat_sessions.py` (Erzeugung, leerer Titel → 400, unbekanntes Projekt/Quelle → 404, Sichtbarkeit, Auth-Pflicht), 3 Frontend-Fälle in `useChatController.test.tsx` sowie 3 in `GlobalSearch.test.tsx` (Sichtbarkeit des Icons, Dialog-Öffnen, getrimmter Titel wird übergeben). Backend-Suite 143/146 grün (die 3 Fehlschläge vorbestehend, siehe O-037), volle Vitest-Suite 52 Tests grün, `tsc --noEmit`, ESLint und Produktions-Build grün. **Folgefix noch am selben Tag** (Nutzer-Feedback nach erstem Test): zwei Konsistenzlücken behoben — (1) erneutes Klicken auf das Speicher-Icon bei bereits aktiver chat-loser Sitzung legte eine zweite Sitzung an, statt die bestehende zu aktualisieren; Button wechselt jetzt auf einen `onUpdateSessionSnapshot`-Pfad ohne Dialog, sobald `activeSessionId` schon gesetzt ist (Tooltip wechselt entsprechend auf „Sitzung aktualisieren"). (2) Der lokale Sidebar-Cache (`sessions`-State) wurde nach einem erfolgreichen `PATCH .../snapshot` nie mit dem tatsächlich gespeicherten `snapshot_json` synchronisiert — dieselbe Sitzung erneut anzuklicken stellte dadurch einen veralteten oder leeren Panel-Zustand wieder her (z. B. Graph-View verschwand, nur Chat blieb offen). `useWorkspaceLayout.ts`s debounced Autosave-Effekt sowie beide neuen Handler (`handleSaveSessionWithoutChat`, `handleUpdateSessionSnapshot`) schreiben den gespeicherten Snapshot jetzt zusätzlich in den lokalen Cache zurück; die Erstspeicherung wartet zudem nicht mehr auf den 1,2s-Debounce, sondern schreibt sofort. Neue Tests: 2 in `useWorkspaceLayout.test.ts` (Cache-Sync nach Debounce, kein Fehler ohne `setSessions`), 4 weitere in `useChatController.test.tsx`, 1 weiterer in `GlobalSearch.test.tsx` — volle Vitest-Suite jetzt 59 Tests grün, `tsc --noEmit`, ESLint und Produktions-Build grün. | Bestehender Chat-Session-/Sidebar-Mechanismus |
| O-030 | Backend / Ingestion | `POST /knowledge-sources/upload` (`backend/api/knowledge_sources.py`) hat keine serverseitige Extension-Allowlist — nur die UI begrenzt die Dateiauswahl auf `.pdf`/`.md`/`.txt`; ein direkter API-Call nimmt jede Datei entgegen und schickt sie in die Verarbeitungs-Pipeline. | **Erledigt 03.09.2026:** serverseitige Allowlist `_ALLOWED_UPLOAD_EXTENSIONS` (`.pdf`/`.md`/`.txt`, synchron zur UI-`accept`-Liste) prüft die Dateiendung vor dem Anlegen der Knowledge-Source und lehnt Abweichungen mit HTTP 400 ab. Neuer Testfall `test_upload_local_document_rejects_disallowed_extension`; bestehender Traversal-Test auf eine erlaubte Endung (`passwd.txt`) umgestellt, da er zuvor ohne Endung lief. | Keine |
| O-031 | Backend / Ingestion | Lokaler Upload-Pfad (`parser/tasks/document.py::process_local_document_async`) hat keinen OCR-Fallback für Bild-PDFs. Folder-/WebDAV-Connectoren teilen sich dafür bereits `connectors/folder.py::_extract_text` (inkl. OCR); `document.py` extrahiert PDF-Text separat und dupliziert die Logik ohne OCR. | **Erledigt 03.09.2026:** neue geteilte Funktion `connectors/folder.py::extract_pdf_pages` (seitenweise Extraktion inkl. OCR-Fallback bei fehlendem Text-Layer, Seitenzuordnung geht dabei auf `page_no=None` zurück). `_extract_text` (Folder-/WebDAV-Pfad) baut jetzt darauf auf; `document.py` ruft dieselbe Funktion statt eigener `pypdf`-Logik auf und erhält damit den OCR-Fallback für lokale Uploads. Neuer Test `test_pdf_extraction.py` (Seitenextraktion, OCR-Fallback bei fehlendem Text-Layer über `_extract_text` und `extract_pdf_pages`, sowie Integrationstest für `process_local_document_async` mit `page=None`-Metadaten). Volle Parser-Suite 179 von 180 grün, der eine Fehlschlag in `test_ap4_persistence.py` ist vorbestehend und auf unverändertem Code reproduzierbar. Parser-Worker neu gebaut und ausgerollt. | Keine |
| O-032 | Backend / Sicherheit | Chat-Share-Mechanik war schwächer geschützt als beabsichtigt: `GET /chat/sessions/by-uuid/{uuid}` und `.../messages` prüften `ChatSession.is_public` nicht und verlangten keine Authentifizierung — jede Session war über ihre UUID lesbar, auch wenn sie nie geteilt wurde. `PATCH /chat/sessions/{id}/snapshot` und `PATCH /chat/messages/{id}/feedback` waren zusätzlich über eine fortlaufende Integer-`session_id`/`message_id` statt UUID adressiert und (Snapshot komplett, Feedback ohne Owner-/Public-Prüfung) ohne echte Zugriffskontrolle erreichbar. | **Erledigt 03.09.2026 (`de2c9c1`):** neue Zugriffsregel `owner_id == user.id or is_public` (`_session_accessible` in `backend/api/chat.py`) jetzt einheitlich durchgesetzt auf den `by-uuid`-Leserouten, dem Snapshot-/Feedback-Update, dem `/chat`-Fortsetzen einer fremden `session_id` sowie zusätzlich auf `GET /chat/sessions/{id}/messages` (dieselbe Lücke — sequentielle ID, bislang komplett ohne Auth/Owner-Check, war im Audit nicht extra erfasst, aber derselbe Fall). Da nichts `is_public` je auf `True` setzte, war die Freigabe-Funktion faktisch nie benutzbar (siehe DOC-F-070); neuer Endpunkt `POST /chat/sessions/{id}/share` (Owner-only) setzt es jetzt explizit beim Klick auf „Chat teilen" (`useChatController.ts::handleShareChat`). 8 neue Testfälle in `backend/tests/test_chat_sessions.py` (15 gesamt grün), `tsc --noEmit` grün, Backend+Frontend neu gebaut und ausgerollt. | Keine |
| O-033 | Backend / Verschlüsselung | `ChatMessage.metadata_json` (u. a. `refs`) und `feedback` liegen unverschlüsselt in der DB; nur `content` ist als `EncryptedString` modelliert. | Fachlich klären, ob Metadaten/Refs schutzwürdige Auszüge enthalten können; falls ja, Verschlüsselung erweitern. | Fachliche Einschätzung nötig |
| O-034 | Backend / Knowledge Graph | Der Knowledge-Graph-Endpunkt (`backend/api/graph.py`) bietet nur `/export/neo4j` (Cypher); anders als der Callgraph (JSON/CSV/GraphML) gibt es keinen neutralen CSV-/GraphML-Export. | **Erledigt 03.09.2026:** neuer Endpunkt `GET /graph/export?format=csv\|graphml` (analog zu `/callgraph/export`) — ruft intern dieselbe `get_graph()` auf wie `GET /graph`, erbt damit dieselbe Sichtbarkeitsprüfung. CSV mit Spalten `source,target,link_type,score,context`; GraphML mit Knoten-Label/Typ und Kanten-`link_type`/`score`. Frontend (`LayoutSettingsTab.tsx`) bekommt zwei weitere Export-Buttons neben dem bestehenden Neo4j-Cypher-Export. Neue Backend-Tests `test_graph_export.py` (4 Fälle: CSV-Inhalt, GraphML-Inhalt, unbekanntes Format → 422, Sichtbarkeitsprüfung → 404). Volle Backend-Suite 135/138 grün (die 3 Fehlschläge in `test_chat_llm_provider_guard.py` sind vorbestehend, `ALLOW_CLOUD_LLM=true` in dieser lokalen Compose-Umgebung, siehe O-037). `tsc --noEmit`, ESLint, volle Vitest-Suite (46 Tests) und Produktions-Build grün. Legacy-Neo4j-Endpunkt bewusst nicht entfernt (weiterhin in Nutzung, keine Migrationsentscheidung getroffen). | Keine |
| O-035 | Backend / LLM-Konfiguration | `POST /model-info` (`backend/api/system.py`) verändert weiterhin `cfg.OLLAMA_LLM_MODEL` global im laufenden Prozess statt request-/profilgebunden zu bleiben. | Modellwahl request- bzw. profilgebunden umsetzen, falls Mehrmandantenbetrieb mit unterschiedlichen lokalen Modellen relevant wird. | Fachliche Priorität klären |
| O-036 | Frontend / Performance | Datei-/Entitätslisten in der Seitenleiste sind bei sehr großen Beständen nicht virtualisiert — die volle Liste wird gerendert, keine Virtualisierungsbibliothek im Frontend vorhanden. | **Erledigt 05.09.2026:** `@tanstack/react-virtual` (MIT) ergänzt. Die beiden potenziell unbeschränkt großen Listen der Seitenleiste sind jetzt gefenstert: Chat-Verlauf (neue Komponente `components/sidebar/VirtualizedSessionList.tsx`) und der Datei-Baum einer aufgeklappten Wissensquelle (`components/sidebar/FileTreeList.tsx`). Der rekursive Baum lässt sich nicht direkt fenstern — neue reine Hilfsfunktion `lib/sidebarFileTree.ts::flattenVisibleFileTree` flacht ihn vorher auf die aktuell sichtbaren Zeilen ab (Kinder eingeklappter Ordner fehlen dort), danach rendert der Virtualizer nur noch die paar Zeilen im sichtbaren Ausschnitt statt aller. Die gepinnten Quellen selbst bleiben unvirtualisiert (`.slice(0, 4)`-gedeckelt, kein Skalierungsproblem). `renderSourceTreeNode`/`buildFileTree` aus `Sidebar.tsx` entfernt (in die neuen Module verschoben), Sidebar.tsx dadurch schlanker. Neue Tests: `lib/sidebarFileTree.test.ts` (6 reine Fälle für Baumaufbau/Abflachung/Kollaps), `VirtualizedSessionList.test.tsx` und `FileTreeList.test.tsx` (je 5-6 Fälle inkl. Nachweis, dass bei 500 Sitzungen bzw. 2000 Dateien nur ein Bruchteil davon im DOM landet). Volle Vitest-Suite (80 Tests), `tsc --noEmit`, ESLint und Produktions-Build grün, Frontend-Container neu gebaut und ausgerollt. | Keine |
| O-037 | Backend / Ingestion | Bei O-030 entdeckt: `POST /knowledge-sources/upload` liefert bei Erfolg einen leeren Response-Body (`{}`) statt der neuen Knowledge-Source. Ursache: `send_tracked_task()` committet nach dem `return`-relevanten letzten Attributzugriff erneut (`record.celery_task_id = task_id; db.commit()`), SQLAlchemy expired danach alle Instanzattribute (`expire_on_commit=True`, Default), und der Endpunkt gibt das ORM-Objekt direkt zurück statt es zu serialisieren — `jsonable_encoder` sieht dadurch ein leeres `__dict__`. Das Frontend (`SourcesSetupTab.tsx::handleFileUpload`) hängt dieses leere Objekt direkt an die Quellenliste an. Zusätzlich rot in der CI (unabhängig davon): `PermissionError: [Errno 13] Permission denied: '/repos'` beim lokalen Datei-Upload-Test — der CI-Runner hat keinen Schreibzugriff auf `UPLOADS_DIR`. Beide Fehlschläge sind vorbestehend (reproduzierbar mit unverändertem `ff4c864`, nicht durch O-030 verursacht) und lassen `test_upload_local_document_creates_source_and_saves_file` sowie `test_upload_local_document_sanitizes_path_traversal_in_filename` weiterhin fehlschlagen. | **Erledigt 03.09.2026 (`d798e3d`):** `upload_local_document` gibt jetzt `serialize_source(db_source)` zurück statt des rohen ORM-Objekts — identisches Muster zu `create_knowledge_source`/`create_git_source`/`create_folder_watch_source`. CI-Workflow (`backend`-Job) legt `/repos/uploads` vor dem Testlauf an und übergibt es dem Runner-User, da dieser Job bare auf `ubuntu-latest` läuft (kein Docker-Compose-Mount für `/repos`). Beide Upload-Tests lokal im neu gebauten `backend-api`-Container grün (`131 passed`; die 3 unabhängig fehlschlagenden `test_chat_llm_provider_guard.py`-Fälle liegen an `ALLOW_CLOUD_LLM=true` in dieser lokalen Compose-Umgebung, nicht an dieser Änderung). Backend neu gebaut und ausgerollt. | Keine |

O-041 bis O-051 stammen aus einer Produktreife-/Vermarktungs-Analyse vom 05.09.2026
(„was fehlt, um Doctus als Produkt zu vermarkten, insbesondere Konnektoren"), gegen
den tatsächlichen Codestand geprüft (nicht nur gegen Doku).

| ID | Bereich | Punkt | Status / nächste Aktion | Abhängigkeit |
|---|---|---|---|---|
| O-041 | Sicherheit / Authentifizierung | Login war ein reines lokales Passwort-Verfahren (`backend/api/auth.py`, Argon2id) — im Backend existierte kein OIDC-/SAML-/LDAP-Code, obwohl `docs/deployment-customer.md` bereits eine Anleitung beschrieb, beim Kunden Issuer-URL/Client-ID/Client-Secret für einen OIDC-Login abzufragen. | **Erledigt 05.09.2026 (`103bf62`):** OpenID-Connect-Authorization-Code-Flow als zweiter Anmeldeweg neben dem lokalen (`backend/core/oidc.py`), aktiv sobald `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` gesetzt sind (`core/config.py::oidc_enabled()`). ID-Token-Prüfung (Signatur über JWKS, Issuer, Audience, Ablauf, Nonce, explizit `algorithms=["RS256"]` gegen Alg-Confusion) über `joserfc`. JIT-Provisioning ausschließlich über den `sub`-Claim, kein automatisches Verknüpfen über die E-Mail-Adresse (Design-Entscheidungen im Detail: `docs/ENTSCHEIDUNGEN.md` E-12). Migration `0007_user_oidc_subject`: `password_hash` nullable für SSO-Konten, neue Spalte `oidc_subject`. `POST /users/{id}/reset-password` lehnt SSO-Konten ab. `GET /config/features` liefert `auth.ssoEnabled`, `LoginView.tsx` zeigt darauf gestützt einen SSO-Button. Getestet ohne echten Kunden-IdP: `backend/tests/test_oidc.py` signiert eigene ID-Tokens mit einem generierten RSA-Schlüsselpaar und verifiziert sie über ein eigenes JWKS (20 Fälle), `test_auth.py`/`test_users_admin.py` decken die Router-Verdrahtung und die Reset-Password-Sperre ab, `LoginView.test.tsx` die Button-Sichtbarkeit und Fehleranzeige. Backend-Suite 164 grün (+12 vorbestehende, unabhängige Fehlschläge), Parser-Suite 179 grün (+1 vorbestehender Fehlschlag), Frontend 64 Tests grün, alle sieben Docker-Services neu gebaut und ausgerollt. `docs/deployment-customer.md` beschrieb den Kunden-Ablauf bereits korrekt — kein Doku-Nachzug nötig. | Keine |
| O-042 | Konnektoren | Kein Konnektor für mainframe-native Quellcode-Verwaltung (Endevor, ChangeMan, Micro Focus/PVCS, IBM RTC/CMVC) oder direkten Zugriff auf z/OS-PDS-Datasets. `parser/connectors/git.py` deckt nur Git-Bestände ab (providerneutraler Bare-Mirror-Clone, funktioniert daher zwar mit GitHub/GitLab/Azure Repos, nicht nur Bitbucket — aber eben nur mit Git). COBOL-Bestände, die noch nicht nach Git migriert sind, lassen sich damit gar nicht anbinden. **05.09.2026 verfeinert:** Am weitesten verbreitet sind laut allgemeinem Branchenwissen (keine für Doctus verifizierte Marktstudie) CA/Broadcom Endevor (Marktführer, v. a. Großkonzerne) und ChangeMan ZMF (OpenText, zweitgrößter Player, stark in Banken/Versicherungen); daneben verwalten ältere Umgebungen COBOL-Code teils direkt als z/OS-PDS-Member ohne kommerzielles SCM. **Vor jedem Codieren zu klären:** Setzt der Zielkunde (Endevor-Fall) zusätzlich "**Endevor Bridge for Git**" ein? Falls ja, synchronisiert Broadcom die Endevor-Elemente bereits automatisch in ein Git-Repo — dafür würde der **bestehende** `GitConnector` vermutlich ausreichen, kein neuer Konnektor nötig. Falls nein (klassischer Endevor-Zugriff über ISPF/Batch-SCL, kein Git-Bridge), bräuchte ein nativer Konnektor Zugriff auf Endevors REST-Schnittstelle ("Endevor Web Services") — technisch anschlussfähig über das bestehende Konnektor-Muster (`BaseConnector`, nur `fetch_documents()` zu implementieren, Parsing/Graph/Embedding bleiben unverändert), aber ohne echten Endevor-Testzugang nicht verifizierbar; der naheliegende Zowe-CLI-Weg scheidet ohnehin aus (EPL-2.0-lizenziert, verstößt gegen CLAUDE.md Prinzip 2). | Mit Vertrieb/Kunden zuerst klären, ob "Endevor Bridge for Git" im Einsatz ist (s. o.) — je nach Antwort ist entweder gar kein neuer Konnektor nötig, oder ein nativer Endevor-REST-Konnektor mit dediziertem Testzugang. Erst danach Konnektor-Architektur umsetzen. | Antwort von Vertrieb/Kunde zu Endevor Bridge for Git; bei nativer Anbindung zusätzlich ein Endevor-Testzugang für Verifikation |
| O-043 | Konnektoren / Fachlichkeit | Kein DB2-Katalog-/Schema-Import. Eingebettetes SQL in COBOL-Programmen bleibt dadurch teilweise unaufgelöst (laut Bestandsauswertung ca. 24 von 473 USES-Kanten „unresolved", vermutlich SQL-Restfälle). Ein Konnektor, der Tabellen-/Spaltenschema aus dem DB2-Katalog zieht, würde diese Kanten auflösbar machen und wäre ein fachliches Alleinstellungsmerkmal gegenüber generischen Code-Assistenten. | Scope klären (nur Schema-Metadaten vs. auch Laufzeitdaten), dann Konnektor + Erweiterung des Edge-Resolvers umsetzen. | Fachliche Priorisierung nötig |
| O-044 | Backend / Ingestion | Direkter Datei-Upload (`POST /knowledge-sources/upload`, `_ALLOWED_UPLOAD_EXTENSIONS` in `backend/api/knowledge_sources.py`) erlaubt serverseitig nur `.pdf/.md/.txt`, während Ordner-Watch- und WebDAV-Connector (`SUPPORTED_EXTENSIONS` in `parser/connectors/folder.py`/`webdav.py`) zusätzlich `.docx/.doc` extrahieren können. Inkonsistentes Verhalten je nach Zugangsweg zur selben Datenquelle. | **Erledigt 05.09.2026:** `_ALLOWED_UPLOAD_EXTENSIONS` um `.docx`/`.doc` erweitert (deckungsgleich mit `parser/connectors/folder.py::SUPPORTED_EXTENSIONS`); UI-`accept`-Liste (`SourcesSetupTab.tsx`) und `dropzoneHint`-Übersetzung (`de.json`/`en.json`) mitgezogen. Zusätzlich Duplikat wie bei O-031 beseitigt: neue geteilte Funktion `connectors/folder.py::extract_docx_text` (Absätze + Tabellenzellen), `_extract_text` (Folder-/WebDAV-Pfad) und `tasks/document.py::process_local_document_async` (lokaler Upload) rufen jetzt dieselbe Funktion statt zweier unabhängiger python-docx-Schleifen. Neue Tests: `test_docx_extraction.py` (6 Unit-/Integrationsfälle, Muster analog zu `test_pdf_extraction.py`/O-031), 1 neuer Backend-Fall `test_upload_local_document_accepts_docx`. Backend-Suite 174/177 grün (3 vorbestehende Fehlschläge in `test_chat_llm_provider_guard.py`, siehe O-037), Parser-Suite 201/213 grün (12 vorbestehende, umgebungsbedingte `[trio]`-Fehlschläge, mit unverändertem `09a1f39` reproduziert). `tsc --noEmit`, ESLint, volle Vitest-Suite (64 Tests) und Produktions-Build grün. | Keine |
| O-045 | Konnektoren | Kein SharePoint-/OneDrive-Konnektor. In vielen Unternehmen liegt Fachdokumentation dort statt in Confluence. | Bedarf beim Zielkunden klären, dann Konnektor analog Confluence/WebDAV umsetzen (Microsoft Graph API). | Fachliche Priorisierung nötig |
| O-046 | Konnektoren | Kein generischer S3-kompatibler Objektspeicher-Konnektor (AWS S3/MinIO). | Bedarf klären — relevant, falls Kunden Doku/Exports bereits in einem S3-Bucket statt Dateisystem/WebDAV halten. | Fachliche Priorisierung nötig |
| O-047 | Konnektoren | Kein Postfach-/E-Mail-Konnektor (IMAP/Exchange) für Fachkorrespondenz oder Anforderungsmails als Wissensquelle. | Bedarf klären, sonst nicht priorisieren. | Fachliche Priorisierung nötig |
| O-048 | Konnektoren | Außer Jira ist kein weiteres ITSM-/Ticket-System angebunden (z. B. ServiceNow, Azure DevOps Boards). | Bedarf beim Zielkunden klären. | Fachliche Priorisierung nötig |
| O-049 | Konnektoren / Chat | Keine Slack-/Teams-Integration für den Chat-Assistenten — Nutzung ist auf die Doctus-Weboberfläche beschränkt. | Bedarf klären (Assistent im Arbeitsalltag vs. reines Recherchewerkzeug), dann Bot-Integration umsetzen. | Fachliche Priorisierung nötig |
| O-050 | Vertrieb / Compliance | Keine Enterprise-Vertrauensnachweise vorhanden: kein Pentest-Bericht, kein Security-Whitepaper, keine ISO-27001-/BSI-Grundschutz-Aussage. Bei Konzern-/Behörden-Beschaffung häufig hartes Ausschlusskriterium in der Ausschreibung, unabhängig vom tatsächlichen Codezustand. | Mit Vertrieb klären, welche Nachweise für die anvisierten Ausschreibungen nötig sind; ggf. externen Pentest beauftragen und Whitepaper verfassen. | Auftraggeber-/Vertriebsentscheidung |
| O-051 | Betrieb / Paketierung | Installation ist „git clone + `.env` von Hand editieren" (siehe `docs/deployment-customer.md`) — kein Installer/Onboarding-Wizard, keine Trial-Version, kein dokumentiertes Update-/Migrationsverfahren zwischen Versionen für laufende Kundeninstallationen, kein Lizenz-/Preismodell. Skaliert aktuell nicht über eine Vor-Ort-Installation durch eine technisch versierte Person hinaus. | Priorisieren, sobald mehr als vereinzelte Pilotkunden geplant sind: Installer-Skript/Wizard, Upgrade-Pfad (Migrationen + Doku), Lizenzmodell festlegen. | Geschäftsentscheidung, wann Skalierung über Einzelinstallationen hinaus ansteht |
| O-052 | Frontend / CI | Bei O-044 entdeckt: `npx tsc --noEmit` schlug auf unverändertem `develop` (`09a1f39`) bereits fehl — `frontend/components/LoginView.test.tsx` reassignt `window.location` per `delete window.location; window.location = ...`, was mit dem aktuellen TypeScript/lib.dom-Typenstand nicht mehr durchgeht (`window.location` ist dort nur noch ein get-only Accessor ohne Setter). Der CI-Schritt „Type-check" auf `develop` war dadurch vermutlich bereits rot. | **Erledigt 05.09.2026:** beide Stellen auf `Object.defineProperty(window, 'location', { configurable: true, value: ... })` umgestellt statt delete+Reassignment; keine `@ts-expect-error`-Direktiven mehr nötig. `tsc --noEmit` und die 5 betroffenen Vitest-Fälle grün, volle Vitest-Suite (64 Tests) weiterhin grün. | Keine |
| O-053 | Backend+Frontend / Knowledge Graph | `GET /graph` (Knowledge-Graph-Übersicht, `backend/api/graph.py`) lud jede sichtbare Code-Entity und jeden Dokument-Chunk unbegrenzt — bei einem großen COBOL-Bestand (Ziel-Skalierung laut CLAUDE.md Prinzip 4) sowohl ein Server- (Antwortgröße/Ladezeit) als auch ein Client-Risiko (d3-force-Kraftsimulation im Browser-Hauptthread, am Ende nur ein unlesbarer "Wollknäuel"). Anders als der Call Graph (`/callgraph/focus`, immer auf eine begrenzte Ein-Hop-Nachbarschaft beschränkt) hatte die Knowledge-Graph-Übersicht kein Sicherheitsnetz. Zusätzlicher Fund dabei: der Endpunkt `GET /graph/focus` — strukturell exakt dasselbe Ein-Hop-Nachbarschaftsmuster wie beim Call Graph, offenbar genau für dieses Problem gebaut — wurde von keiner Stelle im Frontend aufgerufen (totes Code-Fragment). | **Erledigt 05.09.2026:** neuer Deckel `KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES` (Default 2000, env-konfigurierbar, `core/config.py`) in `get_graph()` — analog zu callgraph.py's `MAX_NODES` (F-066), aber mit höherem Wert, da die Übersicht bewusst auch unverlinkte Entities zeigt (Inventarcharakter). Beim Kappen bleiben die am dichtesten verlinkten Knoten zuerst erhalten (Degree-Sortierung), Kanten mit einem weggefallenen Endpunkt werden mitentfernt; Antwort trägt neu `truncated`/`total_nodes`/`total_edges`. `GET /graph/focus` jetzt tatsächlich ans Frontend angebunden: neuer Button „Nur Nachbarschaft laden" (`KnowledgeGraphView.tsx`) lädt bei einem Entity-Knoten dessen echte, ungekappte Nachbarschaft direkt aus der DB (anders als der bestehende, rein visuelle Soft-Focus, der nur das bereits geladene — ggf. gekappte — Übersichtsmaterial abdunkelt); Kapp-Hinweis-Banner in der Übersicht, „Zurück zur Übersicht"-Chip im Nachbarschafts-Modus. Bekannte Grenze: „Nur Nachbarschaft laden" braucht einen Projekt-Kontext (`/graph/focus` verlangt `project_id`), im „Allgemein"-Kontext für projektlose Entities daher nicht verfügbar. Nebenbei bei den neuen Frontend-Tests entdeckt und behoben (O-054, siehe dort). Neue Tests: 3 Backend-Fälle (`test_graph_overview_truncation.py`: unterhalb des Deckels unverändert, Kappen mit korrekten Gesamtzahlen, keine hängenden Kanten nach dem Kappen), 4 Frontend-Fälle (`KnowledgeGraphView.test.tsx`: Kapp-Banner erscheint/bleibt aus, `/graph/focus`-Aufruf mit korrekten Parametern, Rücksprung zur Übersicht). Backend-Suite 177/180 grün (3 vorbestehende Fehlschläge, siehe O-037), `tsc --noEmit`, ESLint, volle Vitest-Suite (84 Tests) und Produktions-Build grün. Backend+Frontend neu gebaut und ausgerollt. | Keine |
| O-054 | Frontend / Codequalität | Bei den O-053-Tests entdeckt: `KnowledgeGraphView`s Default-Parameter `projectEntities = []` erzeugt bei jedem Aufruf ohne diese Prop eine neue Array-Referenz — die Render-Zeit-State-Anpassung weiter unten (`prevFocusDeps.projectEntities !== projectEntities`, Zeile ~396) vergleicht genau darauf und wurde dadurch bei jedem einzelnen Render erneut ausgelöst: eine waschechte Endlosschleife. Bislang folgenlos, weil beide tatsächlichen Aufrufer (`app/page.tsx`, `PanelContentRenderer.tsx`) die Prop immer explizit mitgeben — ein künftiger Aufrufer ohne diese Prop hätte die Ansicht aber sofort eingefroren. | **Erledigt 05.09.2026:** modulweite stabile Konstante `EMPTY_PROJECT_ENTITIES` statt eines Inline-`[]`-Literals als Default. | Keine |

O-055 bis O-062 stammen aus einem Testabdeckungs-Audit vom 05.09.2026: Backend
(163 Testfälle/23 Dateien) und Parser (180/31) sind gut abgedeckt, insbesondere
der COBOL-Golden-Corpus (F-033) und sicherheitsrelevante Backend-Pfade. Beim
Frontend (84 Testfälle/18 Dateien) zeigt eine Stichprobe eine klare Lücke: die
größten, interaktionsreichsten Komponenten haben keinen einzigen Test —
`KnowledgeGraphView.tsx` bekam mit O-053 heute den ersten überhaupt (und
dabei sofort einen echten Endlosschleifen-Bug zutage gefördert, O-054). Kein
Nachlässigkeits-Problem — Tests werden seit 03.09.2026 bei jeder Änderung
mitgeschrieben, aber unberührter Bestandscode bleibt dadurch strukturell
ungetestet, solange ihn niemand aus anderem Anlass anfasst. Diese Punkte
bauen die Lücke gezielt, in Häppchen pro Komponente ab, statt auf den
nächsten zufälligen Berührungspunkt zu warten. Reihenfolge nach Produkt-
Kritikalität und Komplexität, nicht nach ID.

| ID | Bereich | Punkt | Status / nächste Aktion | Abhängigkeit |
|---|---|---|---|---|
| O-055 | Frontend / Tests | `ChatView.tsx` — die eigentliche Chat-Oberfläche, das Kernprodukt — hat keinen einzigen Test. | Component-Tests ergänzen: Nachrichten rendern (inkl. Markdown/Code-Blöcke), Senden (gemockte API), Streaming-Anzeige, Retry/Regenerate-Buttons, leerer Zustand, Fehlerzustand, Quellen-/Refs-Anzeige. | Keine |
| O-056 | Frontend / Tests | `Sidebar.tsx` hat nach dem O-036-Umbau nur für die neuen Unterkomponenten (`VirtualizedSessionList`, `FileTreeList`, `sidebarFileTree`) Tests — die eigene Orchestrierung (Ordner-Akkordeon `expandedFolderId`, gepinnte-Quellen-Filterung nach Projektkontext, Sidebar-Resize, Mobile-Schließen-bei-Auswahl) ist ungetestet. | Component-Tests für die in `Sidebar.tsx` verbliebene Logik ergänzen. | Keine |
| O-057 | Frontend / Tests | `WorkspaceShell.tsx` (Split-/3-col-/4-grid-Rendering, Panel-Breiten-Anwendung, Teiler-Sichtbarkeit je Layoutmodus) hat keinen Test — nur die zugrunde liegende Resize-Arithmetik (`workspaceResize.ts`, `useWorkspaceLayout`) ist getestet, nicht die Komponente selbst. | Component-Tests: korrektes Layout je `layoutMode`, Teiler nur wo vorgesehen, Panel-Breiten aus Snapshot übernommen. | Keine |
| O-058 | Frontend / Tests | `CallGraphView.tsx` hat keinen Test — Fokus-Laden (`/callgraph/focus`), Hops-Auswahl, Export-Buttons (JSON/CSV/GraphML), Truncated-Banner sind ungetestet. | Component-Tests analog zum heutigen `KnowledgeGraphView.test.tsx`-Muster (API gemockt, Interaktionen über gerenderte Buttons). | Keine |
| O-059 | Frontend / Tests | `JobCenter.tsx` hat keinen Test — Job-Liste, Retry/Stop/Entfernen-Aktionen, Admin-only-Gating sind ungetestet. | Component-Tests für die Kernaktionen und die Sichtbarkeitsregeln je Rolle. | Keine |
| O-060 | Frontend / Tests | `LinkManagerView.tsx` hat keinen Test — manuelles Verknüpfen/Bewerten von Quellen (DOC-F-081) ist ungetestet. | Component-Tests für Filterleiste, manuellen Picker und Linkkarten-Interaktionen. | Keine |
| O-061 | Frontend / Tests | `PanelContentRenderer.tsx`/`SplitPaneWorkspace.tsx` (Routing, welcher Panel-Typ für Chat/Code/Dokument/Graph/Web/Callgraph/Link-Manager gerendert wird) hat keinen Test. | Component-Tests für die Zuordnung Panel-Konfiguration → gerenderter Inhalt. | Keine |
| O-062 | Frontend / E2E | Nur 2 Playwright-Specs existieren (`login.spec.ts`, `accessibility.spec.ts`) — kein einziger End-to-End-Test für den eigentlichen Kernworkflow (Quelle anbinden → COBOL wird geparst → Chat-Frage stellen → Quellenverweis anklicken → Code-Ansicht öffnet an der richtigen Zeile). | Ersten goldenen-Pfad-E2E-Test gegen den laufenden Compose-Stack schreiben; deckt damit erstmals das Zusammenspiel aller Schichten (Parser, Backend, Frontend) in einem Testlauf ab, nicht nur isolierte Einheiten. | Keine |

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
- [FAQ Konnektor-Modularität](FAQ_KONNEKTOR_MODULARITAET.md) — Frage-Antwort-Referenz zu O-042 für Vertriebs-/Kundengespräche

## Pflege

Beim Bearbeiten eines Punktes den Status, die nächste Aktion und das Datum direkt
in dieser Tabelle aktualisieren. Erledigte Punkte nicht löschen, sondern in den
Abschnitt „Erledigt“ verschieben und auf Commit, Testlauf oder Abnahme verweisen.
