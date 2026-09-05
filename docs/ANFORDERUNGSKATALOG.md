# Doctus – Anforderungskatalog v1.5

**Abgleich mit der Software: 05.09.2026**  
**Software-Ground-Truth:** Repository `Doctwos`, Commit `925a605` vom 05.09.2026  
**Ausgangsdokument:** `Doctus_Anforderungskonzept.pdf`, Version 1.2, Stand 31.07.2026

**Nachtrag 05.09.2026:** erneuter Codeabgleich (22 Commits seit der v1.4-Ground-Truth
`cdb72cc`). Sechs zuvor TEILWEISE geführte Punkte sind jetzt erfüllt (DOC-F-014,
DOC-F-016, DOC-F-063, DOC-F-064, DOC-F-065, DOC-F-083 — O-029/O-030/O-031/O-032/O-034/
O-036 behoben); eine neue, sicherheitsrelevante Anmeldemethode (DOC-F-007, SSO/OIDC,
O-041) sowie eine zuvor nicht formulierte, bereits umgesetzte Erweiterung (DOC-F-092,
Sitzung ohne Chat-Nachricht, O-038) sind ergänzt. DOC-F-013/DOC-F-016/DOC-F-018 tragen
die erweiterte Upload-Allowlist (DOCX/DOC, O-044) nach. DOC-NF-010/DOC-F-082 tragen den
neuen serverseitigen Deckel und die Frontend-Anbindung von `/graph/focus` für die
Knowledge-Graph-Übersicht (O-053) nach; DOC-NF-011 wechselt auf ERFÜLLT für die
identifizierten Risikofälle. Abschnitt 5 ist um den jetzt gelieferten CSV/GraphML-Export
bereinigt.

**Nachtrag 03.09.2026:** erneuter Codeabgleich (29 Commits seit der v1.3-Ground-Truth
`fdfb906`). Ergebnisse: DOC-F-069 ist inzwischen erfüllt; mehrere TEILWEISE-Punkte
bestehen unverändert und sind jetzt als Folge-Todos O-029–O-036 in
[`OFFENE_ENTWICKLUNGSPUNKTE.md`](OFFENE_ENTWICKLUNGSPUNKTE.md) nachgetragen; zwei
zuvor nicht formulierte, bereits umgesetzte Anforderungen (DOC-F-090, DOC-F-091)
sind ergänzt.

## 1. Zweck und Verbindlichkeit

Dieses Dokument ist die aktualisierte, bearbeitbare Fassung des bisherigen Anforderungskatalogs. Es beschreibt den tatsächlich vorhandenen Stand der Software. Wo die ursprüngliche Anforderung weitergehend war, ist sie an die Implementierung angepasst und die Abweichung wird ausdrücklich genannt.

Die Software ist für diesen Abgleich die maßgebliche Quelle. Eine Anforderung gilt als:

- **ERFÜLLT** – in der Software umgesetzt und im Code bzw. durch Tests nachvollziehbar.
- **TEILWEISE** – grundsätzlich vorhanden, aber mit einer dokumentierten Einschränkung oder noch ausstehender Abnahme.
- **OFFEN** – nicht umgesetzt oder noch nicht belastbar abgenommen.
- **GEÄNDERT** – gegenüber v1.2 bewusst auf den realen v1-Umfang korrigiert.

Das PDF v1.2 bleibt als historische Fassung erhalten. Diese Markdown-Datei ist die aktuelle Arbeits- und Referenzfassung.

## 2. Kurzfazit des Abgleichs

Die Kernfunktionen sind vorhanden: lokale Anmeldung und Projektberechtigungen, read-only Quellenanbindung, COBOL-Analyse, Copybook-/XREF-Auflösung, Codeansichten, Callgraph, Knowledge Graph, Chat/RAG, Job Center und Offline-Betrieb.

Die wichtigsten Korrekturen gegenüber v1.2 sind:

1. Uploads sind jetzt einheitlich: die UI bietet PDF/Markdown/Text/DOCX/DOC an, der Upload-Endpunkt setzt dieselbe Allowlist serverseitig durch, und der lokale Upload-Pfad nutzt für PDF-OCR dieselbe Funktion wie die Datei-Connectoren (O-030/O-031/O-044). CSV ist weiterhin nicht als belastbarer eigener Dokumenttyp umgesetzt.
2. Die COBOL-XREF ist für Copybooks und REPLACING vorhanden; der quellenweite Feldindex ist mit eigenen Copybook-Entities, verschachtelten COPYs und gezielter USES-Nachauflösung vollständig umgesetzt und geprüft.
3. JCL bleibt in v1 textbasiert. Ein struktureller JCL-Parser und `EXECUTES`-Kanten gehören nicht zum aktuellen v1-Umfang.
4. Der lokale Ollama-Modellname ist derzeit eine administrativ veränderbare Prozesskonfiguration und nicht vollständig request-stateless.
5. Sessions/Snapshots erfüllen die ursprünglich formulierten Sicherheitsversprechen inzwischen (O-032); Verschlüsselungsumfang für Metadaten/Feedback bleibt offen (O-033). Der Knowledge-Graph-Export ist jetzt vollständig (JSON/Cypher/CSV/GraphML, O-034); die Übersicht selbst ist zusätzlich gegen unbegrenztes Wachstum bei großen Beständen abgesichert (O-053).
6. Neben der lokalen Anmeldung gibt es seit O-041 einen zweiten, gleichwertigen Anmeldeweg über OpenID Connect (SSO), aktiv sobald ein Kunde `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` setzt.
7. Formale Last-, BITV- und Marken-/Kontrastabnahmen stehen noch aus.

## 3. Funktionale Anforderungen

### 3.1 Identität, Teams und Berechtigungen

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-001 | Lokale Anmeldung mit Argon2id-Passworthashes, signiertem HTTP-only Session-Cookie und verpflichtendem Passwortwechsel beim Bootstrap. | ERFÜLLT |
| DOC-F-002 | Benutzerverwaltung für Superuser/Admin sowie Projekt- und Team-Mitgliedschaften. Neue Benutzer erhalten keine impliziten Projektzugriffe. | ERFÜLLT |
| DOC-F-003 | Projektrollen `admin` und `member`; Backend-Prüfung für Projekte, Quellen, Jobs, Graphen, Chat und Exporte. | ERFÜLLT |
| DOC-F-004 | Rate-Limiting, Login-Fehlversuche, Sperren, Reset- und Entsperrfunktionen. | ERFÜLLT |
| DOC-F-005 | Kein Default-Geheimnis für Sessions; Betrieb ohne gesetzten Session-Schlüssel wird abgelehnt. | ERFÜLLT |
| DOC-F-006 | Connector-Geheimnisse/Tokens werden verschlüsselt gespeichert; Diagnoseausgaben bereinigen Geheimnisse. | ERFÜLLT |
| DOC-F-007 | Zweiter, gleichwertiger Anmeldeweg über OpenID Connect (SSO) für Kunden mit zentralem Identitätsprovider, neben der lokalen Anmeldung. | ERFÜLLT – O-041 (05.09.2026): Authorization-Code-Flow (`backend/core/oidc.py`), aktiv sobald `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` gesetzt sind. ID-Token-Prüfung über JWKS (Signatur, Issuer, Audience, Ablauf, Nonce, `algorithms=["RS256"]` gegen Alg-Confusion). JIT-Provisioning ausschließlich über den `sub`-Claim, kein automatisches Verknüpfen über die E-Mail-Adresse (`docs/ENTSCHEIDUNGEN.md` E-12). SSO-Konten haben kein lokales Passwort (`password_hash` nullable); `POST /users/{id}/reset-password` lehnt sie ab. *(Nachgetragen 05.09.2026 — in v1.2–v1.4 nicht formuliert.)* |

### 3.2 Quellen und Ingestion

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-010 | GitHub, GitLab, Bitbucket sowie generische Git-Repositories; Branch-Auswahl, bare Mirror, Worktree, Sparse-/Blob-Filter und inkrementelle Dateisynchronisation. | ERFÜLLT; die optionale Performance-Evaluation für sehr große Repositories ist unter „Noch zu evaluieren“ (O-006) dokumentiert und kein aktueller Release-Blocker. |
| DOC-F-019 | Branch-isolierte Verarbeitung, Wiederaufnahme über Hash-/Scan-Zustand und Konfliktbehandlung bei parallelen Quellen. | ERFÜLLT |
| DOC-F-011 | Confluence- und Jira-Anbindung als read-only Quellen; Seiten, Anhänge und relevante Inhalte werden synchronisiert. | ERFÜLLT |
| DOC-F-012 | WebDAV, lokale Ordner und FolderWatch als read-only Quellen. | ERFÜLLT |
| DOC-F-013 | Upload bzw. Verarbeitung von PDF, Markdown und Text; Connectoren verarbeiten zusätzlich DOC/DOCX. | ERFÜLLT – seit O-044 (05.09.2026) verarbeitet auch der lokale Upload-Pfad DOC/DOCX, nicht mehr nur die Datei-Connectoren. |
| DOC-F-014 | OCR-Fallback für gescannte PDFs bei den Datei-Connectoren. | ERFÜLLT – O-031 (03.09.2026) behoben: neue geteilte Funktion `connectors/folder.py::extract_pdf_pages`, von Folder/WebDAV UND dem lokalen Upload-Pfad (`parser/tasks/document.py`) gemeinsam genutzt; OCR-Fallback greift jetzt überall. |
| DOC-F-015 | Quellen werden über Projektgrenzen hinweg nicht unberechtigt sichtbar; alle Quellen bleiben im jeweiligen Projektkontext. | ERFÜLLT |
| DOC-F-016 | Erweiterungen und Connector-Typen werden konfigurierbar verarbeitet; unbekannte Dateien werden nicht als fachlich unterstützte Dokumente behauptet. | ERFÜLLT – O-030 (03.09.2026) behoben: serverseitige Allowlist `_ALLOWED_UPLOAD_EXTENSIONS` in `backend/api/knowledge_sources.py`, deckungsgleich mit der UI-Auswahl; seit O-044 (05.09.2026) `.pdf`/`.md`/`.txt`/`.docx`/`.doc`. |
| DOC-F-017 | Ingestion ist idempotent, wiederaufnehmbar und erzeugt nachvollziehbare Source-/Scan-Zustände. | ERFÜLLT |
| DOC-F-018 | Unterstützte Dokumenttypen umfassen PDF, TXT, Markdown und DOC/DOCX; CSV ist nicht als belastbarer eigener Parser/Dokumenttyp umgesetzt. | TEILWEISE – CSV aus v1.2 ist als offene Produktentscheidung zu behandeln (O-007); PDF/MD/TXT/DOCX/DOC sind seit O-044 (05.09.2026) für lokale Uploads UND Connectoren einheitlich verfügbar. |

### 3.3 COBOL-Analyse und Cross-References

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-020 | IBM Enterprise COBOL/z/OS mit Fixed- und Free-Format, Fortsetzungen und toleranter Verarbeitung typischer Legacy-Varianten. | ERFÜLLT |
| DOC-F-021 | Eigener Analyse-/Orchestrierungspfad mit ANTLR-Brücke, strukturierten Entitäten und stabiler Fallback-Verarbeitung bei fehlerhaften Quellen. | ERFÜLLT |
| DOC-F-022 | Copybook-Auflösung inklusive Suchindex, Namensauflösung, `REPLACING` und expliziten unresolved/dynamic Ergebnissen. | ERFÜLLT – inklusive verschachtelter COPYs, vollständiger REPLACING-Anwendung und expliziter unresolved/dynamic Ergebnisse. |
| DOC-F-023 | Erkennung von Programmen, Copybooks, Sections, Paragraphs, Data Items, File Descriptions sowie SQL-Blöcken/-Tabellen. | ERFÜLLT |
| DOC-F-024 | Beziehungen für `CALL`, `PERFORM`, `GOTO`, `COPY`, `READS`, `WRITES`, `USES` und Definitionen. | ERFÜLLT |
| DOC-F-025 | Feldverwendung und Feld-XREF über lokale und eingebundene Copybook-Strukturen. | ERFÜLLT – lokale und quellenweite Copybook-Felder werden ohne Text-Expansion in USES-Kanten überführt und pfadgenau nachaufgelöst. |
| DOC-F-026 | JCL-Unterstützung als optionaler Umfang. | GEÄNDERT – v1 indexiert JCL textuell; ein struktureller JCL-Parser ist nicht Bestandteil des aktuellen v1. |
| DOC-F-027 | Embedded SQL wird als eigener Analyseblock verarbeitet; SQL-Tabellen/Verwendungen werden in den Analysekontext übernommen. | ERFÜLLT |
| DOC-F-028 | Zeichensätze ASCII/UTF-8 im aktuellen v1; EBCDIC bleibt späterer Umfang. | GEÄNDERT – EBCDIC ist v2 und nicht als v1-Funktion zu versprechen. |
| DOC-F-029 | Copybooks können aus demselben Repository/Quellenverbund aufgelöst werden. | ERFÜLLT |
| DOC-F-030 | Strukturierte Entitätstypen: `program`, `copybook`, `section`, `paragraph`, `data_item`, `file_fd`, `sql_table`, `sql_block`. | ERFÜLLT |
| DOC-F-031 | Kandidaten für Dead Code/ungenutzte Artefakte. | OFFEN – im aktuellen Produkt gibt es dafür keine belastbare fachliche Funktion; als KANN-Anforderung zurückgestellt. |
| DOC-F-032 | Unaufgelöste und dynamische Referenzen werden explizit markiert und nicht als sichere Kanten ausgegeben. | ERFÜLLT |
| DOC-F-033 | Golden Corpus, Parser-Fixtures und Tests für Fixed/Free Format, COPY, SQL und Legacy-Fälle. | ERFÜLLT – 16 Fixture/Golden-Paare sind vorhanden; die Testausführung ist in CI vorgesehen. |
| DOC-F-034 | Parser- und Datenmodelländerungen bleiben zwischen Backend und Parser synchron. | ERFÜLLT – Byte-Gleichheit der duplizierten Modelle wird in CI geprüft. |

### 3.4 Suche, RAG und externe Werkzeuge

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-040 | Lokale Embeddings über BGE-M3/Ollama mit 1024 Dimensionen und pgvector/HNSW-Index. | ERFÜLLT |
| DOC-F-041 | Semantische Suche und RAG mit Projekt-/Quellenkontext. | ERFÜLLT |
| DOC-F-042 | Graph-gestützte Retrieval-Erweiterung über relevante COPY-/CALL-Beziehungen. | ERFÜLLT |
| DOC-F-043 | Globale Suche über Projekte/Quellen/Entitäten mit begrenzten Ergebnismengen und Nachladen. | ERFÜLLT |
| DOC-F-044 | Nachvollziehbare Quellen-/Chunk-Bezüge in Chat-Antworten und Code-/Dokumentkontext. | ERFÜLLT |
| DOC-F-049 | MCP-Anbindung für Confluence/Jira-Werkzeuge sowie MCP-basierte Recherche im Chat. | ERFÜLLT – Tool-Aufrufe funktionieren; Toolname und bereinigte Argumente werden je Chat-Turn strukturiert, zeitlich begrenzt und admin-only auditierbar aufgezeichnet (O-022). |
| DOC-F-045 | Lokales Ollama als Standard; Cloud-Provider sind standardmäßig deaktiviert und müssen explizit freigeschaltet werden. | ERFÜLLT |
| DOC-F-046 | Provider-, Modell-, Base-URL- und Request-Optionen können am Chat übergeben werden; Cloud-Nutzung ist serverseitig gesperrt, wenn nicht erlaubt. | ERFÜLLT |
| DOC-F-047 | Cloud-Anfragen werden nur bei aktivierter Konfiguration und mit expliziter Providerwahl ausgeführt. | ERFÜLLT |
| DOC-F-048 | Keine unbeabsichtigte gemeinsame Chat-/Provider-State-Nutzung zwischen Requests. | TEILWEISE – Chatparameter sind requestbezogen; der lokale Ollama-Modellname kann über Admin-`/model-info` weiterhin global im Prozess geändert werden (O-035). |
| DOC-F-050 | Analyseunterstützung wird als nicht bindende technische Unterstützung gekennzeichnet; Quellen und Unsicherheiten bleiben sichtbar. | ERFÜLLT |

### 3.5 Workspace, Graphen und Navigation

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-060 | Workspace mit Chat, Code-/Dokumentansicht und Web-/Quellenansicht. | ERFÜLLT |
| DOC-F-061 | Monaco-Codeansicht mit Syntaxdarstellung, Zeilenbezug und Navigation. | ERFÜLLT |
| DOC-F-062 | Fixierbare Ansichten, Fokusobjekte, Referenzsprünge und kontextbezogene Chat-Anfragen. | ERFÜLLT |
| DOC-F-063 | Sitzungen, Snapshots und Wiederherstellung des Workspace-Zustands. | ERFÜLLT – O-032 (03.09.2026) behoben: einheitliche Zugriffsregel `owner_id == user.id or is_public` (`_session_accessible`, `backend/api/chat.py`) jetzt auf allen Snapshot-/Lese-/Fortsetzen-Routen durchgesetzt, siehe DOC-F-070/DOC-F-071. |
| DOC-F-064 | Ein bis vier Ansichten sowie responsive Desktop-/Mobile-Layouts. | ERFÜLLT – O-021 hat `split` (2 Panels) und `4-grid` (Kreuzgriff) mit der Maus verstellbar gemacht; O-029 (03.09.2026) hat zusätzlich zwei ziehbare Teiler für `3-col` ergänzt. Alle vier Layoutmodi sind damit per Maus verstellbar. |
| DOC-F-065 | Datei-/Entitätsnavigation und Projektkontext in der Seitenleiste. | ERFÜLLT – O-036 (05.09.2026) behoben: Chat-Verlauf und Datei-Baum einer aufgeklappten Wissensquelle rendern jetzt gefenstert (`@tanstack/react-virtual`, `components/sidebar/VirtualizedSessionList.tsx`/`FileTreeList.tsx`) statt vollständig, siehe NF-011. |
| DOC-F-066 | Callgraph für 0–3 Hops mit CALL/PERFORM/GOTO/COPY, Begrenzung, Filtern, unresolved/dynamic Darstellung und JSON/CSV/GraphML-Export. | ERFÜLLT – JCL/`EXECUTES` ist wegen DOC-F-026 nicht Teil des aktuellen v1-Callgraphs. |
| DOC-F-067 | Callgraph- und Analysezugriffe respektieren Projektberechtigungen. | ERFÜLLT |
| DOC-F-068 | Klickbare Code-Entitäten und Rücksprünge zwischen Entität, Datei und Referenz. | ERFÜLLT – seit 02.09.2026 zusätzlich per Rechtsklick-Kontextmenü auf Code-Entitäten in Monaco (`SplitPaneWorkspace.tsx`, Commit `b45d1cf`). |
| DOC-F-069 | Zeilenreferenz/Glyph in Monaco öffnet oder fokussiert die zugehörige Stelle und kann für den Chat verwendet werden. | ERFÜLLT – O-019 (kanonischer Fokus-Snapshot pro Chat-Turn) sowie die direkten Folgefixes `e75c2a4`/`ff4c864` (02.09.2026) lassen den fokussierten Code-Objekt/Datei-Kontext jetzt im Chat-Request ankommen (`backend/api/chat.py::_find_pinned_chunks`) und in der Chat-Nachricht sichtbar werden (`ChatView.tsx`). |
| DOC-F-070 | Sitzungen besitzen UUIDs; Teilen ist optional und soll nur explizit öffentliche Sitzungen sichtbar machen. | ERFÜLLT – O-032 (03.09.2026) behoben: neuer `POST /chat/sessions/{id}/share`-Endpunkt setzt `is_public` erst nach explizitem "Chat teilen"; die `by-uuid`-Leserouten prüfen `is_public`/Owner jetzt (`_session_accessible`, `backend/api/chat.py`). |
| DOC-F-071 | Workspace-Snapshot kann gespeichert und wiederhergestellt werden. | ERFÜLLT – O-032 (03.09.2026) behoben: `PATCH /chat/sessions/{id}/snapshot` verlangt jetzt Authentifizierung und gated auf Owner/`is_public`. |
| DOC-F-072 | Deutsch/Englisch, Themes und responsive Darstellung. | ERFÜLLT |
| DOC-F-073 | Persistente Chatdaten mit Verschlüsselung sensibler Inhalte und nachvollziehbaren Quellen/Feedbackdaten. | TEILWEISE – Nachrichteninhalt (`ChatMessage.content`) ist als `EncryptedString` verschlüsselt; `metadata_json` (u. a. Refs) und `feedback` sind weiterhin unverschlüsselt (O-033). |
| DOC-F-080 | Automatische Aufbereitung/Generierung von Dokumenten in mehreren Schritten mit Review-/Freigabestatus. | ERFÜLLT – Entwurf, Review und Approve/Reject sind vorhanden. |
| DOC-F-081 | Manuelles Verknüpfen und Bewerten von Wissen/Quellen. | ERFÜLLT |
| DOC-F-082 | Knowledge Graph mit Fokus, Übersicht und kontextbezogenen Links. | ERFÜLLT – O-053 (05.09.2026): `GET /graph/focus` (Ein-Hop-Nachbarschaft einer Entity, existierte im Backend bereits) ist jetzt tatsächlich im Frontend angebunden ("Nur Nachbarschaft laden") — lädt bei einem Entity-Knoten die echte, ungekappte Nachbarschaft direkt aus der DB, unabhängig vom Zustand der Übersicht. |
| DOC-F-083 | Neutrale Graph-Ausgabe für JSON/CSV/GraphML; keine Neo4j-Laufzeitabhängigkeit. | ERFÜLLT – O-034 (03.09.2026) behoben: neuer Endpunkt `GET /graph/export?format=csv\|graphml` (analog zu `/callgraph/export`), ruft intern `get_graph()` und erbt dieselbe Sichtbarkeitsprüfung. Legacy-`/export/neo4j` bleibt bestehen (weiterhin in Nutzung, keine Migrationsentscheidung getroffen), kein Neo4j-Service für den Betrieb erforderlich. |
| DOC-F-090 | Admin kann eine bestehende Git-Wissensquelle vollständig neu analysieren (Reindex), ohne sie neu anzulegen und ohne bestehende Verknüpfungen zu verlieren. | ERFÜLLT – `POST /knowledge-sources/{id}/reindex` (admin-only, Commit `46c0edf`, 02.09.2026); nur für Git-Quellen, blockiert bei bereits laufender Analyse. *(Nachgetragen 03.09.2026 – in v1.2/v1.3 nicht formuliert.)* |
| DOC-F-091 | Admin kann einen laufenden Job (Quellen-Sync, Link-Builder u. a.) aktiv abbrechen, nicht nur fehlgeschlagene erneut anstoßen oder abgeschlossene entfernen. | ERFÜLLT – `POST /jobs/{kind}/{id}/stop` (admin-only, Commit `d585e16`, 02.09.2026), storniert den DB-Zustand und widerruft den Celery-Task. Erweiterung zu DOC-NF-014. *(Nachgetragen 03.09.2026 – in v1.2/v1.3 nicht formuliert.)* |
| DOC-F-092 | Eine Chat-Session kann auch entstehen, sobald mehrere Views geöffnet werden, ohne dass der Chat je benutzt wurde — vorher gab es ohne Chat-Nachricht keine speicherbare Sitzung. | ERFÜLLT – O-038 (03.09.2026): neuer Endpunkt `POST /chat/sessions` legt eine Sitzung ohne Chat-Nachricht an; Speicher-Icon in der Header-Bar (`GlobalSearch.tsx`), sichtbar sobald mindestens zwei Panels offen sind und der Chat leer ist. Folgefix am selben Tag behebt zwei Konsistenzlücken (erneutes Klicken legte fälschlich eine zweite Sitzung an; Sidebar-Cache wurde nach Autosave nicht synchronisiert). *(Nachgetragen 05.09.2026 – in v1.2–v1.4 nicht formuliert.)* |

## 4. Nichtfunktionale Anforderungen

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-NF-001 | On-premise/lokaler Betrieb mit lokalem LLM als Standard. | ERFÜLLT |
| DOC-NF-002 | Offline-Bundle für Betrieb ohne externe Netzwerkabhängigkeit. | ERFÜLLT – Offline-Compose und zugehörige Skripte sind vorhanden. |
| DOC-NF-003 | Open-Source-Clearing, Lizenz-Allowlist und nachvollziehbare Abhängigkeiten. | ERFÜLLT – die Clearing-Dokumentation und CI-Prüfungen sind vorhanden; Modell-/Basisimage-Freigaben bleiben Betriebsverantwortung. |
| DOC-NF-004 | Resumierbare, idempotente und fehlertolerante Verarbeitung auch für große Quellen. | TEILWEISE – Mechanismen sind implementiert; formale Abnahme mit repräsentativem DRV-Corpus steht aus. |
| DOC-NF-005 | Verschlüsselung sensibler Inhalte at rest. | ERFÜLLT für Nachrichteninhalt, Dokument-Chunks und Connector-Tokens; technische Metadaten und JSON-Felder sind nicht pauschal verschlüsselt. |
| DOC-NF-006 | Konsistentes Fujitsu-orientiertes Designsystem mit responsiver Nutzung. | TEILWEISE – Designsystem ist umgesetzt; formale Kontrast-/Markenfreigabe steht aus (O-003). |
| DOC-NF-007 | CI prüft Frontend, Backend, Parser, Golden Corpus, Typen und Lizenzen. | ERFÜLLT – CI deckt diese Prüfungen ab; das CI-Redis-Image ist von der produktiven Valkey-Konfiguration abweichend. |
| DOC-NF-008 | Backend- und Parser-Datenmodelle dürfen nicht auseinanderlaufen. | ERFÜLLT – die synchron gehaltenen Modelle werden automatisiert verglichen. |
| DOC-NF-009 | KI-Ausgaben werden mit Quellen-/Unsicherheitshinweisen als Analysehilfe kenntlich gemacht. | ERFÜLLT – Quellen werden im Chat-Kontext eingefordert und dargestellt; eine fachliche Wahrheitsgarantie ist ausdrücklich nicht Bestandteil. |
| DOC-NF-010 | Skalierbare Suche/Graph-Abfragen mit HNSW und begrenzten Ergebnismengen. | TEILWEISE – HNSW und Suche-Limits sind implementiert; die Knowledge-Graph-Übersicht (`GET /graph`) hat seit O-053 (05.09.2026) zusätzlich einen konfigurierbaren Deckel (`KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES`, Default 2000, am dichtesten verlinkte Knoten zuerst) statt vorher unbegrenzt jede Entity/jeden Chunk zu laden; formaler Lasttest mit einem repräsentativen Bestand steht weiterhin aus (O-001). |
| DOC-NF-011 | Große Mengen werden durch Server-Limits, Pagination oder Virtualisierung beherrscht. | ERFÜLLT für die identifizierten Risikofälle – Suche besitzt Limits/Nachladen; Chat-Verlauf und Datei-Baum in der Seitenleiste rendern seit O-036 (05.09.2026) gefenstert (`@tanstack/react-virtual`) statt vollständig; die Knowledge-Graph-Übersicht ist seit O-053 serverseitig gedeckelt. Eine vollständige Durchsicht aller Listen im Produkt hat nicht stattgefunden. |
| DOC-NF-012 | BITV-/Barrierefreiheitsanforderungen und automatisierte UI-Prüfungen. | TEILWEISE – automatisierte axe-Basis ist vorhanden; formale BITV-Abnahme steht aus (O-002). |
| DOC-NF-013 | Alle externen Quellsysteme werden strikt read-only verwendet. | ERFÜLLT |
| DOC-NF-014 | Job Center zeigt laufende/fehlgeschlagene Prozesse; fehlgeschlagene Jobs können nachvollziehbar fortgesetzt werden. | ERFÜLLT – Verlauf bleibt sichtbar; fehlgeschlagene Jobs können fortgesetzt werden, Admins können unterstützte Jobs aus der UI neu anstoßen. |

## 5. Bewusst nicht als aktuelle v1-Funktion zu führen

Die folgenden Punkte aus bzw. im Umfeld der v1.2-Fassung dürfen im aktuellen Katalog nicht als geliefert erscheinen:

- struktureller JCL-Parser und `EXECUTES`-Kanten;
- EBCDIC-Verarbeitung;
- belastbare Dead-Code-Kandidaten als Produktfunktion;
- CSV als vollständig unterstützter Dokumenttyp im Upload;
- formale Performance-, BITV- und Marken-/Kontrastabnahme.

Der neutrale CSV/GraphML-Export des Knowledge Graphs war bis 03.09.2026 hier
geführt und ist seit O-034 geliefert (siehe DOC-F-083).

Der fehlende Neo4j-Service ist dagegen kein Architekturfehler: Für den laufenden Betrieb wird keine Neo4j-Datenbank benötigt. Der noch vorhandene Legacy-Endpunkt ist lediglich als technische Kompatibilität zu dokumentieren oder später zu entfernen.

## 6. Offene Abnahmepunkte

Für eine nächste verbindliche Version sind mindestens folgende Punkte zu entscheiden bzw. abzunehmen:

1. CSV-Anforderung als offene Produktentscheidung (O-007) — Upload-Allowlist/OCR sind seit O-030/O-031/O-044 einheitlich (PDF/MD/TXT/DOCX/DOC, mit OCR-Fallback für alle Wege).
2. Verschlüsselungsumfang für Chat-Metadaten/Feedback bleibt offen (O-033) — Session-/Snapshot-Zugriffskontrolle ist seit O-032 (03.09.2026) behoben.
3. Umgang mit dem Legacy-Neo4j-Cypher-Endpunkt (`/graph/export/neo4j`) — bewusst nicht entfernt, weiterhin in Nutzung, keine Migrationsentscheidung getroffen. Der neutrale CSV/GraphML-Export ist seit O-034 geliefert.
4. Lasttest mit repräsentativem DRV-COBOL (O-001); die optionale Git-Performance-Evaluation ist unter O-006 dokumentiert. O-053 (05.09.2026) ergänzt einen strukturellen Deckel für die Knowledge-Graph-Übersicht als Sicherheitsnetz, ersetzt aber nicht den formalen Lasttest an echten Datenmengen.
5. BITV-Abnahme, Farbkontrast und Markenfreigabe (O-002/O-003).
6. SSO/OIDC (O-041, 05.09.2026) ist gegen selbst signierte Test-Tokens verifiziert (`backend/tests/test_oidc.py`, eigenes RSA-Schlüsselpaar/JWKS), aber noch nicht gegen einen echten Kunden-Identitätsprovider erprobt — braucht vor dem ersten produktiven SSO-Einsatz einen echten Test-IdP.
7. Prozessglobale Ollama-Modellwahl über `/model-info` (O-035).

## 7. Nachweis und Teststand

Der Abgleich wurde gegen den Quellcode und die aktuelle Projektdokumentation durchgeführt. Stand 05.09.2026 (Commit `925a605`), Testläufe gegen den laufenden Docker-Compose-Stack: Frontend **84 von 84 Tests** (18 Testdateien) grün, `tsc --noEmit` und ESLint ohne Fehler, Produktions-Build erfolgreich. Backend **177 von 180 Tests** grün (3 vorbestehende, unabhängige Fehlschläge in `test_chat_llm_provider_guard.py`, verursacht durch `ALLOW_CLOUD_LLM=true` in dieser lokalen Umgebung). Parser **201 von 213 Tests** grün (12 vorbestehende, umgebungsbedingte `[trio]`-Fehlschläge, reproduzierbar auf unverändertem Code).

Relevante Nachweise liegen insbesondere in:

- `README.md`
- `docs/OFFENE_ENTWICKLUNGSPUNKTE.md`
- `docs/IMPLEMENTIERUNGSPLAN.md`
- `docs/ACCESS_CONTROL.md`
- `docs/OSS-CLEARING.md`
- `backend/api/`, `backend/services/`, `parser/cobol/`, `parser/connectors/` und `frontend/components/`
