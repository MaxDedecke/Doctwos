# Doctus — Technischer Implementierungsplan v1.0

> **Umsetzungsstand (31.07.2026):** AP-0 bis AP-4 abgeschlossen und verifiziert.
> AP-5 abgeschlossen: Panel-Typen, Fokusobjekt je Code-Panel, gruppiertes
> Entity-Referenzen-Menü und F-069 (persistierte Zeilen-Referenz im Chat) sind
> umgesetzt. AP-5 und AP-6 sind abgeschlossen; als Nächstes folgt AP-7
> (Design-Tokens, Job-Center und i18n-Nachzug).
> Fortlaufender Stand, offene Punkte und nächste Schritte: **`docs/UMSETZUNGSSTAND.md`**.
> Festgelegte Streitpunkte: **`docs/ENTSCHEIDUNGEN.md`**.

**Basis:** Anforderungskatalog v1.2 (Stand 31.07.2026) · Condo-Template (`develop`, Commit 27789d4)
**Zielrepo:** `MaxDedecke/Doctwos`
**Leitprinzip dieses Plans:** *Maximale Übernahme, minimaler Neubau.* Doctus ist kein Greenfield-Projekt, sondern ein **Fork des Condo-Templates mit ausgetauschter Fachlogik**. Alles, was nicht COBOL-spezifisch ist, wird 1:1 übernommen — inklusive Bugs, Kommentaren und Betriebs-Härtungen, die dort bereits erkämpft wurden.

---

## 0. Executive Summary

Die Analyse des Templates ergibt eine überraschend günstige Ausgangslage: **rund 75 % des MUSS-Umfangs existiert bereits lauffähig** und muss nur umbenannt bzw. entkernt werden. Der Aufwand konzentriert sich auf fünf echte Neubauten:

| # | Neubau | Umfang | Anteil |
|---|--------|--------|--------|
| 1 | **COBOL-AST-Parser** (F-020…F-034) | ~4.000 LOC + Testkorpus | dominierend |
| 2 | **Kantenmodell + Call-Graph-View** (F-032, F-066) | ~1.200 LOC | groß |
| 3 | **Multi-Branch-Monorepo-Ingestion** (F-019, NF-004) | ~600 LOC (Umbau `git.py`) | mittel |
| 4 | **Fokus-Objekt + Zeilen-Referenz-Chat** (F-067…F-069) | ~700 LOC Frontend | mittel |
| 5 | **Lokale Auth + Job-Center + Design-Tokens** (F-001…F-006, NF-006, NF-014) | ~900 LOC | mittel |

Alles andere — Workspace, Chat, Streaming, Sessions/Snapshots, Konnektoren (Git/Confluence/Jira/WebDAV/Folder/Upload), Delta-Sync, Sync-Transparenz, RAG-Kern, pgvector+HNSW, LLM-Profile, MCP-Tool-Calling, Link Manager, Topics, Knowledge-Graph, Verschlüsselung at-Rest, i18n, Docker/Offline-Bundle, Diagnostics, Alembic — wird **übernommen**.

**Gesamtschätzung:** 14–20 Personenwochen bis lauffähiges Showcase (MUSS-Umfang), davon 6–8 Wochen allein Parser inkl. Testkorpus.

---

## 1. Ausgangslage

### 1.1 Was im Template steckt (verifiziert)

```
Condo-develop/                 43.937 LOC (Python + TS/TSX, ohne node_modules)
├── backend/     FastAPI, 19 API-Router, Alembic (33 Migrationen), Auth via OIDC
├── parser/      Celery-Worker, 12 Konnektoren, BaseConnector-ABC + Registry
├── frontend/    Next.js, Monaco, SplitPaneWorkspace, KnowledgeGraphView, Settings-Wizard
├── docker-compose{,.dev,.offline}.yml, install.sh, scripts/build-offline-bundle.sh
└── docs/        24 Dokumente, u.a. OPEN_SOURCE_CLEARING.md
```

### 1.2 Wichtige Befunde aus der Code-Analyse

| Befund | Konsequenz für den Plan |
|--------|-------------------------|
| `parser/code_parser.py` ist **81 Zeilen reines Text-Chunking** — die `languages/`-Ebene wurde bereits als toter Code entfernt (`docs/TECH_DEBT_CLEANUP_PLAN.md §1`) | Der COBOL-Parser hat **keine Vorlage**. Kompletter Neubau, bestätigt Anforderung F-020. |
| `backend/core/auth_dependency.py` implementiert bereits **eigene signierte Session-Cookies** (`itsdangerous`, HTTP-only, `secure` aus `FRONTEND_URL` abgeleitet, `SESSION_SECRET_KEY`-RuntimeError-Pattern) | **DOC-F-006 ist faktisch bereits erfüllt.** Nur `oidc.py` + `api/auth.py` werden ersetzt, die Session-Schicht bleibt unverändert. Deutlich kleiner als im Katalog vermutet. |
| `CodeEntity` existiert, wird aber **nur vom IFC-Konnektor** befüllt (`parser/connectors/ifc.py:311`); `code_references` wurde per Migration `c7d8e9f0a1b2` gedroppt | Entity-Tabelle bleibt als Gerüst, wird COBOL-tauglich erweitert. Kantentabelle ist Netto-Neubau (bestätigt F-032). |
| HNSW-Index auf `document_chunks.embedding` existiert bereits (`b1c2d3e4f5a6`, `m=16, ef_construction=64`) | **NF-010 zu großen Teilen erfüllt.** Nur Lasttest + ggf. Tuning offen. |
| `GitConnector` macht Shallow Clone (`depth=1`) + optional Sparse-Checkout + Delta-Sync mit 50k-Datei-Schwelle | **F-010 zu ~70 % erfüllt.** Fehlt: `--filter=blob:none`, Multi-Branch-Isolation (F-019), Wiederaufsetzbarkeit (NF-004). |
| Backend-Image installiert **Node.js + npm** nur für `@notionhq/notion-mcp-server` | Mit Notion-Entfall (Kat. 2.2) fällt die Node-Runtime aus dem Backend-Image → kleineres Image, erfüllt F-049 („keine Node.js-Runtime erforderlich"). |
| `backend/models/database.py` ↔ `parser/models/database.py` müssen **byte-identisch** von Hand gehalten werden (getrennte Build-Kontexte) | NF-008: im Zuge des Neuaufbaus in ein geteiltes Package auflösen (Abschnitt 12.2). |
| Kein „Job-Center"/globale Aktivitätsanzeige im Frontend vorhanden | NF-014 ist echter Neubau (aber klein, da alle Run-Tabellen schon existieren). |
| `parser/utils.py:85` hat `extract_text_from_pdf_ocr` (pytesseract + pdf2image) | **OCR-Fallback F-012/F-018 bereits erfüllt.** |
| `cloud_llm_allowed()` in `backend/core/config.py:98` + `ALLOW_CLOUD_LLM` | **F-050 bereits erfüllt**, nur Default-Prüfung + UI-Ausblendung nachziehen. |

### 1.3 Offene Eingaben (blockieren nichts, aber früh klären)

1. **Der „bestehende frühere COBOL-Parser-Ansatz"** (Entscheidungspunkt 2) liegt nicht auf dieser Maschine. → Bitte bereitstellen; er bestimmt, ob AP-2 bei 6 oder 8 Wochen landet.
2. **Fujitsu-CI-Werte** (Hex-Farben, Logo-Assets, Hausschrift-Lizenz) aus dem internen Brand-Portal (NF-006).
3. **Reale Bestandszahlen** der DRV (Anzahl Programme/Copybooks/Dateien, Repo-Größe) für die Lasttest-Abnahme (NF-010).
4. **Repräsentativer COBOL-Beispielbestand** für den Testkorpus (F-033) — ohne den ist der Parser nicht abnehmbar.

---

## 2. Zielarchitektur

Unverändert aus dem Template übernommen — **keine neue Technologie, keine neuen Services:**

```
┌───────────┐   ┌──────────────┐   ┌────────────────┐
│ frontend  │──▶│ backend-api  │──▶│ db (pgvector)  │
│ Next.js   │   │ FastAPI      │   │ PostgreSQL 16  │
└───────────┘   └──────┬───────┘   └────────▲───────┘
                       │                    │
                  ┌────▼────┐   ┌───────────┴──────┐
                  │ redis   │◀──│ parser-worker    │  (Celery)
                  │(valkey) │   │ parser-beat      │
                  └─────────┘   └───────────┬──────┘
                                            │
                                     ┌──────▼──────┐
                                     │ ollama      │  bge-m3 + Mistral NeMo
                                     └─────────────┘
```

Begründung für „keine Änderung": Jede zusätzliche Komponente (Neo4j, ElasticSearch, ANTLR-Runtime, tree-sitter) erzeugt OSS-Clearing-Aufwand (NF-003), Offline-Bundle-Aufwand (NF-002) und Betriebsrisiko — bei null Anforderungsnutzen. Entscheidungspunkt 9 hat Neo4j bereits ausgeschlossen; dieser Plan schließt konsequent auch alle anderen Zusatz-Services aus.

---

## 3. Übernahme-Matrix (das Herzstück)

Legende: **Ü** = 1:1 übernehmen · **U** = umbenennen/anpassen · **N** = Neubau · **X** = löschen

### 3.1 Backend

| Datei | Aktion | Bemerkung |
|---|---|---|
| `main.py` | U | Router-Liste kürzen (aec_workflows, regulations raus), Rest identisch |
| `agent.py` | U | Tool-Set: `get_repo_entities` → COBOL-Entities; Graph-Kontext ergänzen (F-043) |
| `mcp_client.py` | U | Notion-Zweig entfernen, mcp-atlassian bleibt (F-049) |
| `core/auth_dependency.py` | **Ü** | unverändert — Session-Schicht ist bereits die geforderte |
| `core/config.py` | U | OIDC-Vars raus, `BOOTSTRAP_*` rein; `cloud_llm_allowed()` bleibt |
| `core/db_setup.py`, `core/tracing.py`, `core/teams.py`, `core/projects.py` | **Ü** | |
| `core/oidc.py` | X | Keycloak/OIDC entfällt (Kat. 2.2) |
| `api/auth.py` | N | ~150 LOC lokaler Login (Abschnitt 11) |
| `api/users.py` | U | + Anlegen/Deaktivieren/Passwort-Reset (F-004) |
| `api/knowledge_sources.py` (1.149 LOC) | U | AEC-Endpunkte (`/ifc`,`/dwg`,`/gaeb`,`/convert-dxf-to-svg`) raus; `/upload` bleibt (F-018); `/git` um `branch` erweitern (F-010/019) |
| `api/chat.py` (1.025 LOC) | **Ü** | Streaming, Provider-Guard, Quellen — unverändert |
| `api/projects.py`, `teams.py`, `connectors.py`, `search.py`, `serializers.py`, `schemas.py`, `system.py`, `config_router.py`, `diagnostics.py` | **Ü** | ggf. Feldnamen |
| `api/entity_links.py`, `knowledge_links.py`, `link_chat.py`, `topics.py` | **Ü** | F-080/081/082 explizit MUSS |
| `api/graph.py` | U | Neo4j-Export → GraphML/CSV/JSON (F-083); Rest bleibt |
| `api/aec_workflows.py`, `app/agents/hoai.py` | X | |
| `api/regulations.py` | X | Compliance out of scope (Kat. 5) |
| `api/entities.py` | **N** | Fokus-Objekt + 1-Hop-Nachbarschaft (F-067) |
| `api/callgraph.py` | **N** | Call-Graph-Daten + Export (F-066) |
| `api/jobs.py` | **N** | Job-Center-Aggregation über alle `*_runs`-Tabellen (NF-014) |
| `services/search.py`, `ollama_client.py` | **Ü** | |
| `services/ifc_reader.py`, `dxf_reader.py` | X | |
| `tests/` | U | AEC-Tests raus, Auth-Tests umschreiben, Rest übernehmen |

### 3.2 Parser

| Datei | Aktion | Bemerkung |
|---|---|---|
| `worker.py` | U | Task-Liste bereinigen, Beat-Schedule bleibt |
| `db.py`, `utils.py`, `ollama_client.py`, `core/config.py`, `core/tracing.py` | **Ü** | inkl. OCR-Fallback |
| `chunk_reindex.py` | **Ü** | `reindex_chunks_preserving_links` ist kritisch — Links überleben Re-Sync |
| `connectors/base.py` (287 LOC) | **Ü** | Sync-Lock, Progress, Logging — das Fundament von F-013/F-014 |
| `connectors/registry.py` | U | Registry-Einträge auf Doctus-Typen reduzieren |
| `connectors/git.py` (348 LOC) | **U (groß)** | → `CobolGitConnector`, Abschnitt 7 |
| `connectors/confluence.py`, `jira.py`, `webdav.py`, `folder.py`, `http_retry.py`, `extract.py` | **Ü** | F-011/F-012/F-017 damit erledigt |
| `connectors/ifc.py`, `dwg.py`, `gaeb.py`, `dalux.py`, `autodesk.py`, `notion.py` | X | |
| `tasks/sync.py`, `document.py`, `shared.py`, `diagnostics.py` | **Ü** | |
| `tasks/link_builder.py`, `cross_link_builder.py` | **Ü** | F-080/082 |
| `tasks/compliance.py` (1.176 LOC), `regulation_import.py` | X | |
| `cobol/` (neues Package) | **N** | Abschnitt 6 — der große Brocken |
| `tests/` | U | + neuer Golden-File-Testkorpus (F-033) |

### 3.3 Frontend

| Datei | Aktion | Bemerkung |
|---|---|---|
| `app/page.tsx` (2.595 LOC) | U | AEC-Zweige raus, Fokus-Objekt-State rein |
| `components/SplitPaneWorkspace.tsx` (1.255 LOC) | U | Panel-Typen: `bim`/`compliance` raus, `callgraph` rein |
| `components/ChatView.tsx`, `AgentSteps.tsx`, `MarkdownContent.tsx`, `GlobalSearch.tsx` | **Ü** | |
| `components/Sidebar.tsx` | U | AEC-Baum → Programm→Section→Paragraph (F-065) |
| `components/KnowledgeGraphView.tsx` (1.260 LOC) | **Ü** | F-083 explizit „Übernahme unverändert" |
| `components/CallGraphView.tsx` | **N** | eigenständig, UI-Bausteine aus KnowledgeGraphView wiederverwenden (F-066) |
| `components/LinkManagerView.tsx`, `TopicsPanel.tsx`, `LinkChatView.tsx` | **Ü** | |
| `components/LoginView.tsx` | U | OIDC-Redirect → Formular (F-001) |
| `components/BimCadViewer.tsx`, `ComplianceView.tsx` | X | |
| `components/JobCenter.tsx` | **N** | NF-014 |
| `components/settings/tabs/*` | U | Sources/Git-Wizard um Branch-Feld; Users-Tab neu (F-004) |
| `components/ui/*`, `lib/*`, `lib/i18n/*` | **Ü** | |
| `tailwind.config.js`, `app/globals.css` | **U (groß)** | Fujitsu-Design-Tokens, Abschnitt 10.5 |

### 3.4 Betrieb

| Datei | Aktion |
|---|---|
| `docker-compose.yml`, `.offline.yml`, `.dev.yml` | U — Keycloak-Service raus, Namen/Env |
| `install.sh`, `scripts/build-offline-bundle.sh`, `scripts/install-offline.sh` | **Ü** |
| `.github/workflows/ci.yml` | U — + Parser-Golden-File-Job (F-033) |
| `.github/keycloak/` | X |
| `docs/OPEN_SOURCE_CLEARING.md` | **Ü** als Vorlage (NF-003 Pflichtartefakt) |
| `docs/DEPLOYMENT.md`, `FOLDER_WATCH.md`, `PROMPT_INJECTION.md`, `DIAGNOSTICS_HARDENING.md`, `PROJECT_ACCESS_CONTROL.md`, `TEAM_ACCESS_CONTROL.md` | U |
| `AEC_FEATURES.md`, `COMPLIANCE_EVAL*.md`, `IFC_*`, `Businessplan*`, `ROADMAP_PILOTKUNDE.md`, `watched/` | X |

---

## 4. Bootstrap: So entsteht das Repo konkret

Reihenfolge ist wichtig — **erst kopieren, dann entkernen, dann umbauen.** Nicht selektiv kopieren: das verliert Kommentare und Härtungen, die man später teuer nachbaut.

```bash
# AP-0.1 — Vollkopie ohne Template-Historie
rsync -a --exclude .git --exclude node_modules Condo-develop/ Doctwos/
cd Doctwos && git checkout -b develop

# AP-0.2 — Entkernung (Löschliste aus Abschnitt 3, Katalog 2.2)
git rm -r backend/api/aec_workflows.py backend/api/regulations.py backend/app/agents \
          backend/core/oidc.py backend/services/ifc_reader.py backend/services/dxf_reader.py \
          parser/connectors/{ifc,dwg,gaeb,dalux,autodesk,notion}.py \
          parser/tasks/{compliance,regulation_import}.py \
          frontend/components/{BimCadViewer,ComplianceView}.tsx \
          .github/keycloak watched AEC_FEATURES.md docs/COMPLIANCE_EVAL*.md ...

# AP-0.3 — Alembic-Reset: keine Condo-Migrationskette mitschleppen (Katalog 2.2)
git rm backend/alembic/versions/*.py     # alle 33
#   → eine einzige neue Baseline-Migration (Abschnitt 5)

# AP-0.4 — Rename condo→doctus (Bezeichner, Container, Cookie, DB, Images)
grep -rl 'condo\|Condo\|CONDO' --exclude-dir=.git . | xargs sed -i 's/condo/doctus/g; s/Condo/Doctus/g; s/CONDO/DOCTUS/g'
#   Achtung: danach `docker-compose*.yml`, `.env.example`, `install.sh` manuell durchsehen
#   (Volume-Pfade ./data/postgres bleiben, Image-Digests bleiben).

# AP-0.5 — Erststart grün bekommen: docker compose up, /health, Login-Stub
```

**Abnahmekriterium AP-0:** `docker compose up -d` startet alle Services healthy, `GET /health` grün, Frontend lädt, `npx tsc --noEmit` fehlerfrei. Ab hier wird nur noch inkrementell gebaut.

> **Abgenommen am 31.07.2026** (`./install.sh`): sieben Services healthy, `/health` mit `database/redis/ollama = ok`, Frontend HTTP 200, Anmeldung end-to-end durchgespielt. Details in `docs/UMSETZUNGSSTAND.md`.

---

## 5. Datenmodell

### 5.1 Baseline-Migration (eine einzige, sauber)

Übernommen aus `b42f8210a7ea_baseline_schema.py`, bereinigt und erweitert. Enthaltene Tabellen:

> **Gegengeprüft am 31.07.2026.** `alembic upgrade head` gegen eine leere DB, danach
> `alembic revision --autogenerate` — Delta leer. Der erste Durchlauf war es nicht:
> `uq_team_memberships_user_team` fehlte in der Migration und die beiden
> `document_chunks`-Indizes fehlten umgekehrt im ORM. Beides korrigiert; wer die
> Baseline anfasst, wiederholt diese Gegenprobe.

**Unverändert übernommen:** `teams`, `team_memberships`, `projects`*, `project_memberships`, `project_access_requests`, `knowledge_sources`, `document_chunks`, `chat_sessions`, `chat_messages`, `entity_doc_links`, `knowledge_links`, `topics`, `topic_nodes`, `link_builder_runs`, `diagnostics_runs`
*(`projects`: `jurisdiction`/`regulation_*`/`building_class`/`usage_types`/`special_building_types` entfallen)

**Entfallen:** alle `compliance_*`, alle `regulation_*`, `ifc_scan_files`, `dwg_scan_files`, `gaeb_scan_files`

### 5.2 `users` — geändert (F-001, F-004, F-005)

```python
class User(Base):
    __tablename__ = "users"
    id                   = Column(Integer, primary_key=True)
    username             = Column(String, unique=True, index=True, nullable=False)  # ersetzt `sub`
    email                = Column(String, index=True, nullable=True)
    name                 = Column(String, nullable=True)
    password_hash        = Column(String, nullable=False)   # Argon2id, NIE EncryptedString
    role                 = Column(String, nullable=False, server_default="user")  # 'superuser'|'user'
    is_active            = Column(Boolean, nullable=False, server_default="true")
    must_change_password = Column(Boolean, nullable=False, server_default="false")
    failed_login_count   = Column(Integer, nullable=False, server_default="0")
    locked_until         = Column(DateTime(timezone=True), nullable=True)
    created_at, last_login_at = ...
```
> **Invariante (F-005):** `password_hash` ist bewusst `String`, **nicht** `EncryptedString`. Verschlüsselung wäre reversibel — gefordert ist ein Salted Hash. Ein CI-Test prüft, dass das Feld nie in Serializern, Logs oder im Diagnostics-Bundle auftaucht.

### 5.3 `code_entities` — erweitert (F-030)

```python
type            # 'program'|'copybook'|'section'|'paragraph'|'data_item'|'file_fd'|'sql_table'|'sql_block'
                # v2: 'jcl_job'|'jcl_step'
parent_id       # FK self, ondelete CASCADE — Programm→Section→Paragraph, Programm→DataItem
qualified_name  # 'XAAOA.MAIN-SECTION.INIT-PARA' — stabiler Schlüssel für Deep-Links
meta_json       # PIC-Klausel, Level, OCCURS/REDEFINES, SQL-Statement-Typ, Format (fixed/free)
content_hash    # Inkrementalität: unveränderte Datei → Entities/Kanten nicht neu schreiben
# entfällt: ifc_guid
UniqueConstraint(source_id, qualified_name)
Index(source_id, type), Index(source_id, file_path), Index(name)
```

> **Entscheidungspunkt D-1:** F-030 listet `sql_block` nicht als Entity-Typ, F-032 verlangt aber Kanten `SQL-Block→Datenfeld (USES)`. Eine Kante braucht auf beiden Seiten einen Knoten. **Vorschlag:** `sql_block` als achter Entity-Typ aufnehmen (nicht fokussierbar im Sinne F-067, aber als Kantenendpunkt und Kontext-Träger für F-027 vorhanden). Zur Bestätigung.

### 5.4 `code_edges` — Netto-Neubau (F-032)

```python
class CodeEdge(Base):
    __tablename__ = "code_edges"
    id             = Column(Integer, primary_key=True)
    project_id     = Column(FK projects, CASCADE, index=True)
    source_id      = Column(FK knowledge_sources, CASCADE, index=True)   # Quellen-Isolation F-019
    src_entity_id  = Column(FK code_entities, CASCADE, nullable=False, index=True)
    dst_entity_id  = Column(FK code_entities, CASCADE, nullable=True,  index=True)  # NULL = unresolved/dynamic
    dst_name       = Column(String, nullable=False, index=True)  # immer gesetzt, auch bei resolved
    type           = Column(String, nullable=False, index=True)
        # v1: CALL | PERFORM | COPY | DEFINES | USES | READS | WRITES
        # v2: EXECUTES
    resolution     = Column(String, nullable=False)   # 'resolved' | 'unresolved' | 'dynamic'
    src_start_line = Column(Integer, nullable=False)  # exakte Fundstelle im Quellprogramm
    src_end_line   = Column(Integer, nullable=False)
    meta_json      = Column(JSON, nullable=True)      # z.B. {"thru": "END-PARA"}, {"replacing": [...]}
    __table_args__ = (
        Index("ix_code_edges_src_type", "src_entity_id", "type"),
        Index("ix_code_edges_dst_type", "dst_entity_id", "type"),
        Index("ix_code_edges_dstname",  "source_id", "dst_name"),   # Nachauflösung
    )
```

**Warum `dst_name` immer gesetzt ist:** Beim inkrementellen Sync wird Programm A vor Programm B geparst. Der `CALL 'B'` aus A ist zunächst `unresolved`. Sobald B geparst ist, löst ein günstiger Nachlauf-Pass (`UPDATE ... FROM code_entities WHERE dst_name = name`) alle offenen Kanten auf — ohne Reparse. Das ist der Mechanismus, der Monorepo-Ingestion überhaupt wiederaufsetzbar macht (NF-004).

### 5.5 `source_scan_files` — vereinheitlicht

Ersetzt `folder_scan_files`/`ifc_scan_files`/`dwg_scan_files`/`gaeb_scan_files` durch **eine** Tabelle (`source_id`, `file_path`, `content_hash`, `parse_status`, `parse_error`, `indexed_at`, UNIQUE(source_id, file_path)). Sie ist gleichzeitig:
- Idempotenz-Journal für NF-004 („Abbruch bei Datei n → Fortsetzung bei n+1")
- Fehlerregister für F-029 (nicht parsebare Datei → Eintrag, kein Sync-Abbruch)
- Datenquelle für den Datei-Zähler in F-014

### 5.6 `knowledge_sources` — erweitert (F-019)

```python
branch            = Column(String, nullable=True)   # explizites Feld, nicht mehr in spaces-JSON versteckt
repo_fingerprint  = Column(String, nullable=True, index=True)  # sha1(normalisierte Repo-URL)
sync_cursor       = Column(JSON, nullable=True)     # {"last_commit":"…","last_path":"…","phase":"parse"}
# UNIQUE(project_id, url, branch)  ← NICHT UNIQUE(url); F-019 explizit
```

---

## 6. Der COBOL-Parser (AP-2 — größter Neubau)

### 6.1 Nicht verhandelbare Grundregeln

1. **Zeilennummern sind heilig.** Jede Entity und jede Kante trägt physische Start-/Endzeile der Originaldatei. Copybooks werden **nie in den Programmtext expandiert** — sonst verschieben sich alle Zeilennummern und die Codeview-Navigation (F-061/F-067/F-069) bricht. Stattdessen: `COPY`-Kante speichern.
2. **Kein Abbruch.** Jede Ebene fängt Fehler und liefert ein Teilergebnis + Fehlereintrag (F-029). Ein nicht parsebares Programm wird zu generischem Text-Chunking degradiert und bleibt durchsuchbar.
3. **Kein LLM im Parser.** Der Parser ist deterministisch. Golden Files müssen byte-stabil reproduzierbar sein (F-033).
4. **Streaming.** Datei für Datei, nie den Gesamtbestand im Speicher (NF-004).

### 6.2 Package-Layout

```
parser/cobol/
├── model.py          # Dataclasses: LogicalLine, CobolProgram, Section, Paragraph,
│                     #              DataItem, FileDescriptor, SqlBlock, ParsedEdge, ParseResult
├── source_format.py  # F-021: Fixed/Free-Autodetektion, Spaltenzerlegung (1-6 Seq, 7 Ind, 8-72 Code),
│                     #        Kommentar (*,/), Continuation (-), Debug (D)
│                     #        → List[LogicalLine] mit Rückverweis auf physische Zeile
├── lexer.py          # Tokenizer über LogicalLines: Wörter, Literale ('..', "..") , Nummern,
│                     #        Satzenden (.), Area A/B-Position, Pseudo-Text (== ==) für REPLACING
├── embedded.py       # F-034: EXEC <dialect> … END-EXEC als atomarer Block erkannt & übersprungen.
│                     #        LÄUFT VOR ALLEM ANDEREN — sonst zerlegt ein Punkt im SQL die Paragraphen.
├── divisions.py      # F-020: IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE + SECTIONs, PROGRAM-ID
├── data_division.py  # F-025: Level-Nummern (01/05/77/88), PIC, REDEFINES, OCCURS, VALUE,
│                     #        FD/SD → FileDescriptor; Gruppenhierarchie über parent_id
├── procedure.py      # F-023/024: Paragraphen mit exakten Zeilenbereichen,
│                     #        CALL 'LIT' | CALL WS-VAR, PERFORM [THRU], GO TO
├── copybook.py       # F-022: COPY name [OF lib] [REPLACING ==a== BY ==b==]
│                     #        Auflösung über CopybookIndex (repo-interne Suchpfade)
├── sql.py            # F-027: leichtgewichtiger EXEC-SQL-Klassifikator
│                     #        Typ | Tabellen/Views | Host-Variablen (:WS-FELD) | Cursor-Namen
├── xref.py           # F-025: Verwendungsstellen-XREF Datenfeld↔Paragraph
│                     #        (MOVE/IF/COMPUTE/ADD/…; Wort-Match gegen DataItem-Namensindex)
├── chunking.py       # F-041: COBOL-bewusstes Chunking entlang Paragraph/Section-Grenzen
└── parse.py          # Orchestrierung: parse_program(text, path, copybook_index) -> ParseResult
```

### 6.3 Pipeline (pro Datei)

```
Rohtext
  │  source_format.detect()          Fixed | Free   (Heuristik: Spalte 7 Indikatoren, Seq-Nummern)
  ▼
LogicalLine[]  (code, comment?, continuation aufgelöst, phys_line erhalten)
  │  embedded.mask()                 EXEC…END-EXEC → Blockmarker, Inhalt zur Seite gelegt
  ▼
Token[]        (lexer)
  │  divisions.scan()
  ▼
CobolProgram { id, divisions[], sections[], paragraphs[] }   ← exakte Zeilenbereiche
  │  data_division.parse()   → DataItem[], FileDescriptor[]
  │  procedure.scan()        → CALL/PERFORM/GOTO-Kanten
  │  copybook.resolve()      → COPY-Kanten (resolved|unresolved)
  │  sql.classify()          → SqlBlock[] + READS/WRITES/USES-Kanten
  │  xref.build()            → USES-Kanten Paragraph→DataItem
  ▼
ParseResult { entities[], edges[], chunks[], errors[] }
```

### 6.4 Zwei-Pass-Ingestion über das Repo

```
Pass 0  Copybook-Index bauen:  alle *.cpy/*.copy scannen → {NAME: [pfade]}  (nur Namen, kein Volltext)
Pass 1  pro Datei: parse → Entities/Kanten/Chunks persistieren, Fortschritt committen
Pass 2  Kanten-Nachauflösung:  UPDATE code_edges SET dst_entity_id = … WHERE resolution='unresolved'
                               AND dst_name IN (SELECT name FROM code_entities WHERE …)
```
Pass 0 ist billig (nur Dateinamen) und macht die Copybook-Auflösung in Pass 1 vollständig lokal — genau die Vereinfachung, die Entscheidungspunkt 5 (gleiches Monorepo) erlaubt.

### 6.5 Testkorpus (F-033 — abnahmerelevant)

```
parser/tests/cobol_corpus/
├── fixtures/
│   ├── 01_minimal.cbl              Divisions, ein Paragraph
│   ├── 02_fixed_edge.cbl           Spalte 72 Abschneiden, Continuation, Sequenznummern
│   ├── 03_free_format.cbl          Free-Format-Autodetektion
│   ├── 04_copy_replacing.cbl       COPY … REPLACING mit Pseudo-Text
│   ├── 05_copy_missing.cbl         nicht auflösbares Copybook → 'unresolved', kein Silent Fail
│   ├── 06_data_qualified.cbl       OF/IN-Qualifizierung, REDEFINES, OCCURS DEPENDING ON
│   ├── 07_exec_sql.cbl             SELECT/DECLARE CURSOR/FETCH, Host-Variablen
│   ├── 08_exec_cics.cbl            CICS-Block muss sauber übersprungen werden (F-034)
│   ├── 09_dynamic_call.cbl         CALL WS-PGM → 'dynamic'
│   ├── 10_perform_thru.cbl         PERFORM A THRU B
│   └── 99_garbage.cbl              vorsätzlich kaputt → Fallback greift, kein Crash
└── golden/  *.json                 erwartete ParseResult-Serialisierung
```
CI-Job `parser-golden`: Regression = **blockierend** (F-033). Erkennungsquoten (z. B. „≥ 98 % der Programme liefern PROGRAM-ID + ≥1 Paragraph") werden am realen DRV-Bestand kalibriert und als Schwellwert in die CI eingetragen.

### 6.6 Aufwandsschätzung AP-2

| Teilstück | PW |
|---|---|
| `source_format` + `lexer` + `embedded` (Fundament, höchstes Risiko) | 1,5 |
| `divisions` + `procedure` (Struktur, Call-/Perform-Graph) | 1,5 |
| `data_division` + `xref` | 1,5 |
| `copybook` + Auflösungslogik | 0,5 |
| `sql` (leichtgewichtig, kein DB2-Grammar) | 1,0 |
| Testkorpus + Golden Files + CI | 1,5 |
| **Summe** | **7,5 PW** |

---

## 7. Ingestion: Monorepo-tauglicher Git-Konnektor (AP-3)

> **Umgesetzt am 31.07.2026.** `parser/git_utils.py` (reine Bare-Mirror-/
> Worktree-Primitiven, kein DB-Zugriff) + `parser/connectors/git.py`
> (Neubau). Zwei Abweichungen vom Pseudocode oben, beide durch Ausprobieren
> an einem echten lokalen Repo gefunden, nicht aus der Doku ersichtlich:
> 1. `git -C wt reset --hard FETCH_HEAD` schlägt aus einem an den Bare-Mirror
>    angehängten Worktree fehl (`unknown revision`), obwohl die Datei im
>    gemeinsamen Gitdir liegt — FETCH_HEAD ist von dort schlicht nicht
>    auflösbar. Umgangen über einen benannten Ref: `fetch` zieht
>    `refs/heads/<branch>` im Bare-Mirror per `branch -f` auf FETCH_HEAD nach,
>    Worktrees resetten gegen den Branch-Namen statt FETCH_HEAD direkt.
> 2. `git branch -f` verweigert das Verschieben eines Branches, solange
>    irgendein Worktree ihn nicht-losgelöst ausgecheckt hat — bricht, sobald
>    zwei Wissensquellen (verschiedene Projekte) denselben Branch desselben
>    Repos referenzieren, was F-019 ausdrücklich erlaubt. Alle Worktrees
>    werden daher mit `--detach` angelegt.
>
> `sync_cursor` trägt nur `{"last_commit": …}` — `last_path`/`phase` aus dem
> Modell-Kommentar blieben ungenutzt, weil der Resume-Check ohnehin pro Datei
> über `SourceScanFile.content_hash` (Git-Blob-SHA, gekürzt auf 32 Zeichen)
> läuft und damit feiner greift als ein einzelner Cursor-Zeiger. E-3 (Partial
> Clone per `DOCTUS_GIT_PARTIAL_CLONE`) ist umgesetzt; der optionale
> `repack -a -d`/`fetch --refetch`-Nachlauf aus E-3 ist weiterhin offen, da er
> laut E-3 erst an einem echten großen Bestand gemessen werden sollte — der
> fehlt bis heute (Plan §1.3, Punkt 4).

### 7.1 Physisches Layout (F-019, „Implementierungsfreiheit")

```
/repos/
├── bare/<repo_fingerprint>.git        ein Bare-Mirror je Repo-URL, geteilt über alle Quellen
└── wt/ks_<source_id>/                 ein Worktree je Wissensquelle (= je Branch)
```
Ein 100-GB-Monorepo liegt damit **einmal** auf Platte, egal wie viele Projekte es mit verschiedenen Branches einbinden. Die logische Trennung (eigene `source_id`, eigene Chunks/Entities/Kanten, eigenes Sync-Intervall) bleibt davon unberührt — genau die im Katalog beschriebene Aufteilung.

### 7.2 Clone/Fetch (F-010)

```bash
# Erstanlage
git clone --bare --filter=blob:none --no-tags <auth_url> bare/<fp>.git
git -C bare/<fp>.git worktree add ../wt/ks_<id> <branch>       # + optional sparse-checkout set

# Delta-Sync
git -C bare/<fp>.git fetch --filter=blob:none origin <branch>
git -C wt/ks_<id> reset --hard FETCH_HEAD
git -C wt/ks_<id> diff --name-status <last_commit> HEAD
```
Redis-Lock zweistufig: `lock:git_fetch:<fingerprint>` (verhindert paralleles Fetch auf denselben Bare-Store) und das bestehende `lock:sync_source:<id>` aus `BaseConnector`. Die Lease-Verlängerung (`redis_client.expire` im Producer-Loop) wird 1:1 übernommen.

### 7.3 Wiederaufsetzbarkeit (NF-004)

Der bestehende Producer/Consumer-Loop in `git.py:294-324` (Semaphore 20, 50 Tasks in Flight) bleibt. Ergänzt wird:
- **Vor** dem Embedding: `content_hash` gegen `source_scan_files` prüfen → unverändert = überspringen (billigster Resume-Mechanismus).
- **Nach** jedem persistierten Dokument: Zeile in `source_scan_files` + `sync_cursor` aktualisieren.
- Backpressure: die Semaphore bekommt eine Env-Größe (`EMBED_CONCURRENCY`, Default 20) statt Konstante, damit eine schwächere Ollama-Instanz gedrosselt werden kann.

### 7.4 Dateiklassifikation (F-016)

```python
COBOL_EXT   = {".cbl", ".cob", ".cobol"}
COPYBOOK_EXT= {".cpy", ".copy"}
JCL_EXT     = {".jcl", ".proc", ".prc"}     # v1: nur Text-Index, keine Strukturanalyse (F-026)
```
Konfigurierbar über `DOCTUS_COBOL_EXTENSIONS` (Env) + Wissensquellen-Feld — ersetzt die `EXT_LANG_MAP` aus `git.py:23`.

---

## 8. RAG & Retrieval (AP-4)

> **Läuft, Stand 31.07.2026.** Pass 0-2 (§6.4) sind umgesetzt: `parser/
> connectors/git.py::_build_copybook_index` (Pass 0), `parser/
> cobol_persist.py` (Pass 1 — Entity-/Kanten-UPSERT mit ID-Erhalt über
> Reparse hinweg, siehe Docstring dort für die dabei gefundene CASCADE-
> Falle), `parser/tasks/edge_resolver.py::resolve_global_edges` (Pass 2).
> `parse.py` bekam `parse_copybook()` für eigenständige Copybook-Entities
> und die quellenweite XREF-Vererbung über COPY-Grenzen einschließlich
> `COPY … REPLACING` (E-2). F-043 und die AP-4-relevanten Backend-Router
> `/entities` und `/callgraph` sind ebenfalls umgesetzt und getestet.
> Details: `docs/UMSETZUNGSSTAND.md`.

| Anforderung | Umsetzung | Aufwand |
|---|---|---|
| F-040 pgvector/bge-m3 | **übernommen**, unverändert | — |
| F-041 COBOL-bewusstes Chunking | `cobol/chunking.py`: ein Chunk je Paragraph (Split bei Übergröße, Merge bei Winzlingen), `metadata_json` = `{program, section, paragraph, start_line, end_line, format}` | 0,5 PW |
| F-042 klickbare Quellen | **übernommen** (Sources-JSON existiert), nur Metadaten-Felder erweitern | 0,2 PW |
| F-043 graph-erweitertes Retrieval | Nach Vektor-Top-k: Entities der Treffer bestimmen → 1 Hop über `code_edges` (COPY-Ziele, Aufrufer) → deren Definitions-Chunks anhängen, hartes Token-Budget | 0,8 PW |
| F-044 GlobalSearch | **übernommen**, Suchziele auf COBOL-Entities umstellen | 0,3 PW |
| F-049 MCP-Tool-Calling | **übernommen**, Notion-Zweig entfernen | 0,2 PW |
| F-027 SQL-Antwortfähigkeit | Prompt-Assembly: bei Zeilenreferenz in einem SQL-Block → vollständiger Block + PIC-Klauseln der Host-Variablen + umgebender Paragraph in den Kontext | 0,5 PW |

---

## 9. Backend-API-Delta

Neu (drei schlanke Router, alles andere bleibt):

```
GET  /entities/{id}                     Entity + Definition
GET  /entities/{id}/neighbors           F-067: 1-Hop, gruppiert nach type+direction
     ?types=CALL,COPY&direction=in|out|both
GET  /entities/resolve?source_id&path   F-067: Top-Level-Objekt einer Datei (.cbl→program, .cpy→copybook)
GET  /callgraph/focus?entity_id&hops=1  F-066: Knoten+Kanten für die Call-Graph-View (serverseitig begrenzt)
GET  /callgraph/export?format=graphml|csv|json
GET  /jobs                              NF-014: Aggregation über sync-Quellen + *_runs-Tabellen
POST /jobs/{kind}/{id}/retry            NF-014: Wiederaufnahme
POST /auth/login, /auth/logout, /auth/change-password
GET  /users                             F-004: Liste inkl. Sperr-/Aktivstatus
POST /users                             F-004: anlegen, liefert das Startpasswort einmalig
PATCH /users/{id}                       F-004: Rolle, Name, aktiv/deaktiviert
POST /users/{id}/reset-password         F-004: neues Startpasswort, hebt die Sperre mit auf
POST /users/{id}/unlock                 F-005: Sperre aufheben
```
Alle Endpunkte laufen unter der bestehenden `_authenticated`-Dependency und der bestehenden projekt-/team-Sichtbarkeitsprüfung (`_is_project_visible` aus `api/graph.py` wird nach `core/projects.py` gehoben und wiederverwendet).

---

## 10. Frontend (AP-5)

### 10.1 Panel-Modell (F-064)

> **Stand 31.07.2026: umgesetzt.** `bim`/`compliance` sind entfernt; die
> bestehende 1–4-Panel-Mechanik arbeitet mit den bereinigten View-Typen.

`'chat' | 'code' | 'doc' | 'webview' | 'graph' | 'callgraph'` — `bim`/`compliance` entfallen. Die 1–4-Panel-Mechanik in `SplitPaneWorkspace.tsx` und `ensurePanelType()` in `page.tsx` bleiben unverändert; nur die Typunion und die Render-Zweige ändern sich.

### 10.2 Fokus-Objekt (F-067/F-068)

> **Stand 31.07.2026: umgesetzt.** Dateiöffnung löst das Top-Level-Objekt über
> `/entities/resolve` auf, jeder Code-Panel-Zustand hält seinen eigenen Fokus.
> Monaco-Entity-Klicks wechseln nur den Fokus. Das Menü lädt die gruppierte
> 1-Hop-Nachbarschaft über `/entities/{id}/neighbors`; ungeparste Dateien und
> fokusierte Objekte ohne Nachbarn haben eigene Leerzustände.

Neuer Zustand pro Code-Panel: `focusedEntity: {id, type, name, qualified_name}`.
- Datei öffnen → `GET /entities/resolve` → Top-Level-Objekt setzen.
- Klick auf eine Monaco-Dekoration → Fokus wechselt, **kein** Sprung.
- Referenzen-Menü rendert `GET /entities/{id}/neighbors`, gruppiert: „Aufrufer" / „ruft auf" / „verwendet Copybook" / „verwendet von" / „liest Tabelle" / „schreibt Tabelle".
- Datei ohne geparste Entity → Menü zeigt Hinweistext (nicht leer).

Die Dekorations-Infrastruktur (Underlines/Glyphs/Hover) und die Sprung-Breadcrumb existieren bereits und werden übernommen.

### 10.3 Zeilen-Referenz in den Chat (F-069)

> **Stand 31.07.2026: umgesetzt.** Der Gutter-Klick erzeugt eine strukturierte
> Referenz mit Datei, Zeile, Quelle sowie umschließendem Programm/Section/Paragraph,
> öffnet bei Bedarf ein Chat-Panel und übernimmt die konkrete Quellzeile in den
> RAG-Kontext. Beim Senden wird die Referenz in `metadata_json.refs[]` persistiert;
> der Chip bleibt nach dem Laden einer Sitzung anklickbar und springt zurück in die
> referenzierte Codezeile.

Monaco `glyphMarginClickHandler` → `{file, line, program, section, paragraph}` → aktives Chat-Panel (oder eines öffnen) → Chip im Eingabefeld → beim Senden in `ChatMessage.metadata_json.refs[]` persistiert → Chip in der Historie klickbar (Rücksprung) → Codeausschnitt geht in den RAG-Kontext.

### 10.4 Call-Graph-View (F-066)

> **Stand 31.07.2026: umgesetzt.** Die eigenständige `CallGraphView` lädt den
> Fokusgraphen über `/callgraph/focus` mit 1–3 Hops, bietet Kantentyp-Filter und
> Zoom/Fit-Steuerung und öffnet Codeknoten in der zugehörigen Datei. Dynamische
> und unaufgelöste Ziele erscheinen als gestrichelte Warnkanten mit eigenem
> Zielknoten. JSON, CSV und GraphML werden über `/callgraph/export` heruntergeladen;
> die serverseitige 500-Knoten-Grenze wird im UI sichtbar gemacht.

Eigenständige Komponente, aber **Layout-/Zoom-/Fokus-Bausteine aus `KnowledgeGraphView.tsx` extrahiert** statt neu geschrieben (der Katalog erlaubt das ausdrücklich). Inkrementelles Hop-Laden (NF-011), Kantentyp-Filter, dynamische/unaufgelöste Kanten visuell abgesetzt (gestrichelt + Warnfarbe), Export GraphML/CSV/JSON.

### 10.5 Design-Token-System (NF-006)

```
frontend/app/globals.css     :root { --ds-* } Light-first + Dark-Variante
frontend/tailwind.config.js  theme.extend.colors → ausschließlich var(--ds-*)
```
Regeln:
- **Eine** Quelle für Farbe. Ein ESLint-/CI-Check verbietet Hex-Literale und `text-blue-500`-artige Tailwind-Farbklassen in `components/`.
- Fujitsu-Rot nur als `--ds-accent` für CTAs, aktive Zustände, Fokusringe, Logo — **nie** als Fließtextfarbe (Kontrast, NF-012).
- Kantentyp-Farben der Graph-Views werden aus der Token-Palette abgeleitet, nicht einzeln gesetzt.
- Monaco behält ein eigenes Entwickler-Farbschema (explizit erlaubt).
- Die bestehende Condo-Palette in `tailwind.config.js` wird **ersetzt**, nicht ergänzt — sonst bleiben zwei Systeme nebeneinander bestehen.

### 10.6 Job-Center (NF-014)

Persistenter Header-Button mit Badge (Anzahl laufender Jobs) → Panel mit allen aktiven/fehlgeschlagenen Vorgängen: Quellen-Syncs (`knowledge_sources.sync_status/progress/progress_message/estimated_finish_at` — existiert bereits), Link-Builder-Runs, Diagnostics-Runs. Poll-Intervall 3 s, Fehlerdetail aufklappbar, „Wiederaufnehmen"-Button.

---

## 11. Auth-Umbau (AP-1 — kleiner als gedacht)

> **Umgesetzt am 31.07.2026.** Eine Abweichung von der Vorgabe unten: das Rate-Limit
> zählt nicht nur in Redis, sondern zusätzlich dauerhaft in der `users`-Zeile — sonst
> hebt ein Redis-Neustart jede Sperre auf. Begründung in `docs/ENTSCHEIDUNGEN.md`, E-5.

**Bleibt unverändert:** `core/auth_dependency.py` (signiertes HTTP-only-Cookie, 14 Tage, `secure` aus `FRONTEND_URL`), `SESSION_SECRET_KEY`-RuntimeError-Pattern in `core/config.py`, alle `_authenticated`-Dependencies, Team-/Projekt-Sichtbarkeit.

**Neu (~150 LOC Backend, ~120 LOC Frontend):**
```python
POST /auth/login     {username, password}
    → Argon2id-Verify (argon2-cffi, MIT)
    → Rate-Limit: Redis-Zähler pro (username, IP), exponentielles Backoff, locked_until (F-005)
    → create_session_cookie_value(user.id)   ← bestehende Funktion
    → 200 {must_change_password: bool}
POST /auth/change-password   {old, new}      erzwungen bei must_change_password (F-001)
GET  /auth/me                                 ← bestehend, unverändert
```
**Bootstrap (F-001):** `core/db_setup.py` legt beim ersten Start genau einen Superuser an. Passwort aus `BOOTSTRAP_SUPERUSER_PASSWORD`; ist die Variable leer, wird eines generiert und **einmalig** ins Startlog geschrieben. `must_change_password=True`. Kein DB-Zugriff nötig, um die Software in Betrieb zu nehmen.

**Kapselung für v2 (Katalog Abschnitt 5):** Es gibt genau eine Auth-Dependency und genau einen User-Provisioning-Pfad (`core/users.py::get_or_create_user`). Ein späterer IdP-Anschluss ergänzt dort einen zweiten Zweig und **ergänzt** die lokale User-Tabelle, statt sie zu ersetzen.

**Rollenmodell v1:** genau `superuser` und `user` (F-004). Die bestehenden Projekt-Rollen (`admin`/`pruefingenieur`/`member`) in `project_memberships` werden auf `admin`/`member` reduziert.

---

## 12. Betrieb, CI, Qualität

### 12.1 Deployment
`docker-compose.yml` unverändert bis auf: Keycloak-Service raus, OIDC-Env raus, `BOOTSTRAP_*` rein, Node.js aus `backend/Dockerfile` raus, Image-Namen `doctus-*`. Offline-Bundle-Skripte funktionieren dadurch ohne Änderung (NF-002). Alle Image-Digest-Pinnings bleiben.

### 12.2 NF-008: Modell-Duplikation auflösen
Empfehlung: Build-Kontext beider Dockerfiles auf das Repo-Root heben und ein geteiltes `shared/`-Package (`database.py`, `crypto_types.py`) in beide Images kopieren. Fallback, falls das zu invasiv wird: CI-Job `diff -q backend/models/database.py parser/models/database.py` als harte Gate. **Nicht** wieder zwei handgepflegte Kopien ohne Absicherung.

> **Stand:** Der Fallback läuft (Job `model-sync`). Die eigentliche Auflösung über einen gemeinsamen Build-Kontext steht weiterhin aus — bis dahin gilt: wer ein ORM-Modell ändert, ändert beide Kopien.

### 12.3 CI (`.github/workflows/ci.yml`)
Bestehende Jobs übernehmen + ergänzen:
`tsc --noEmit` · `pytest backend` · `pytest parser` · **`parser-golden` (F-033, blockierend)** · `models-identical` (NF-008) · `design-tokens` (keine Hex-Literale, NF-006) · `no-password-leak` (F-005) · `pip-licenses` gegen die Allowlist (NF-003).

> **Stand 31.07.2026.** Vorhanden: `frontend` (tsc + vitest + e2e), `backend`, `parser`,
> `model-sync` (= `models-identical`), `no-password-leak`. Es fehlen noch
> `parser-golden` (kommt mit AP-2), `design-tokens` (AP-7) und `pip-licenses` (AP-9).
>
> **Bekannte Lücke:** Weder der `backend`- noch der `parser`-Job stellt einen Ollama
> bereit. Drei Tests brauchen einen (Embedding-/Retrieval-Pfad) und tragen deshalb
> `@requires_ollama`: lokal laufen sie, in der CI werden sie übersprungen. Ob
> stattdessen ein `ollama`-Service in beide Jobs gehört — Image plus 1,2 GB Modell pro
> Lauf —, ist offen.

### 12.4 NF-003 OSS-Clearing
`docs/OPEN_SOURCE_CLEARING.md` aus dem Template übernehmen und neu befüllen. Zu prüfende Änderungen gegenüber Condo: **entfernt** ifcopenshell/ezdxf/authlib/`@notionhq/notion-mcp-server`; **neu** argon2-cffi (MIT); **weiterhin zu bestätigen** Mistral NeMo (Apache 2.0), bge-m3 (MIT), Valkey (BSD-3), pgvector (PostgreSQL License). Ein CI-Job (`pip-licenses`/`license-checker`) hält die Liste aktuell. **Release-Voraussetzung.**

### 12.5 NF-012 Barrierefreiheit
Von Anfang an, nicht nachträglich: Tastaturbedienbarkeit aller sechs Panel-Typen, sichtbare Fokusringe (Token `--ds-focus`), Kontrastprüfung im Design-Token-Check, `aria-live` für Job-Center und Streaming-Antworten, semantische Baumnavigation in Sidebar/Referenzen-Menü. Verbindlichen BITV-Umfang früh mit dem Auftraggeber klären.

---

## 13. Arbeitspakete & Reihenfolge

| AP | Inhalt | Abhängig von | PW | Anforderungen |
|----|--------|--------------|-----|---------------|
| ~~**AP-0**~~ | ~~Fork, Entkernung, Rename, Alembic-Baseline, Erststart grün~~ **erledigt** | — | 1,0 | Kat. 2.1/2.2 |
| ~~**AP-1**~~ | ~~Lokale Auth, Bootstrap-Superuser, User-Verwaltung, Rate-Limit~~ **erledigt** | AP-0 | 1,5 | F-001…006 |
| **AP-2** | **COBOL-Parser + Testkorpus** | AP-0 | 7,5 | F-020…034 |
| ~~**AP-3**~~ | ~~Monorepo-Git-Konnektor, Multi-Branch, resumable Sync~~ **erledigt** | AP-0 | 2,0 | F-010, F-016, F-019, NF-004 |
| **AP-4** | Entity-/Kanten-Persistenz + Nachauflösung + Retrieval | AP-2, AP-3 | 2,0 | F-030…032, F-041, F-043 |
| ~~**AP-5**~~ | ~~Frontend: Panels, Fokus-Objekt, Referenzen-Menü, Zeilen-Chip~~ **erledigt** | AP-4 | 2,5 | F-061, F-064…069 |
| ~~**AP-6**~~ | ~~Call-Graph-View + Export~~ **erledigt** | AP-4 | 1,5 | F-066 |
| **AP-7** | Design-Token-System (Fujitsu), Job-Center, i18n-Nachzug | AP-5 | 1,5 | NF-006, NF-014 |
| **AP-8** | Konnektoren-Nachzug (Upload/CSV, Confluence/Jira/WebDAV-Retest) | AP-3 | 1,0 | F-011, F-012, F-017, F-018 |
| **AP-9** | Härtung: Lasttest, Barrierefreiheit, OSS-Clearing, Offline-Bundle, Doku | alle | 2,0 | NF-002/003/010/011/012 |
| | **Summe** | | **22,5 PW** | |

**Parallelisierung:** AP-2 (Parser, Python) und AP-5/AP-7 (Frontend) sind vollständig unabhängig. Bei zwei Entwickler:innen liegt der kritische Pfad bei **AP-0 → AP-2 → AP-4 → AP-6** ≈ 12–13 Wochen.

**Empfohlene Showcase-Reihenfolge (Fujitsu-Kontext, „Geschwindigkeit vor Vollausbau"):** Nach AP-0/1/3 existiert bereits ein lauffähiges System, das COBOL-Code als Text indexiert und beantwortet. Jeder weitere AP macht es messbar besser — es gibt zu keinem Zeitpunkt einen „großen Knall", auf den man wartet.

---

## 14. Risiken

| # | Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| R1 | **Realer COBOL-Bestand weicht von Annahmen ab** (Dialekt-Eigenheiten, Präprozessor-Direktiven, Sonderformate) | Parser-Erkennungsquote bricht ein — trifft den größten AP | Testkorpus **vor** dem Parserbau aus realem Bestand ziehen (siehe offene Eingabe 4). F-029-Fallback macht auch 60 % Erkennung noch produktiv nutzbar. |
| R2 | Erstindexierung eines 100-GB-Monorepos dauert Tage | Akzeptanz | NF-004 (resumable) + NF-014 (Transparenz) sind genau dafür MUSS. Zusätzlich: Priorisierung nach Pfad-Whitelist (Sparse-Checkout) für den Showcase. |
| R3 | Ollama-Durchsatz limitiert das Embedding | Ingestion-Dauer | Backpressure per Env-Semaphore; Embedding-Batchgröße messbar machen; ggf. zweite Ollama-Instanz (reine Compose-Änderung). |
| R4 | Fujitsu-CI-Vorgaben kommen spät | Rework im Frontend | Token-System **jetzt** bauen, mit Platzhalterwerten. Der Farbwechsel ist dann ein Ein-Datei-Commit. |
| R5 | Kantenmodell wächst unerwartet stark (XREF Datenfeld↔Paragraph ist die volumenstärkste Kantenart) | DB-Größe, Query-Latenz | XREF-Kanten in eigener Partition/Index-Strategie; Menge früh am realen Bestand messen; notfalls XREF auf 01-Level-Gruppen aggregieren. |
| R6 | BITV-Umfang wird spät verbindlich | teures Nachrüsten | NF-012 sagt es selbst: „nachträglich teuer". Von Beginn an mitbauen (AP-5/AP-7), nicht in AP-9 schieben. |

---

## 15. Traceability (Anforderung → Arbeitspaket)

| Bereich | IDs | AP | Status im Template |
|---|---|---|---|
| Benutzer/Teams/Zugriff | F-001…006 | AP-1 | Session-Schicht ✅, Login ➕ |
| Wissensquellen | F-010…019 | AP-3, AP-8 | Konnektoren ✅, Multi-Branch ✅ |
| COBOL-Analyse | F-020…034 | AP-2, AP-4 | ❌ Netto-Neubau |
| RAG & Index | F-040…044, F-049 | AP-4 | ✅ weitgehend |
| LLM-Profile | F-045…050 | AP-0 | ✅ vollständig |
| Workspace & Views | F-060…069 | AP-5, AP-6 | Basis ✅, Fokus/Callgraph ➕ |
| Sessions | F-070…073 | AP-0 | ✅ vollständig |
| Links & Graph | F-080…083 | AP-0 | ✅ vollständig |
| Nicht-funktional | NF-001…014 | AP-9 (+ laufend) | ✅ bis auf NF-006/NF-014 |

Legende: ✅ übernehmbar · ➕ Erweiterung · ❌ Neubau

---

## 16. Nächste Schritte (konkret)

> Laufend gepflegt in `docs/UMSETZUNGSSTAND.md` — die Liste hier hält nur den groben Kurs fest.

1. ~~**AP-0 ausführen**~~ — erledigt am 31.07.2026, Erststart-Abnahme am selben Tag nachgeholt (Docker steht seitdem auf der Entwicklungsmaschine). Ergebnis: lauffähiges, AEC-freies Doctus-Gerüst mit lokaler Anmeldung und einer Alembic-Baseline, die per Autogenerate gegen eine echte DB gegengeprüft ist.
2. ~~**AP-1 fertigstellen**~~ — erledigt am 31.07.2026: Rate-Limit/Kontosperre beim Login (F-005), Nutzerverwaltung inkl. Users-Tab (F-004).
3. ~~**AP-2 starten**~~ — Fundament erledigt am 31.07.2026: `parser/cobol/source_format.py`,
   `embedded.py`, `lexer.py` + 26 Unit-Tests. Als Nächstes: `divisions.py` + `procedure.py`.
4. **Parallel:** die offenen Eingaben aus Abschnitt 1.3 einholen. Stand 31.07.2026: der frühere Parser-Ansatz ist **nicht verfügbar** (AP-2 rechnet mit dem oberen Ende der Schätzung), ein realer COBOL-Beispielbestand kommt **später** — bis dahin wird gegen selbst gebaute Fixtures entwickelt.
5. ~~**D-1 entscheiden**~~ — entschieden: `sql_block` ist ein Entity-Typ (siehe `docs/ENTSCHEIDUNGEN.md`, E-4).
