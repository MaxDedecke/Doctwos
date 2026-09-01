# Tech-Debt-Cleanup-Plan (Stand 2026-07-05)

> **Status (2026-07-05):**
> - §3 (Sidebar-Dateibaum): **erledigt** (Commit `d7d2d54`).
> - §1a (Backend/Parser: `parser/languages/`, `CodeParser`, `CodeReference`-Modell
>   + Alembic-Drop, COBOL-Auflösung in `graph.py`/`projects.py`, Link-Builder
>   Pass 3, COBOL-Fixtures, `tree-sitter` aus `requirements.txt`): **erledigt**.
>   Verifiziert: `parser`- und `backend`-Images neu gebaut, Parser-Testsuite
>   (7/7) und Backend-Testsuite (42/43, der eine Fehlschlag ist eine
>   vorbestehende, unabhängige LLM-Provider-Gating-Test-Flake) grün, Migration
>   gegen die laufende DB angewendet (`code_references`-Tabelle weg,
>   `code_entities` mit IFC-Daten unverändert), `/projects/{id}/entities`,
>   `/graph/focus`, `/projects/{id}/references` live gegen das GFZ-Demoprojekt
>   durchgetestet.
> - §1b (Frontend/Monaco: Datei-Gating, `detectLanguage()`, COBOL-Tokenizer,
>   Entity-Decorations/Click-to-select in `SplitPaneWorkspace.tsx`): **offen**
>   (Stand 2026-07-09 weiterhin unverändert — `detectLanguage()` in
>   `SplitPaneWorkspace.tsx` hat noch alle ~13 Sprachzuordnungen inkl. COBOL).
> - §2 (MCP-Restore): **erledigt** (Commit `ebb7396`, 2026-07-05). Schritte
>   1–6 umgesetzt: `mcp-atlassian` in `backend/requirements.txt`, Node.js/npm
>   im `backend/Dockerfile` (nur für Notion), `@notionhq/notion-mcp-server`
>   beim Image-Build global vorinstalliert (kein Registry-Fetch zur
>   Laufzeit), Fehler-Logging auf `logger.error(...)` umgestellt,
>   `backend/tests/test_mcp_client.py` ergänzt. Schritt 7 (Feature-Flag-
>   Sichtbarkeit) wurde für dieses Deployment mit "UI wieder freischalten"
>   entschieden — `config/features.json` hat `connectors.confluence/jira/
>   notion` inzwischen auf `true`.
>
> - §5 (Frontend-God-Components `page.tsx`/`SettingsModal.tsx` entflechten):
>   **in Arbeit** (2026-07-16). **Schritt 1 (SettingsContext) erledigt** — die
>   ~36 Einzel-Props von `SettingsModal` laufen jetzt über `components/settings/
>   SettingsContext.tsx` statt durch `page.tsx` gedrillt; die Aufrufstelle in
>   `page.tsx` ist von 47 Props auf `<SettingsProvider value={…}><SettingsModal
>   isOpen onClose /></SettingsProvider>` geschrumpft, `SettingsModalProps` auf
>   `isOpen`/`onClose`. **Schritt 2 ERLEDIGT:** alle 10 Tabs (`editor`, `layout`,
>   `ai`, `project-setup`, `logs`, `teams`, `git-setup`, `sources-setup`, `sources`,
>   `projects`) nach `components/settings/tabs/` herausgelöst; `SettingsModal.tsx`
>   ~4707 -> ~237 Zeilen (reiner Shell: Tab-Nav + 2 verbliebene Effekte +
>   Navigations-Callbacks). tsc + vitest grün. **Vorstufe zu Schritt 3
>   erledigt (2026-07-17):** in `page.tsx` verwaiste Reste aus der
>   Vor-Settings-Split-Ära entfernt (per Grep verifiziert: keine Aufrufstelle
>   mehr) — `handleFileUpload`+`parsePublicGitUrl`+die 3 zugehörigen
>   Upload-States (lebende Entsprechungen inzwischen in `SourcesSetupTab.tsx`/
>   `GitSetupTab.tsx`), `handleEditorNavigate`+`handleEditorEntitySelect`
>   (vollständig verwaist, keine lebende Entsprechung), `handleDeleteProject`+
>   `handleDeleteSource`+`getMockDocs` (lebende Entsprechungen in
>   `ProjectsTab.tsx`/`SourcesTab.tsx`), toter `sourcesWizardStep`-State, toter
>   `MarkdownContent`-Import. `page.tsx` 2720 -> 2508 Zeilen. tsc + vitest grün,
>   Login-Screen per Playwright gegen `next dev` gegengeprüft (rendert
>   fehlerfrei; ein authentifizierter Klick-Test war nicht möglich, da Login
>   ausschließlich per OIDC/SSO läuft und keine Testzugangsdaten vorliegen).
>   Offen: Schritt 3 selbst (page.tsx-Domänen-Hooks: `useProjects`,
>   `useChatSessions`, `useKnowledgeSources`, `useWorkspaceLayout` — Cluster/
>   Kopplungsanalyse für diese vier liegt bereits vor, siehe Session vom
>   2026-07-17), Schritt 4 (useCallback/memo) **offen**. Die XSS-/401-Befunde
>   desselben Reviews sind separat gefixt (Commit `41779bc`).
>
> Dieses Dokument ist bewusst so
> geschrieben, dass eine andere/spätere Session ohne Rückfragen direkt mit
> der Umsetzung anfangen kann — jeder Abschnitt enthält Entscheidung/
> Begründung, konkrete Datei:Zeile-Referenzen (Stand des Commits, auf den
> sich dieser Plan bezieht: `3dbb0ac`) und Verifikationsschritte. Zeilennummern
> können sich verschieben, wenn zwischenzeitlich andere Änderungen an
> denselben Dateien gemacht wurden — vor dem Edit kurz gegenchecken.
>
> Empfohlene Reihenfolge: **3 → 1 → 2** (aufsteigendes Risiko/Ambiguität;
> 2 hängt von einer externen Paket-Entscheidung ab, die erst noch verifiziert
> werden sollte, siehe dort).

---

## 1. AST-Code-Parsing entfernen + Monaco auf Markdown/Text beschränken

### Entscheidung (an mich delegiert, hiermit getroffen: **ja, entfernen**)

Begründung:
- `PARSER_REGISTRY` (`parser/languages/__init__.py:8`) ist und war immer leer —
  jede Sprache fällt auf `GenericParser` zurück, der wiederum nur für
  Python/JS/TS per **Regex** (nicht AST) `function`/`class`-Zeilen erkennt
  und für jede andere Sprache sofort `[]` zurückgibt. `tree-sitter`/
  `tree-sitter-languages` sind in `parser/requirements.txt` geladen, aber
  `GenericParser.__init__` speichert `self.language`/`self.parser` nur, ohne
  sie je zu verwenden — vollständig totes Gewicht, keine einzige Zeile nutzt
  tatsächlich tree-sitter.
- `extract_references()` liefert **immer** `[]`, für jede Sprache — die
  gesamte CALL/COPY/PERFORM-Referenzerkennung (COBOL) ist seit Einführung
  nie produktiv gelaufen. `CodeReference` wird nirgends befüllt aus echtem
  Code; die einzigen konsumierenden Codepfade (`link_builder.py` Pass 3,
  `graph.py`s COBOL-Auflösung) laufen bei jedem echten Repo ins Leere. Der
  Case-Mismatch zwischen `link_builder.py` (`"CALL","COPY"` groß) und
  `graph.py`/`projects.py` (`"call","copy","use","perform","goto"` klein)
  zeigt zusätzlich: dieser Pfad wurde nie end-to-end mit echten Daten
  getestet, sonst wäre das aufgefallen.
- **Aktuell (dieses Deployment, `config/features.json`) sind Git-Connectoren
  (`git.github/gitlab/bitbucket/public`) UND Confluence/Jira/Notion allesamt
  auf `false`** — der einzige Weg, wie heute überhaupt Python/JS/TS-Dateien
  in eine `KnowledgeSource` gelangen könnten (Git-Repo-Anbindung), ist im
  UI komplett ausgeblendet. Es gibt aktuell keinen einzigen aktiven
  Nutzerpfad, der `GenericParser`s Python/JS/TS-Zweig überhaupt erreicht.
- Die Projekt- und Betriebsdokumentation beschreibt diesen Pfad als Altlast
  aus einer früheren, nicht-AEC-Produktrichtung, nicht als aktives Feature.
- Null Testabdeckung: kein Test importiert `code_parser.py`,
  `languages/__init__.py`, `languages/base.py` oder `languages/generic.py`.
  Zwei COBOL-Fixture-Dateien (`parser/tests/fixtures/sample.cbl`,
  `dialects.cbl`) sind komplett verwaist, kein Test referenziert sie.

**Monaco-Konsequenz:** Der Editor bleibt als Viewer/Editor für
Markdown/Text bestehen (weiterhin nützlich — Protokolle, Notizen,
Konfigurationsdateien als Text). Aber: die generische "jede Datei fällt auf
Code-Sprache zurück"-Logik (aktuell ~15 Sprachen inkl. COBOL-Tokenizer)
wird auf Markdown/Plaintext reduziert. Andere, bisher nicht erkannte
Dateitypen (die weder BIM/CAD noch PDF/DOC/Bild sind) zeigen künftig einen
"keine Vorschau verfügbar"-Platzhalter statt im Code-Editor zu öffnen.

### 1a. Backend/Parser — zu entfernen

| Was | Ort | Aktion |
|---|---|---|
| `PARSER_REGISTRY`, `get_language_parser` | `parser/languages/__init__.py` | Ganze Datei löschen |
| `GenericParser` | `parser/languages/generic.py` | Ganze Datei löschen |
| `BaseLanguageParser` | `parser/languages/base.py` | Ganze Datei löschen — aber: `chunk_file()` (Zeilen 22-89) ist die generische zeilenbasierte Chunking-Logik, die **jede** Datei unabhängig von Sprache in `DocumentChunk`s zerlegt (nicht AST-spezifisch!). Diese Methode muss **erhalten bleiben**, nur an einen neuen, einfacheren Ort verschoben werden (z.B. direkt in `code_parser.py` oder `connectors/base.py`), sonst bricht das generische Text-Chunking für FolderWatch-Dateien. |
| `CodeParser` | `parser/code_parser.py` | Vereinfachen: kein Dispatch an Sprach-Parser mehr nötig — durch die (verschobene) `chunk_file()`-Logik ersetzen, `extract_entities`/`extract_references` als Konzept komplett entfernen (keine Aufrufer mehr, siehe unten). |
| `tree-sitter`, `tree-sitter-languages` | `parser/requirements.txt` | Zeilen entfernen |
| Aufrufer von `CodeParser(...).extract_entities()`/`extract_references()` | `parser/tasks/repository.py` (Zeilen ~102-128, 206-208 laut Recherche) | Die `CodeEntity`/`CodeReference`-Bulk-Insert-Logik für **Git-Repo-Dateien** entfernen. **Wichtig:** `CodeEntity` selbst (die Tabelle) bleibt — sie wird weiterhin von `parser/connectors/ifc.py` für BIM-Elemente benutzt (`type=ifc_wall` etc.) und vom Link Manager/Graph generisch konsumiert. Nur die Befüllung aus Git-Repo-Quellen (Funktionen/Klassen) fällt weg. |
| `CodeReference`-Modell | `backend/models/database.py` (Zeile ~197) + `parser/models/database.py` (gespiegelte Kopie) | Modell + Tabelle per Alembic-Migration entfernen (kein Consumer mehr übrig, siehe nächste Zeile) |
| COBOL-Auflösung in `graph.py` | `backend/api/graph.py` (`_containing_entity`, `_resolve_reference_target`, `.type.in_(("paragraph","section"))`, `.type.like("variable%")`, `CodeReference`-Queries in `/graph/focus`, Zeilen laut Recherche ~99-111, 225-277, 308-348) | Entfernen. Die generische, IFC/Link-Manager-taugliche Graph-Logik (Knotenaufbau via `EntityDocLink`) bleibt unberührt. |
| COBOL-Referenzauflösung in `projects.py` | `backend/api/projects.py` (`_structured_refs_to`, `CodeReference`-Query in `_refs_for_file`, Zeilen ~281-283, 698-711, 745-748) | Entfernen. Der **generische Text-Grep-Fallback** in `_refs_for_file` (Zeilen ~758-783, sucht `import`/`from`/`require`/`COPY`-Patterns in `DocumentChunk.content`) bleibt — der ist unabhängig von `CodeEntity`/`CodeReference` und liefert im Referenzen-Dropdown ohnehin schon die meisten echten Treffer. |
| Pass 3 (`_pass_syntactic`) | `parser/tasks/link_builder.py` (Zeilen ~132-148, CALL/COPY-Suche) | Entfernen. 3-Pass-Scan wird 2-Pass (semantic + keyword). Docstring am Dateikopf entsprechend anpassen. |
| COBOL-Fixtures | `parser/tests/fixtures/sample.cbl`, `dialects.cbl` | Löschen (unreferenziert) |
| `GET /projects/{id}/entities`, `.../references` | `backend/api/projects.py` | **Bleiben** — funktionieren weiterhin generisch für IFC-Entities, nur der COBOL-spezifische Ast wird entfernt (siehe oben). Prüfen, ob nach der Bereinigung noch unbenutzte Imports übrig bleiben. |

**Migration:** neue Alembic-Revision zum Droppen von `code_references` (nach
den bestehenden Migrationen, `down_revision` auf den aktuellen Head setzen —
`alembic heads` vorher prüfen, da in dieser Session mehrfach neue Revisionen
dazukamen).

**Nicht anfassen:** `CodeEntity`-Tabelle, `parser/connectors/ifc.py`,
`EntityDocLink`, Link-Manager-Endpunkte, `backend/api/entity_links.py`,
`backend/api/knowledge_links.py` — alles IFC/BIM-generisch und aktiv genutzt.

### 1b. Frontend/Monaco — zu entfernen/einschränken

Datei: `frontend/components/SplitPaneWorkspace.tsx` (Referenzstand: 1249
Zeilen), gesteuert von `frontend/app/page.tsx`.

1. **Dateityp-Gating verschärfen** (`page.tsx:78-92`, `getSelectionViewType`):
   Aktuell `return 'code'` als Fallback für buchstäblich jede nicht
   BIM/PDF/DOC/Bild-Datei. Neue Logik: nur `.md`/`.markdown`/`.txt` →
   `'code'`; alles andere (was nicht BIM/DOC/Bild ist) → neuer View-Typ
   `'unsupported'` mit einem einfachen "Keine Vorschau verfügbar"-Panel
   (analog zum bestehenden `svgError`-Zustand in `BimCadViewer.tsx` als
   Vorbild für die Optik).
2. **`detectLanguage()` reduzieren** (`SplitPaneWorkspace.tsx:35-63`): nur
   noch `.md`/`.markdown` → `'markdown'`, `.txt` → `'plaintext'`. Alle
   anderen ~13 Sprachzuordnungen (py/js/ts/json/html/css/sh/yaml/java/c/
   cpp/cs, `.cob/.cbl/.cpy` → `'cobol'`) entfernen.
3. **COBOL-Monarch-Tokenizer + Spalten-Lineal entfernen**
   (`SplitPaneWorkspace.tsx:406-492` Sprachregistrierung, `1120-1207`
   Lineal-UI) — nach Punkt 2 unerreichbar (keine `.cbl`-Datei öffnet den
   Editor mehr), toter Code.
4. **Entity-Decorations entfernen** (`SplitPaneWorkspace.tsx:345-404`,
   Decorations basierend auf `projectEntities`/`ent.name`-Stringsuche pro
   Zeile) — nach 1a gibt es für Git-Repo-Dateien keine `function`/`class`-
   Entities mehr, die Decoration-Logik liefe nur noch für IFC-Entities ins
   Leere (die aber ohnehin nie in Monaco geöffnet werden, s.u.). Toter Code.
5. **Click-to-select-Entity entfernen** (`onMouseDown`-Handler,
   `SplitPaneWorkspace.tsx:538-584`) — selbe Begründung wie 4.
6. **"Referenzen"-Dropdown** (`SplitPaneWorkspace.tsx:688-946`): **nicht**
   komplett entfernen — der `entity_name`-Zweig (abhängig von
   `CodeEntity`/`CodeReference`, ohnehin schon praktisch immer leer) fällt
   mit 1a automatisch weg, sobald `_structured_refs_to` im Backend entfernt
   ist (liefert dann `[]`, UI zeigt einfach keine Treffer in diesem Zweig —
   kein Frontend-Codeänderung zwingend nötig, aber der jetzt komplett tote
   `entity_name`-Ast könnte zur Klarheit mit entfernt werden). Der
   **Text-Grep-Fallback-Zweig** (unabhängig, nutzt nur `DocumentChunk`) und
   der **`realTimeDocs`-Tab** (pgvector-Suche) bleiben vollständig
   unverändert — funktionieren unabhängig von alldem.
7. **Line-Jump/Highlight** (`SplitPaneWorkspace.tsx:246-279`) — **bleibt
   unverändert**, generische Monaco-Navigation, unabhängig von Entities.
8. **Gutter-Click "Ask Doctus AI"** — **bleibt unverändert**, unabhängig.

**Bestätigt unabhängig, nicht anfassen:** `.ifc`/`.dwg`/`.dxf` öffnen
bereits heute nie in Monaco (eigene Regex-Route zu `BimCadViewer.tsx`,
`page.tsx:78-92`), daher keine Überschneidung mit dieser Änderung.

### Verifikation

- Backend/Parser: `docker compose build backend-api parser-worker`, Tests
  laufen lassen (`pytest tests/` in beiden Containern). Bestehenden Sync
  eines Git-verbundenen Testprojekts (falls eins existiert) gegenprüfen,
  dass Repo-Sync weiterhin funktioniert (Dateien werden weiterhin gechunkt,
  nur ohne `CodeEntity`-Erzeugung).
- Frontend: `npx tsc --noEmit`, dann im Browser: eine `.md`-Datei öffnen
  (muss funktionieren), eine z.B. `.py`- oder unbekannte Datei öffnen (muss
  "keine Vorschau"-Panel zeigen statt Editor), IFC/DWG-Dateien weiterhin im
  BimCadViewer prüfen (darf nicht betroffen sein).
- `GET /projects/{id}/entities` weiterhin gegen das Demoprojekt (IFC-
  Entities) aufrufen — muss unverändert funktionieren.

### Offene Frage für die Zukunft

Historische Hinweise auf "echte AST-Erkennung" als Zukunftsidee nach dieser
Bereinigung aus der Zukunftsliste streichen. Dieser Plan ist ein
abgeschlossener Historieneintrag und keine aktuelle Produkt-Roadmap.

---

## 2. MCP-Tool-Calling wiederherstellen — ERLEDIGT (2026-07-05, Commit `ebb7396`)

### Kernbefund (ändert den ursprünglich vermuteten Fix)

Die aktuellen Paketnamen in `backend/mcp_client.py` sind zu zwei Dritteln
**falsch/nicht real**:
- `@modelcontextprotocol/server-jira` (Zeile ~185) — **existiert nicht**
  unter diesem Scope.
- `@modelcontextprotocol/server-confluence` (Zeile ~211) — **existiert
  nicht** unter diesem Scope.
- `@notionhq/notion-mcp-server` (Zeile ~225) — **echt und offiziell**,
  einziger der drei, der wie im Code geschrieben tatsächlich funktionieren
  würde, sobald Node.js verfügbar ist.

Recherche (Web, 2026-07-05) ergab: Atlassian hat einen offiziellen MCP-
Server, aber als **Remote/Cloud-Server** (OAuth 2.1, kein lokal spawnbares
npm-Paket) — passt nicht zum bestehenden `MCPClient`-Architekturmuster
(lokaler Subprozess + stdio-JSON-RPC). Der praxistauglichste Fit für die
bestehende Architektur ist **`mcp-atlassian`** (`sooperset/mcp-atlassian`,
[PyPI](https://pypi.org/project/mcp-atlassian/), [GitHub](https://github.com/sooperset/mcp-atlassian)) —
ein **reines Python-Paket**, das Jira UND Confluence in einem Server
abdeckt, per `pip install mcp-atlassian` installierbar und per `uvx
mcp-atlassian` oder als Modul lokal als stdio-Subprozess lauffähig — exakt
kompatibel mit `MCPClient.start()`s bestehendem
`asyncio.create_subprocess_exec`-Muster, **ohne dass Node.js im
Backend-Image nötig wird** (nur für Jira/Confluence — Notion braucht
weiterhin Node/npx).

**Das ändert den Fix-Umfang:** statt "Node.js für alle drei Konnektoren
in den Dockerfile" → "Python-Paket für Jira/Confluence + Node.js nur für
Notion".

**Vor Umsetzung zu verifizieren** (nicht mehr Teil dieser Planungssession,
da das echtes Ausprobieren gegen eine echte/Test-Atlassian-Instanz
braucht): ob `mcp-atlassian` bei gleichzeitig gesetzten `JIRA_*`- und
`CONFLUENCE_*`-Umgebungsvariablen automatisch beide Tool-Sets anbietet,
oder ob zwei getrennte Prozesse (einer nur mit Jira-Env, einer nur mit
Confluence-Env) gestartet werden müssen — das bestimmt, ob
`init_mcp_clients_for_sources` (`mcp_client.py:162-230`) für "jira" und
"confluence" weiterhin zwei separate Spawns bleibt oder zu einem
konsolidiert wird.

### Schritte

1. **Paket-Wahl verifizieren** — `mcp-atlassian`s tatsächliches
   CLI-Interface/Env-Var-Namen gegen die aktuelle Version auf PyPI prüfen
   (Namen wie `JIRA_URL`/`JIRA_PERSONAL_TOKEN`/`CONFLUENCE_URL`/
   `CONFLUENCE_PERSONAL_TOKEN` laut Recherche, aber vor dem Schreiben von
   Code exakt gegen die Doku bestätigen).
2. **`backend/requirements.txt`**: `mcp-atlassian` ergänzen.
3. **`backend/mcp_client.py`**: `init_mcp_clients_for_sources` für "jira"/
   "confluence" auf `command="python", args=["-m", "mcp_atlassian"]` (oder
   `uvx`, falls `uv` im Image verfügbar gemacht wird) umstellen, mit den
   korrekten Env-Var-Namen aus Schritt 1. Notion-Zweig unverändert lassen
   (bleibt `npx`-basiert).
4. **`backend/Dockerfile`**: Node.js/npm ergänzen — **nur für Notion**
   nötig. Einfachste Variante angesichts des bestehenden Single-Stage-Builds
   (`python:3.11-slim` Basis): `apt-get install -y nodejs npm` in derselben
   Zeile wie die bestehenden `build-essential libpq-dev`.
5. **Air-Gapped-Bundle-Implikation lösen** (`scripts/build-offline-bundle.sh`):
   `npx -y @notionhq/notion-mcp-server` würde bei einer Kundeninstallation
   ohne Internet zur Laufzeit fehlschlagen (npx versucht, das Paket vom
   öffentlichen npm-Registry zu holen). Fix: im Dockerfile das Paket beim
   Image-Build **vorinstallieren** (`npm install -g @notionhq/notion-mcp-server`)
   und `mcp_client.py`s Notion-Spawn von `npx -y <pkg>` auf einen direkten
   Aufruf des global installierten Binaries umstellen (kein Registry-Fetch
   zur Laufzeit mehr nötig). `mcp-atlassian` hat dieses Problem nicht, da es
   als normale Python-Dependency bereits beim Image-Build via
   `requirements.txt` installiert wird.
6. **Logging fixen** (betrifft das allgemeine Beobachtbarkeitsmuster):
   `mcp_client.py:56-62` (Spawn-Fehler nur `print(..., file=sys.stderr)`,
   `stderr=DEVNULL` verschluckt zusätzlich die Subprozess-Fehlerausgabe
   selbst) — auf echtes `logger.error(...)` inkl. der eigentlichen
   Subprozess-stderr-Ausgabe umstellen, damit ein fehlgeschlagener MCP-Start
   künftig sichtbar ist statt komplett lautlos zu verschwinden.
7. **Entscheidung zur Feature-Flag-Sichtbarkeit klären** (kein Code, reine
   Rückfrage an den Nutzer für eine künftige Session): `config/features.json`
   hat `connectors.confluence/jira/notion` aktuell auf `false` (bewusst,
   Teil des AEC-Pivots). Soll die Wiederherstellung das UI wieder freischalten,
   oder bleibt es backend-seitig repariert, aber UI-seitig weiterhin
   versteckt (z.B. für Kunden, die trotz AEC-Fokus zusätzlich Confluence/
   Jira nutzen und das gezielt aktivieren können sollen)?

### Verifikation

- Unit-/Integrationstest für `mcp_client.py` ergänzen (aktuell **null**
  Testabdeckung) — zumindest den Subprozess-Spawn mocken und prüfen, dass
  `start()` `True`/`False` korrekt zurückgibt und Fehler jetzt geloggt werden.
- Live-Test: eine echte (oder Sandbox-)Confluence/Jira/Notion-Instanz mit
  Testzugangsdaten als `KnowledgeSource` anlegen (Feature-Flag temporär auf
  `true`), einen Chat mit `project_id` auslösen, in den Logs prüfen, dass
  `MCPClient.start()` → `True` und `list_tools()` eine nicht-leere Liste
  liefert.
- Air-Gapped-Pfad: `scripts/build-offline-bundle.sh` einmal durchlaufen
  lassen, den resultierenden Bundle-Container ohne Internetzugang starten,
  bestätigen, dass der Notion-MCP-Spawn nicht versucht, das Netz zu erreichen.

Sources (aus der Recherche für diesen Abschnitt):
- [atlassian/atlassian-mcp-server](https://github.com/atlassian/atlassian-mcp-server) (offizieller Remote-Server, nicht das passende Muster)
- [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) (empfohlene Wahl)
- [mcp-atlassian auf PyPI](https://pypi.org/project/mcp-atlassian/)
- [mcp-atlassian Installationsdoku](https://mcp-atlassian.soomiles.com/docs/installation)

---

## 3. Sidebar-Dateibaum sauber entfernen

### Sanity-Check der Prämisse

Bestätigt per `git log --follow -p`: Commit `438efea` ("feat(sources): add
pin/unpin for knowledge sources with sidebar display", 2026-07-01) hat genau
die JSX-Aufrufstellen (`renderTreeNode(...)`, `renderAnalyseTree()`, den
`sidebarViewMode === 'files' ? ... : ...`-Tab-Switcher) aus dem `return`-Block
entfernt, aber die Funktionsrümpfe, Props und Parent-State stehen gelassen.
Exakt die "Regression aus unvollständigem Refactor" aus der Memory.

**Wichtige Korrektur zur ursprünglichen Annahme:** `buildFileTree` (Zeilen
220-244) und `renderSourceTreeNode` (113-180) sind **nicht** tot — sie
werden aktiv von der "Pinned Knowledge Sources"-Sektion benutzt (Aufruf bei
Zeile 772/779). Nur `renderTreeNode` (der *Projekt*-Dateibaum, zu
unterscheiden von `renderSourceTreeNode`) und `renderAnalyseTree`/
`getEntityBadge` sind tot. **Nicht anfassen:** `buildFileTree`,
`renderSourceTreeNode`, `collapsedFolders`, `toggleFolder`, `sourceFiles`,
`loadingSourceId`, `loadSourceFiles`, `expandedFolderId`.

### In `Sidebar.tsx` zu löschen

| Was | Zeilen (Referenzstand) |
|---|---|
| `renderTreeNode` | 246-314 |
| `getEntityBadge` | 316-395 |
| `renderAnalyseTree` | 397-554 |
| `fileSearchQuery`-State + Setter | 95 |
| `useEffect`, der `fileSearchQuery` bei Projektwechsel zurücksetzt | 182-185 |
| Icon-Imports `Network` (nur Zeile 441 genutzt), `FileCode` (nur 495), `Code` (nur 309) | Import-Zeilen 12/16/19 |

Bereits **jetzt schon** komplett unbenutzt (unabhängig von obiger Liste,
beim selben Anlass mit entfernen): Props `files`, `sidebarViewMode`/
`setSidebarViewMode`, `isLoadingEntities` — werden destrukturiert, aber
nirgends im Dateikörper gelesen.

`SidebarProps`-Interface: `files`, `isLoadingEntities`, `projectEntities`,
`selectedEntity`, `setSelectedEntity`, `handleEntitySelect`,
`sidebarViewMode`, `setSidebarViewMode`, `expandedPrograms`,
`setExpandedPrograms`, `isAnalysisRootExpanded`, `setIsAnalysisRootExpanded`
entfernen. **Bleiben:** `theme`, `isSidebarOpen`, `setIsSidebarOpen`,
`backendStatus`, `startNewChat`, `sessions`, `activeSessionId`,
`handleSessionSelect`, `handleRemoveSession`, `selectedProject`,
`selectedFile`, `handleFileSelect`, `handleLogout`, `connectedSources`,
`pinnedSourceIds`.

### In `page.tsx` (Aufrufstelle `<Sidebar ... />`, Zeilen 2309-2340)

Prop-Zeilen entfernen: `files={files}` (2320), `isLoadingEntities={...}`
(2326), `projectEntities={...}` (2327), `selectedEntity={...}` (2328),
`setSelectedEntity={...}` (2329), `handleEntitySelect={...}` (2330),
`sidebarViewMode={...}` (2332), `setSidebarViewMode={...}` (2333),
`expandedPrograms={...}` (2334), `setExpandedPrograms={...}` (2335),
`isAnalysisRootExpanded={...}` (2336), `setIsAnalysisRootExpanded={...}` (2337).

**Nur die Prop-Zeile löschen, den State behalten** (anderswo aktiv genutzt):
`projectEntities`/`setProjectEntities`, `selectedEntity`/`setSelectedEntity`,
`handleEntitySelect` — alle drei werden von den Split-Pane-Panels/BIM-CAD-
Auswahl-Sync noch gebraucht.

**State komplett löschen** (kein anderer Leser irgendwo im Frontend):
`sidebarViewMode`/`setSidebarViewMode` (Zeile 200), `isAnalysisRootExpanded`/
`setIsAnalysisRootExpanded` (203), `expandedPrograms`/`setExpandedPrograms`
(204), `isLoadingEntities`/`setIsLoadingEntities` (202 + Aufrufe Zeilen
869/876).

**Innerhalb sonst noch aktiver Funktionen einzelne Zeilen entfernen:**
- `handleEntitySelect` (1226-1240): Zeilen 1231-1237 löschen
  (`setSidebarViewMode('analyse')`, `setIsAnalysisRootExpanded(true)`,
  `setExpandedPrograms(...)` + zugehöriger Kommentar). Rest bleibt.
- `handleEditorEntitySelect` (1251-1264): Zeilen 1255-1257 löschen (gleiches
  Muster). Rest bleibt.

### i18n-Keys mit entfernen

`frontend/lib/i18n/de.json:511-513` und `en.json:511-513` —
`sidebar.higherLevelLogic`, `sidebar.noPrograms`, `sidebar.entityTitle`,
ausschließlich von `renderAnalyseTree` benutzt.

### Judgment Calls für die Zukunft (nicht in dieser Session entschieden)

1. **`files`/`setFiles`** (page.tsx 139) wird nach Entfernen von
   `files={files}` komplett schreibend-aber-nie-gelesen (dead write-only
   state) — vollständige Bereinigung würde auch in `ChatView.tsx` (Prop
   `setFiles` Zeile 40) und `SettingsModal.tsx` (Aufrufer nach
   `api.getProjectFiles`) hineinreichen. **Empfehlung:** in diesem Durchgang
   nur `files={files}` an der Sidebar-Aufrufstelle löschen, den Rest
   unangetastet lassen — größere Ripple-Bereinigung als eigene, spätere
   Aufgabe behandeln, nicht hier mit reinziehen.
2. **`useFeatures()`/`features`** in Sidebar.tsx (Zeile 27/90) — komplett
   unbenutzt, aber unabhängig vom Dateibaum-Thema. Gleiche Empfehlung: nicht
   in diesem Durchgang mitentfernen, ist eigentlich Teil des separat schon
   getrackten "orphaned feature flags"-Punkts aus `CLAUDE.md`.
3. **`Search`/`Database`/`Pin`-Icon-Importe** in Sidebar.tsx — vorbestehend
   unbenutzt, unabhängig vom Dateibaum. Nur erwähnen/bei Gelegenheit
   mitnehmen, kein eigener Punkt.

### Verifikation

`npx tsc --noEmit` (muss sauber bleiben), dann im Browser: Sidebar öffnen,
History-Liste + Pinned-Sources-Baum weiterhin funktionsfähig prüfen
(Datei in einer gepinnten Wissensquelle anklicken → öffnet weiterhin
korrekt im Editor).

---

## 4. GAEB-Mengen-/Kostenauswertung — was damit gemeint ist (Erklärung, keine Aufgabe)

`parser/connectors/gaeb.py` liest sowohl das XML-Format (`parse_gaeb_xml`,
Zeilen 49-119) als auch das klassische GAEB90-Textformat (`parse_gaeb_classic`,
122-191) und wandelt jede LV-Position in einen Markdown-Textblock um:
Positionsnummer, **Menge** + Einheit, Beschreibung — das war's. Es gibt:

- **Keine Preis-Extraktion.** Weder Einheitspreis (`<UP>`/EP) noch
  Gesamtpreis (`<GP>`/GP) werden aus der GAEB-Datei gelesen, obwohl beide
  Formate diese Felder enthalten (bei ungeprüften Leistungsverzeichnissen
  oft `0,00` bzw. leer, bei bepreisten/kalkulierten LVs aber vorhanden).
- **Keine strukturierten Daten, nur Text.** Die Positionen landen als
  Freitext in `DocumentChunk` fürs RAG/Chat — es gibt keine eigene
  Datenbanktabelle mit numerischen Spalten (Menge, Einheitspreis,
  Gesamtpreis) pro Position, die man abfragen/aggregieren könnte.
- **Keine Summenbildung.** Keine Berechnung von Titel-/Los-/Gesamtsummen
  aus den Positionen.
- **Kein Abgleich gegen das Modell.** Der Code-Compliance-Checker gleicht
  IFC-Brandschutzklassen gegen Textdokumente ab — eine analoge Prüfung
  "stimmen die im LV
  angegebenen Mengen mit den tatsächlich im IFC-Modell vorhandenen Bauteilen/
  Flächen überein" gibt es für GAEB nicht.

Kurz: **Rohimport funktioniert** (Positionen sind durchsuchbar/befragbar im
Chat), aber es gibt **keine Rechen-/Auswertungsschicht** obendrauf — kein
"wie viel kostet Titel 3 insgesamt", kein "welche Positionen haben Menge 0
oder fehlenden Preis", kein Mengenabgleich gegen das BIM-Modell. Das wäre
ein separates, eigenständiges Feature (neue DB-Tabelle für strukturierte
GAEB-Positionen + Aggregations-/Vergleichs-Endpunkte + Frontend-Ansicht) —
nicht Teil dieses Cleanup-Plans, nur zur Einordnung hier dokumentiert, falls
das als eigener Auftrag später aufgegriffen werden soll.

## 5. Frontend-God-Components entflechten (`page.tsx`, `SettingsModal.tsx`) — OFFEN, für nächste Session vorgemerkt

Aufgenommen 2026-07-16 aus einem gezielten Frontend-Review vor dem Piloten.
Die XSS- und 401-Befunde desselben Reviews sind bereits gefixt (Commit
`41779bc`); **dieser Punkt hier ist bewusst NICHT angefasst worden**, weil er
ein eigenständiges, mehrschrittiges Refactoring ist und kein Ein-Commit-Thema.

### Befund (gemessen, nicht geschätzt)

Zwei Komponenten widersprechen direkt den in `CLAUDE.md` festgeschriebenen
Coding-Guidelines ("Keep `app/page.tsx` clean … only shared state wiring" +
"Encapsulate Local States"):

| Datei | Zeilen | `useState` | `useEffect` | `useCallback` | Props |
|---|---|---|---|---|---|
| `frontend/app/page.tsx` | ~2700 | 68 | 20 | 0 | — |
| `frontend/components/SettingsModal.tsx` | ~4700 | 89 | — | — | ~47 (`interface SettingsModalProps`) |

Konkrete Probleme, die daraus folgen:
- **`page.tsx` ist ein God-Component, kein Orchestrator.** 68 Zustände + 20
  Effekte in einer Datei → Effekt-Reihenfolge-/Abhängigkeitsbugs und
  Re-Render-Kaskaden. **0 `useCallback`** bei 27 `handle*`-Funktionen: jeder
  Handler wird pro Render neu erzeugt und nach unten durchgereicht — Memoi-
  sierung der Kinder läuft dadurch ins Leere.
- **`SettingsModal.tsx` mit ~47 Props + 89 lokalen States** ist praktisch nicht
  mehr sicher änderbar (Prop-Drilling-Hölle, jede Signatur-Änderung fasst die
  Aufrufstelle in `page.tsx` mit an).

**Pilot-Relevanz:** kein Sicherheits-/Funktions-Blocker, aber in den Iterations-
Wochen 3–5 produziert jede Änderung auf dieser Basis leicht Regressionen. Daher
Wartbarkeits-Schuld, die vor/während einer längeren Zusammenarbeit abgetragen
werden sollte — nicht in Panik vor dem ersten Termin.

### Vorgeschlagener Schnitt (inkrementell, risikoarm zuerst)

Nicht als ein Big-Bang. Reihenfolge nach Aufwand/Risiko:

1. ~~**`SettingsModal`-Props bündeln (kleinster, sichtbarster Gewinn).**~~
   **ERLEDIGT 2026-07-16.** Variante (a) umgesetzt: `components/settings/
   SettingsContext.tsx` (`SettingsContextValue`, `SettingsProvider`,
   `useSettings()`). `page.tsx` stellt den Provider an der Aufrufstelle bereit;
   `SettingsModal` liest die ~36 Werte via `useSettings()` statt aus Props, der
   4700-Zeilen-Body blieb dabei unverändert (nur Signatur/Interface). tsc +
   vitest grün. **Browser-Durchklick der Settings-Tabs steht noch aus** (siehe
   Verifikation) — reiner Typecheck deckt keine Laufzeit-Regression im UI ab.
2. **`SettingsModal` in Tab-Komponenten zerlegen.** Die 89 States sind fast
   sicher pro Wizard-Schritt/Tab lokal — jeder Tab wird eine eigene Komponente
   mit eigenem `useState`, statt alles auf oberster Modal-Ebene. Das ist genau
   die "Encapsulate Local States"-Regel aus CLAUDE.md.
   **BEGONNEN 2026-07-16 — Muster etabliert, 6 Tabs herausgelöst:**
   `components/settings/tabs/EditorSettingsTab.tsx` (`editor`),
   `LayoutSettingsTab.tsx` (`layout`, inkl. der zuvor auf Modal-Ebene liegenden
   Handler `handleThemeToggle` + `exportNeo4j`, die nur dieser Tab nutzte),
   `AiSettingsTab.tsx` (`ai`, inkl. der 5 Profil-Handler + 7 profil-lokalen
   Formular-States), `ProjectSetupTab.tsx` (`project-setup`, inkl. der 5
   new-project-States + `handleCreateProject`; Tab-Navigation via `onDone`-Prop,
   da die gehört dem Modal), `LogsSettingsTab.tsx` (`logs`, inkl.
   `activeLogSource`/`refreshingLogs`/`diagnostics*`, `handleGenerateDiagnostics`,
   `refreshKnowledgeSources` + 5s-Polling) und `TeamsSettingsTab.tsx` (`teams`,
   vollständig eigenständig inkl. eigenem `allUsers`). Alle konsumieren ihren
   Zustand direkt via `useSettings()` (kein Prop-Drilling, dank Schritt 1; einzige
   Ausnahme: `ProjectSetupTab.onDone` für die Navigation). In `SettingsModal`
   bleibt je `{settingsTab === '…' && <…Tab />}`. `SettingsModal.tsx` von ~4707
   auf ~3218 Zeilen.
   **Noch offen (gleiches Muster, `grep "settingsTab === '"`):** `projects`,
   `git-setup`, `sources`, `sources-setup` (je ~500 Zeilen, eigene lokale States/
   Handler, die beim Herauslösen mitwandern müssen — vor dem Schnitt jeweils kurz
   die lokalen Abhängigkeiten prüfen). Jeweils einzeln tsc+vitest+Browser
   verifizieren.
   **Erledigte Cross-Tab-Kopplungen (Referenz fürs Muster bei den restlichen
   Tabs):** `logs`↔`sources` teilten `connectedSources` + `refreshKnowledgeSources`
   — gelöst, indem `connectedSources` geteilter Context-State blieb und der
   `sources`-Sync-Poll-Effekt im Modal einen eigenen Inline-Refetch bekam (nur
   `setConnectedSources`), während das logs-seitige Refresh in `LogsSettingsTab`
   wanderte. `teams`↔`projects` teilten `allUsers` (nur von `refreshTeams`
   befüllt, im `projects`-Tab gelesen — latenter Bug: für Nicht-Global-Admins nie
   befüllt) — gelöst, indem `TeamsSettingsTab` sein eigenes `allUsers` hält und
   der `projects`-Tab im Modal `allUsers` selbst via `refreshAllUsers()` beim
   Öffnen lädt (behebt zugleich den Bug). **Achtung** beim `sources`/`projects`-
   Schnitt: `connectedSources`/`allUsers` müssen an ihren jeweiligen Lade-/Nutzstellen
   bleiben, nicht blind in eine Tab-Komponente ziehen.
   `GitSetupTab.tsx` (`git-setup`): attach-only-Wizard, Einstieg ausschließlich über
   den "Repo anbinden"-Button im `projects`-Tab (setzt `targetProjectIdForGitSetup`
   + navigiert). Der Wizard bekam `targetProjectId` als Prop und `onDone` für die
   Rück-Navigation; die 17 Wizard-States + Handler + `parsePublicGitUrl` sind lokal
   (mounten frisch je Eintritt, daher wurde `resetWizard` zu schlichtem `onDone`).
   `targetProjectIdForGitSetup` bleibt im Modal (der projects-Tab setzt es).
   **NB Produktrichtung:** Git soll künftig als Wissensquellen-Typ (`sources`)
   behandelt werden statt als eigener Wizard — der `git-setup`-Tab ist damit
   Kandidat, später in `sources-setup` aufzugehen (eigenes, geplantes Vorhaben nach
   dem Refactoring). Siehe Memory `git-as-knowledge-source`.
   `SourcesSetupTab.tsx` (`sources-setup`): Wissensquellen-Anlege-Wizard, Einstieg
   aus dem `sources`-Tab (setzt `activeSourceType` + navigiert). Bekam
   `activeSourceType` + `selectedSourceRepoId` als Props und `onDone` (= reset
   `activeSourceType` + zurück zu `sources`). 23 Wizard-States + 7 Connect-Handler
   lokal; neue Quellen werden via `setConnectedSources` an die geteilte Context-
   Liste angehängt. `activeSourceType`/`selectedSourceRepoId` bleiben im Modal
   (der `sources`-Tab setzt/nutzt sie). Der Einstiegs-Button setzte vorher die
   Formularfelder zurück — entfällt, da die Komponente frisch mit denselben
   Defaults mountet. (`sourcesWizardStep` ist bereits vorher toter State.)
   `SourcesTab.tsx` (`sources`): reine Render-Komponente + 4 Handler
   (handleDeleteSource/handleSyncRepo/handleSyncSource/handleIntervalChange), die
   alle nur aus Context/Hooks lesen. `connectedSources` bleibt geteilter Context-
   State (Modal-Poll-Effekt schreibt dieselbe Liste). `selectedSourceRepoId` bleibt
   Modal-State (Sync mit `selectedProject` + wird an `SourcesSetupTab` gereicht) und
   kommt als Prop. Beide Wizard-Einstiege (Quelle anlegen, Git-Repo anbinden) laufen
   über die Callbacks `onSetupSource`/`onAttachGit` — die Navigation + zugehöriger
   State (`activeSourceType`, `targetProjectIdForGitSetup`, `sourcesWizardStep`)
   bleiben im Modal. **Letzter offener Tab `projects`** (größter, ~500 Zeilen): teilt
   `projects`/`setProjects`, `allUsers` (via `refreshAllUsers`), `projectStats`,
   `projectMembers`/`projectAccessRequests`, `selectedProject`, sowie den git-setup-
   Einstieg (`targetProjectIdForGitSetup`) und den project-setup-Einstieg.
   `ProjectsTab.tsx` (`projects`): kapselt das gesamte Projekt-Domänenmodell
   (Mitglieder/Zugriffsanfragen, Discoverable-Projects, Abschluss/Promote, Inline-
   Edit, eigenes `allUsers` — nach der teams-Extraktion nur noch hier gebraucht)
   inkl. aller ~15 Handler + Lade-Effekt beim Mount. `projects`/`selectedProject`/
   `connectedSources` bleiben geteilter Context-Zustand (via `useSettings`); der
   git-setup-Einstieg lag entgegen der Annahme NICHT hier, sondern im `sources`-Tab,
   daher braucht `ProjectsTab` nur `onNewProject` (-> project-setup). Damit ist
   **Schritt 2 abgeschlossen**: `SettingsModal.tsx` ist ein 237-Zeilen-Shell (Tab-
   Nav, Header/Footer, die beiden verbliebenen Effekte `selectedSourceRepoId`-Sync +
   `sources`-Poll, und die Navigations-/Wizard-Einstiegs-Callbacks). Ungenutzte
   Context-Destrukturierungen + Icon-/UI-Imports wurden dabei entfernt. (`sources`
   `WizardStep` bleibt als bereits vorher toter State bestehen.)
3. **`page.tsx`: Domänen-State aus dem Orchestrator ziehen.** Kandidaten für
   eigene Context-Provider/Hooks (`useProjects`, `useChatSessions`,
   `useKnowledgeSources`, `useWorkspaceLayout`): die zusammenhängenden
   `useState`-Cluster + ihre Fetch-Effekte + Handler wandern in einen Hook,
   `page.tsx` konsumiert nur noch. Ziel ist die in CLAUDE.md beschriebene Rolle
   "only shared state wiring".
4. **Erst nach Schritt 3 `useCallback`/`memo` gezielt nachziehen** — vorher
   lohnt es nicht, weil die Handler eh noch verschoben werden.

### Verifikation (pro Schritt, nicht erst am Ende)

- `npx tsc --noEmit` grün nach jedem Schritt.
- `npx vitest run` grün.
- Im Browser die betroffene Fläche real durchklicken (Settings-Modal alle Tabs
  öffnen/speichern; Projekt-Wechsel; Chat-Session laden/teilen) — Refactoring
  ohne Verhaltensänderung ist die ganze Prämisse, also gegen das laufende UI
  gegenprüfen, nicht nur Typecheck.
- Kein neuer `dangerouslySetInnerHTML`-Aufruf ohne `lib/sanitize.ts` (siehe
  Commit `41779bc` — der sichere Pfad existiert jetzt, beim Verschieben von
  Render-Code nicht versehentlich daran vorbei bauen).
