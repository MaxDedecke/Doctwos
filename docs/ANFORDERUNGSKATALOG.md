# Doctus – Anforderungskatalog v1.3

**Abgleich mit der Software: 02.09.2026**  
**Software-Ground-Truth:** Repository `Doctwos`, Commit `fdfb906` vom 01.09.2026  
**Ausgangsdokument:** `Doctus_Anforderungskonzept.pdf`, Version 1.2, Stand 31.07.2026

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

1. Uploads sind nicht einheitlich: Die UI bietet PDF/Markdown/Text an; DOC/DOCX und OCR sind bei Connectoren vorhanden, bei lokalen Uploads aber nicht vollständig. CSV ist nicht als belastbarer eigener Dokumenttyp umgesetzt.
2. Die COBOL-XREF ist für Copybooks und REPLACING vorhanden, der vollständige quellübergreifende Feldindex ist noch offen.
3. JCL bleibt in v1 textbasiert. Ein struktureller JCL-Parser und `EXECUTES`-Kanten gehören nicht zum aktuellen v1-Umfang.
4. Der lokale Ollama-Modellname ist derzeit eine administrativ veränderbare Prozesskonfiguration und nicht vollständig request-stateless.
5. Sessions/Snapshots und Knowledge-Graph-Export sind funktional vorhanden, erfüllen die ursprünglich formulierten Sicherheits-/Exportversprechen aber nur teilweise.
6. Formale Last-, BITV- und Marken-/Kontrastabnahmen stehen noch aus.

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

### 3.2 Quellen und Ingestion

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-010 | GitHub, GitLab, Bitbucket sowie generische Git-Repositories; Branch-Auswahl, bare Mirror, Worktree, Sparse-/Blob-Filter und inkrementelle Dateisynchronisation. | ERFÜLLT; die optionale Performance-Evaluation für sehr große Repositories ist unter „Noch zu evaluieren“ (O-006) dokumentiert und kein aktueller Release-Blocker. |
| DOC-F-019 | Branch-isolierte Verarbeitung, Wiederaufnahme über Hash-/Scan-Zustand und Konfliktbehandlung bei parallelen Quellen. | ERFÜLLT |
| DOC-F-011 | Confluence- und Jira-Anbindung als read-only Quellen; Seiten, Anhänge und relevante Inhalte werden synchronisiert. | ERFÜLLT |
| DOC-F-012 | WebDAV, lokale Ordner und FolderWatch als read-only Quellen. | ERFÜLLT |
| DOC-F-013 | Upload bzw. Verarbeitung von PDF, Markdown und Text; Connectoren verarbeiten zusätzlich DOC/DOCX. | ERFÜLLT für die tatsächlich angebotenen/unterstützten Wege. |
| DOC-F-014 | OCR-Fallback für gescannte PDFs bei den Datei-Connectoren. | TEILWEISE – bei Folder/WebDAV ist OCR vorhanden; der lokale Upload-Pfad bricht bei PDF ohne extrahierbaren Text ab. |
| DOC-F-015 | Quellen werden über Projektgrenzen hinweg nicht unberechtigt sichtbar; alle Quellen bleiben im jeweiligen Projektkontext. | ERFÜLLT |
| DOC-F-016 | Erweiterungen und Connector-Typen werden konfigurierbar verarbeitet; unbekannte Dateien werden nicht als fachlich unterstützte Dokumente behauptet. | TEILWEISE – der Upload-Endpunkt besitzt keine strikte Allowlist; die UI begrenzt die Auswahl auf `.pdf`, `.md`, `.txt`. |
| DOC-F-017 | Ingestion ist idempotent, wiederaufnehmbar und erzeugt nachvollziehbare Source-/Scan-Zustände. | ERFÜLLT |
| DOC-F-018 | Unterstützte Dokumenttypen umfassen PDF, TXT, Markdown und DOC/DOCX; CSV ist nicht als belastbarer eigener Parser/Dokumenttyp umgesetzt. | TEILWEISE – CSV aus v1.2 ist als offene Produktentscheidung zu behandeln (O-007); lokale Uploads bieten derzeit nur PDF/MD/TXT an. |

### 3.3 COBOL-Analyse und Cross-References

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-020 | IBM Enterprise COBOL/z/OS mit Fixed- und Free-Format, Fortsetzungen und toleranter Verarbeitung typischer Legacy-Varianten. | ERFÜLLT |
| DOC-F-021 | Eigener Analyse-/Orchestrierungspfad mit ANTLR-Brücke, strukturierten Entitäten und stabiler Fallback-Verarbeitung bei fehlerhaften Quellen. | ERFÜLLT |
| DOC-F-022 | Copybook-Auflösung inklusive Suchindex, Namensauflösung, `REPLACING` und expliziten unresolved/dynamic Ergebnissen. | TEILWEISE – Copybook-Auflösung ist vorhanden; der vollständige Feldindex über alle Copybook-Grenzen ist noch nicht abgeschlossen (O-009). |
| DOC-F-023 | Erkennung von Programmen, Copybooks, Sections, Paragraphs, Data Items, File Descriptions sowie SQL-Blöcken/-Tabellen. | ERFÜLLT |
| DOC-F-024 | Beziehungen für `CALL`, `PERFORM`, `GOTO`, `COPY`, `READS`, `WRITES`, `USES` und Definitionen. | ERFÜLLT |
| DOC-F-025 | Feldverwendung und Feld-XREF über lokale und eingebundene Copybook-Strukturen. | TEILWEISE – lokale Analyse und Copybook-Vererbung sind implementiert; die quellweite Vollständigkeit ist offen (O-009). |
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
| DOC-F-048 | Keine unbeabsichtigte gemeinsame Chat-/Provider-State-Nutzung zwischen Requests. | TEILWEISE – Chatparameter sind requestbezogen; der lokale Ollama-Modellname kann über Admin-`/model-info` global im Prozess geändert werden. |
| DOC-F-050 | Analyseunterstützung wird als nicht bindende technische Unterstützung gekennzeichnet; Quellen und Unsicherheiten bleiben sichtbar. | ERFÜLLT |

### 3.5 Workspace, Graphen und Navigation

| ID | Aktuelle Anforderung / Softwarestand | Status |
|---|---|---|
| DOC-F-060 | Workspace mit Chat, Code-/Dokumentansicht und Web-/Quellenansicht. | ERFÜLLT |
| DOC-F-061 | Monaco-Codeansicht mit Syntaxdarstellung, Zeilenbezug und Navigation. | ERFÜLLT |
| DOC-F-062 | Fixierbare Ansichten, Fokusobjekte, Referenzsprünge und kontextbezogene Chat-Anfragen. | ERFÜLLT |
| DOC-F-063 | Sitzungen, Snapshots und Wiederherstellung des Workspace-Zustands. | TEILWEISE – Funktion vorhanden; Snapshot-Endpunkte und Deep Links benötigen noch eine vollständige Prüfung der Sichtbarkeits-/Berechtigungsregeln. |
| DOC-F-064 | Ein bis vier Ansichten sowie responsive Desktop-/Mobile-Layouts. | ERFÜLLT – das 1–4-Layout existiert; frei mit der Maus veränderbare Teiler für alle Layouts sind noch offen (O-021). |
| DOC-F-065 | Datei-/Entitätsnavigation und Projektkontext in der Seitenleiste. | ERFÜLLT – große Listen sind funktional, aber noch nicht durchgängig virtualisiert/paginiert (siehe NF-011). |
| DOC-F-066 | Callgraph für 0–3 Hops mit CALL/PERFORM/GOTO/COPY, Begrenzung, Filtern, unresolved/dynamic Darstellung und JSON/CSV/GraphML-Export. | ERFÜLLT – JCL/`EXECUTES` ist wegen DOC-F-026 nicht Teil des aktuellen v1-Callgraphs. |
| DOC-F-067 | Callgraph- und Analysezugriffe respektieren Projektberechtigungen. | ERFÜLLT |
| DOC-F-068 | Klickbare Code-Entitäten und Rücksprünge zwischen Entität, Datei und Referenz. | ERFÜLLT |
| DOC-F-069 | Zeilenreferenz/Glyph in Monaco öffnet oder fokussiert die zugehörige Stelle und kann für den Chat verwendet werden. | TEILWEISE – die Zeilenreferenz funktioniert; die Fokus-Synchronisierung bei LLM-Anfragen ist noch eine offene Nacharbeit (O-019). |
| DOC-F-070 | Sitzungen besitzen UUIDs; Teilen ist optional und soll nur explizit öffentliche Sitzungen sichtbar machen. | TEILWEISE – UUID/Public-Felder und Teilen existieren; die Zugriffskontrolle der UUID-/Snapshot-Routen muss für dieses Versprechen nachgeschärft bzw. formal abgenommen werden. |
| DOC-F-071 | Workspace-Snapshot kann gespeichert und wiederhergestellt werden. | TEILWEISE – umgesetzt; Snapshot-Inhalt liegt als JSON vor und die Zugriffskontrolle ist noch nicht vollständig dokumentiert/abgenommen. |
| DOC-F-072 | Deutsch/Englisch, Themes und responsive Darstellung. | ERFÜLLT |
| DOC-F-073 | Persistente Chatdaten mit Verschlüsselung sensibler Inhalte und nachvollziehbaren Quellen/Feedbackdaten. | TEILWEISE – Nachrichteninhalt ist verschlüsselt; Quellen-/Metadaten-/Feedback-JSON und Workspace-Snapshots sind nicht vollständig verschlüsselt. |
| DOC-F-080 | Automatische Aufbereitung/Generierung von Dokumenten in mehreren Schritten mit Review-/Freigabestatus. | ERFÜLLT – Entwurf, Review und Approve/Reject sind vorhanden. |
| DOC-F-081 | Manuelles Verknüpfen und Bewerten von Wissen/Quellen. | ERFÜLLT |
| DOC-F-082 | Knowledge Graph mit Fokus, Übersicht und kontextbezogenen Links. | ERFÜLLT |
| DOC-F-083 | Neutrale Graph-Ausgabe für JSON/CSV/GraphML; keine Neo4j-Laufzeitabhängigkeit. | TEILWEISE – kein Neo4j-Service ist erforderlich; der Callgraph exportiert neutral, der Knowledge-Graph besitzt aktuell jedoch keinen vollständigen neutralen CSV/GraphML-Export und führt noch einen Legacy-`/export/neo4j`-Kompatibilitätsendpunkt. |

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
| DOC-NF-010 | Skalierbare Suche/Graph-Abfragen mit HNSW und begrenzten Ergebnismengen. | TEILWEISE – HNSW, Limits und Graph-Begrenzungen sind implementiert; formaler Lasttest steht aus (O-001). |
| DOC-NF-011 | Große Mengen werden durch Server-Limits, Pagination oder Virtualisierung beherrscht. | TEILWEISE – Suche besitzt Limits/Nachladen; mehrere Datei-/Entitätslisten liefern aktuell noch vollständige Mengen ohne durchgängige Virtualisierung. |
| DOC-NF-012 | BITV-/Barrierefreiheitsanforderungen und automatisierte UI-Prüfungen. | TEILWEISE – automatisierte axe-Basis ist vorhanden; formale BITV-Abnahme steht aus (O-002). |
| DOC-NF-013 | Alle externen Quellsysteme werden strikt read-only verwendet. | ERFÜLLT |
| DOC-NF-014 | Job Center zeigt laufende/fehlgeschlagene Prozesse; fehlgeschlagene Jobs können nachvollziehbar fortgesetzt werden. | ERFÜLLT – Verlauf bleibt sichtbar; fehlgeschlagene Jobs können fortgesetzt werden, Admins können unterstützte Jobs aus der UI neu anstoßen. |

## 5. Bewusst nicht als aktuelle v1-Funktion zu führen

Die folgenden Punkte aus bzw. im Umfeld der v1.2-Fassung dürfen im aktuellen Katalog nicht als geliefert erscheinen:

- struktureller JCL-Parser und `EXECUTES`-Kanten;
- EBCDIC-Verarbeitung;
- belastbare Dead-Code-Kandidaten als Produktfunktion;
- vollständiger quellweiter Copybook-Feldindex inklusive aller `REPLACING`-Sonderfälle;
- CSV als vollständig unterstützter Dokumenttyp im Upload;
- vollständiger neutraler CSV/GraphML-Export des Knowledge Graphs;
- formale Performance-, BITV- und Marken-/Kontrastabnahme.

Der fehlende Neo4j-Service ist dagegen kein Architekturfehler: Für den laufenden Betrieb wird keine Neo4j-Datenbank benötigt. Der noch vorhandene Legacy-Endpunkt ist lediglich als technische Kompatibilität zu dokumentieren oder später zu entfernen.

## 6. Offene Abnahmepunkte

Für eine nächste verbindliche Version sind mindestens folgende Punkte zu entscheiden bzw. abzunehmen:

1. CSV-Anforderung und einheitliche Upload-Allowlist einschließlich DOCX/OCR (O-007).
2. Vollständiger Copybook-Feldindex und USES-XREF-Volumen über den gesamten Quellbestand (O-009).
3. Session-/Snapshot-Sichtbarkeit, Public-Share-Semantik und Verschlüsselungsumfang.
4. Neutraler Knowledge-Graph-Export und Umgang mit dem Legacy-Neo4j-Endpunkt.
5. Lasttest mit repräsentativem DRV-COBOL (O-001); die optionale Git-Performance-Evaluation ist unter O-006 dokumentiert.
6. BITV-Abnahme, Farbkontrast und Markenfreigabe (O-002/O-003).
7. UI-Nacharbeiten: View-Resize, Link-Manager bei vier Views, Job-Center-Historie und LLM-Fokus-Synchronisierung (O-018–O-021).

## 7. Nachweis und Teststand

Der Abgleich wurde gegen den Quellcode und die aktuelle Projektdokumentation durchgeführt. Der Frontend-Testlauf war erfolgreich: **1 Testsuite, 8 Tests bestanden**. Der TypeScript-Check lief ohne Fehler durch. Die Parser-/Backend-Tests konnten in der vorliegenden Umgebung nicht vollständig abgenommen werden, weil die benötigte Testdatenbankverbindung nicht verfügbar war; dabei liefen die vorhandenen In-Memory-/Unit-Tests weitgehend durch, die datenbankabhängigen Tests jedoch nicht.

Relevante Nachweise liegen insbesondere in:

- `README.md`
- `docs/OFFENE_ENTWICKLUNGSPUNKTE.md`
- `docs/IMPLEMENTIERUNGSPLAN.md`
- `docs/ACCESS_CONTROL.md`
- `docs/OSS-CLEARING.md`
- `backend/api/`, `backend/services/`, `parser/cobol/`, `parser/connectors/` und `frontend/components/`
