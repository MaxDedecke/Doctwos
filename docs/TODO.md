# Doctus – priorisierte TODO-Liste

Stand: 28.09.2026

Diese Datei ist die kanonische Liste der noch offenen Arbeit. Die Reihenfolge
innerhalb einer Priorität ist zugleich die empfohlene Ausführungsreihenfolge.
`teilweise` bedeutet, dass der verbleibende Abnahmepunkt weiterhin offen ist.
Erledigte Punkte stehen nicht mehr im aktiven Backlog; ihr Nachweis bleibt in der
Git-Historie und in den verlinkten Fachunterlagen erhalten.

**MCP-Sicherheitsprüfung vom 24.09.2026:** Die zwei reproduzierten Befunde zu
Projektisolation der Wissenssuche und unbeschränkter Call-Flow-Abfrage wurden
behoben; 27 isolierte Sicherheitsprüfungen sowie 9 MCP-Regressionen bestanden.
Details: [MCP-Sicherheitsbericht](MCP_SECURITY_REVIEW_2026-09-24.md).

## P0 – abgeschlossen (Entwicklung abgeschlossen, Abnahmen laufen begleitend)

| Rang | ID | Ergebnis | Status / Abnahme |
|---:|---|---|---|
| 1 | O-271, O-301 | Durchgängigen Erkenntnis-Workflow liefern: aus Chat, Code oder Prozessschritt einen belegten Entwurf sichern und durch einen zweiten berechtigten Nutzer freigeben. | **Abgeschlossen.** Am 24.09.2026 gegen die laufende lokale API mit dem bestehenden Superuser und einem temporär angelegten, regulär angemeldeten CardDemo-Projekt-Admin geprüft: Entwurf aus `chat`, `code` und `process` jeweils 201, Selbstfreigabe 403, Freigabe durch zweiten Admin 200; Status, Beleg-Snapshot und Auditfelder lesbar. Temporäre Konten und Entwürfe entfernt. Die gesonderte UI-E2E-Abnahme entfällt auf Nutzerentscheidung. |
| 2 | O-272, O-302 | Erkenntnisstatus und Provenienz durchgängig anzeigen; Quellenänderungen erzeugen eine Review-Aufgabe. | **Umgesetzt, E2E-Abnahme offen.** `draft`, `verified` und `outdated`, Provenienz-Snapshot sowie Hochstufung belegter Erkenntnisse bei Quellenänderung sind implementiert. Widerspruch/Zurückweisung bleiben Bestandteil der fachlichen Abnahme und der Prüflisten-Weiterentwicklung. |
| 3 | O-303 | Priorisierte Prüfliste für neue Links, widersprüchliche, abgelehnte und veraltete Erkenntnisse bereitstellen. | **Umgesetzt für Erkenntnisse, E2E-Abnahme offen.** Die Prüfansicht priorisiert „erneut prüfen“, Entwürfe und freigegebene Erkenntnisse; sie nutzt den bestehenden Link-Review-Kontext. Fachlich mit einem Quellenwechsel und zwei Rollen abnehmen. |
| 4 | O-305 | COBOL-Syntax-Recovery an realen Dialektfällen stabilisieren, damit lokale Fehler nicht ganze Divisions-, Paragraphen- und Feldstrukturen vernichten. | Teilweise. Recovery-Fix für EXEC-Blöcke in DATA/COPYBOOK und mehrzeilige IDENTIFICATION-Metadaten umgesetzt und Regressionen ergänzt; Reindex der drei Bestände läuft bzw. ist beim externen RunPod-Embedding-Endpunkt wegen 404 noch nicht abnahmefähig. |
| 5 | O-309 | Java-Aufrufe über Parameter, lokale Variablen, Felder, Vererbung und Interfaces belegbar auflösen. | **Umgesetzt, Bestandsabnahme offen.** Receiver-Typen aus Parametern, lokalen Variablen/Feldern (inkl. `var`-`new`), expliziter Vererbung, Interfaces und `super`-Dispatch werden mit Ziel-Qualified-Name und Receiver-Evidenz aufgelöst. Mehrdeutige oder dynamische Ausdrücke bleiben bewusst sichtbar unaufgelöst; Regressionen decken die sicheren Fälle ab. |
| 6 | O-310 | Deklarationen und Referenzvorkommen in Java und COBOL direkt anklickbar machen; Hierarchie als begrenzte `CONTAINS`-Struktur zeigen. | Teilweise umgesetzt: Entity-Nachbarschaften liefern deklarationsfähige Ziele und einen separaten belegten Referenz-Locator; unresolved/dynamische Kanten behaupten kein Ziel. Die UI zeigt Java-Kantentypen und eine auf 32 Vorfahren begrenzte `CONTAINS`-Hierarchie. Abnahme am Zielbestand steht aus. |
| 7 | O-292 | Begrenzten, sprachneutralen Backendvertrag für die Process View bereitstellen. | **Umgesetzt, Bestandsabnahme offen.** Versionierter `/process/focus`-Vertrag mit serverseitigen Node-/Edge-Limits, sichtbarer Kürzung, Zyklen und quellennahen Locators ist vorhanden und durch Backend-Regressionen abgedeckt. |
| 8 | O-293, O-294, O-295 | COBOL- und Java-Kanten in denselben Prozessvertrag projizieren und Sicherheit, Reihenfolge sowie Unsicherheit belegen. | **Umgesetzt, Bestandsabnahme offen.** COBOL- und Java-Kanten werden projektiert; Strukturkanten bleiben ausgeschlossen, `certain`/`possible`/`unresolved`, Verzweigungen, Zyklen und nur beobachtete Reihenfolge sind im Vertrag enthalten. |
| 9 | O-299 | Workflow „Was macht dieses Element?“ von Frage bis Originalbeleg verbinden. | **Umgesetzt, fachliche E2E-Abnahme offen.** Chat-Zitate, geführte Code-/Prozessschritte sowie Java-/COBOL-Referenz-Locators öffnen die Originalquelle an der belegten Stelle. Je eine reale Java- und COBOL-Frage vollständig abnehmen. |
| 10 | O-300 | Workflow „Änderung untersuchen“ fachlich an Java und COBOL abnehmen. | Teilweise. Technischer Impact-Schnitt ist umgesetzt; Bestandsabnahme fehlt. |
| 11 | O-304 | Produktschnitt mit versionierten Java-/COBOL-Szenarien und Ground Truth messen. | Offen. Erst starten, wenn O-299 bis O-303 fachlich abnehmbar sind. |
| 12 | O-311 | COBOL-Parser darf keine doppelten `data_item`-Entities mit gleichem Source-/Varianten-/Pfad-/Qualified-Name persistieren. | **Umgesetzt.** Kollisionsfreie Qualified-Name-Disambiguierung für REDEFINES und gleichnamige Geschwister über Level-Stack und Zeilenanker umgesetzt; Defense-in-Depth-Deduplizierung in structure_persist.py ergänzt. Regressionen in test_cobol_parse.py und test_structure_persist_cobol_scoping.py; COACTUPC.cbl und COTRTUPC.cbl indizieren mit 627 bzw. 191 Entitäten fehlerfrei strukturiert. |
| 13 | O-312 | Remote-Ollama während langer Imports stabil betreiben: Modellresidenz, Admission und Verbindungsabbrüche beobachten. | **Teilabnahme 28.09.2026:** BGE-M3 ist vollständig im RunPod-VRAM resident; `:latest`-Aliasfehler in der GPU-Erkennung korrigiert und `is_gpu_accelerated('bge-m3')` im Worker mit `True` geprüft. Syncope-BGE-Reindex lief seit 09:34 UTC; letzter bekannter Stand vor der Lesesperre: 3.318/4.648 Dateien. Der Importabschluss und der endgültige Chunk-Stand wurden danach nicht abgefragt. Das 20-Minuten-Ziel war bereits beim bekannten Zwischenstand 2.180/4.648 Dateien und 16.897 Chunks verfehlt. Vier CardDemo-Chats liefen parallel, der Import blieb aktiv. Direkte GPU-Rechenauslastung und Abschlussdurchsatz bleiben offen. CardDemo unverändert. Details in [EVALRUN_1.md](EVALRUN_1.md). |
| 14 | O-314 | COBOL-Importdurchsatz gezielt optimieren. | **Umgesetzt.** Parsezeit, Chunk-Anzahl, Embedding-Batchgröße und Admission-Wartezeit je Datei werden erfasst und im Sync-Log protokolliert; Chunks großer Text-/Datenartefakte werden in bounded Fair-Batches (Standard 20) mit kooperativen Event-Loop-Yields unterteilt. Embedding-Parallelität ist standardmäßig auf die freie Admission-Batch-Kapazität (3 Slots bei Chat-Reserve) begrenzt; Abhängigkeitsauflösung (`_analysis_dependency_paths`) nutzt gezielte SQL-Joins statt speicherintensiver Python-Dictionaries. Regressionen in `test_o314_fair_batching_and_analysis_deps.py`, `test_git_connector.py` und `test_inference_admission.py`. |
| 15 | O-315 | Automatischen Link-Builder vom normalen Quellenimport entkoppeln. | **Umgesetzt.** Kein automatischer Link-Build nach Quellenimport; statische Parserkanten, Chunks und Quellenbelege bleiben ohne ihn vollständig nutzbar. Link-Build als separat start-/abbruchbarer Job im Job-Center (auch für abgebrochene Läufe wiederaufnehmbar), Deduplizierung aktiver Läufe sowie Kosten-/Umfangshinweis (`/link-recommendations/estimate` und Dialog im Link-Manager) umgesetzt. Regressionen in test_entity_links.py, test_jobs.py und test_sync_decoupled_link_builder.py. |
| 16 | O-316 | Chat-Startpfad unter Importlast verschlanken und messbar machen. | **Gestrichen / Zurückgestellt.** Durch die Chat-Reserve und das Fair-Batching aus O-314 treten Slot-Blockaden nicht mehr auf; heuristische Vorab-Klassifikation von Smalltalk/Code birgt hohes Fehlerrisiko bei geringem Hebel. Details unter „Bewusst zurückgestellt“. |
| 17 | O-317 | Datei- und Projektfokus im Eval-Retrieval erzwingen. | **Umgesetzt, Bestandsabnahme offen.** Explizite Pfade, Dateinamen und COBOL-Programm-IDs begrenzen Retrieval und lokale Repo-Werkzeuge; auch durch Graph-Erweiterung hinzugekommene fremde Dateien werden verworfen. J1/J2/C1/C4/C6 am Zielbestand erneut messen. |
| 18 | O-318 | Quellenkonsistenz vor Chat-Antwort validieren. | **Umgesetzt, Bestandsabnahme offen.** Vor dem finalen SSE-Answer werden Dateizitate und Zeilen gegen den gelieferten Recherchekontext geprüft; explizite Aufrufbehauptungen benötigen eine aufgelöste `trace_call_flow`-Kante. Bei fehlendem Beleg wird eine Index-/Parserlücke statt einer plausiblen Ersatzquelle/-kante ausgegeben. |
| 19 | O-319 | Zielpfad aus der Nutzerfrage vor dem allgemeinen Repository-Bootstrap extrahieren. | **Umgesetzt, Bestandsabnahme offen.** Backtick-Pfade, Dateinamen und Programm-IDs begrenzen den Bootstrap; zusätzlich werden explizit genannte Klassen, Methoden, Paragraphen und Templates vor dem Modelllauf als exakte, dateigebundene Indexentitäten aufgelöst. J1–J4 und C1/C3 am Zielbestand erneut messen. |
| 20 | O-320 | COBOL-Dateisuche quellenweit statt verzeichnislokal machen. | **Umgesetzt, Bestandsabnahme offen.** Rekursive Repo-Suche und Listing verwenden dieselben gefilterten, stabil sortierten Pfade. Nach einem Import ist das Scan-Journal maßgeblich für den Projekt-Dateibaum, sodass auch übersprungene/partielle Dateien sichtbar bleiben; vor dem ersten Journal-Eintrag dient der vollständige Worktree als Fallback. C6 am Zielbestand erneut messen. |
| 21 | O-321 | Exakte Entity-Auflösung vor `trace_call_flow` erzwingen. | **Umgesetzt, Bestandsabnahme offen.** Bei explizitem Datei-/Symbolfokus akzeptiert `trace_call_flow` nur zuvor exakt und dateigebunden aufgelöste Entitäten; abweichende IDs oder Namen liefern die Kandidaten samt Auflösungsstatus statt eines zufälligen Flows. C1 am Zielbestand erneut messen: `COPAUA0C.MAIN-PARA`, nie `PAUDBUNL.MAIN-PARA`. |
| 22 | O-322 | Eval-Fragen mit Ground-Truth-Datei regressionssichern. | **Umgesetzt, Bestandsabnahme offen.** Offline-Ground-Truth-Suite deckt J1–J5 und C1–C6 mit Primärdatei, Zeile, Kante und Ersatzdatei ab. Sie verhindert insbesondere, dass ein fremder Pfad mit gleichem Basename als Quelle durchgeht; die Messung am echten Zielbestand bleibt offen. |
| 23 | O-323 | Chat-SSE-Telemetrie für Eval und Betrieb vervollständigen. | **Umgesetzt.** Der SSE-Stream liefert relative monotone Meilensteine für `request_received`, ersten Tool-Call, First-Token, Tool-Ende, Modell-Ende und `message_saved`; sein Abschlussprotokoll sowie die gespeicherte Antwort enthalten Antwortzeit, First-Token, Tool-Anzahl und Retrieval-Wartezeit. |
| 24 | O-346 | Chat-Antworten bei expliziten Codepfaden und Aufrufkanten strikt an tatsächlich gelesene Zeilen und Indexkanten binden. | **Bug erneut bestätigt, Java-Fälle ergänzt (28.09.2026).** Frühere C1/C3/C6-Funde bleiben reproduziert: C1 liefert interne erfundene Kanten nach bloßer Entity-Auflösung; C3 liest weiter `PAUDBUNL.CBL` und beantwortet mit erfundenem SQL aus `COTRTUPC.CBL`, ohne Quellen. Neu: J1 beantwortet Felder aus gelesenen Zeilen, Quellenobjekt zeigt aber nur Zeile 37; J2 hat ein passendes `trace_call_flow`-Resultat, verwirft es final mit `sources=[]`; J4 findet XSLT-Templates, behauptet intern Calls, verwirft die Antwort final ebenfalls mit `sources=[]`. C6 öffnet weiterhin keinen Dateitext. Vor finaler Antwort Originalzeilen/Indexkanten abrufen und belegte Toolresultate zitieren oder präzise als Lücke kennzeichnen. Siehe [EVALRUN_1.md](EVALRUN_1.md). |
| 25 | O-347 | Explizite COBOL-Programm-ID vor dem ersten Agenten-Tool-Aufruf als Dateifokus verwenden. | **Teilweise live bestätigt; Regression offen.** C1, C2 und C4 starteten mit `COPAUA0C.cbl` im Dateifokus. C2 las die Datei vollständig und erreichte 4/6 mit korrekten Copybook-Beispielen, aber unvollständiger Gruppenabdeckung. C4 brach nach einer generischen `COPY`/`USES`-Entity-Suche ab; C5 verwendete weiter den allgemeinen Bootstrap ohne zielgerichtete Datei. Exakte Call-/Copybook-Kanten und C5-Dateifokus bleiben offen. |
| 26 | O-348 | Quellfilter in der globalen Suche auch für Code-Entities anwenden. | **Bug erneut bestätigt (28.09.2026).** `GET /search?q=COPAUA0C&project_id=1247&source_id=1005&types=entity` lieferte HTTP 200, `counts={}` und null Treffer. Der vorherige Vergleich ohne Quellenfilter lieferte 198 Entity-Treffer. Filter auf `CodeEntity.source_id` anwenden und O-193 mit Projekt- und Quellenfokus regressionssichern. |

## P1 – danach umsetzen

### MCP-Erkenntnisqualität aus dem Codex-Benchmark vom 28.09.2026

Priorisierte Ergänzungen zu O-342 bis O-345; die Rangfolge in dieser Tabelle
bestimmt die Umsetzung innerhalb dieses Pakets. Grundlage sind die archivierten
Artefakte `codex_benchmark.html` und `doctus_ab_probe/official_luna_benchmark/`
(insbesondere `raw/`, `scores.json` und die eingefrorenen Rubriken; aktuell unter
`/root`, nicht Bestandteil des Repositorys). 30 Paare: 64,7 % Rubrikpunkte ohne
gegenüber 65,1 % mit MCP, medianer gepaarter Mehraufwand 22,2 Sekunden.
Die folgenden Maßnahmen sind offen; ihr Nutzen muss erneut gemessen werden.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 1 | O-349 | MCP-Ausführungsfluss von Struktur-, Ressourcen- und Datenabhängigkeiten trennen. | **Umgesetzt, End-to-End-Abnahme offen.** `get_call_flow` trennt `execution`, `dependencies` und `all`; `research_project` nutzt execution. `CARD-INCIDENT-02_r1_with_mcp` liefert bei `get_call_flow(direction=both)` 64 reine `COPY`-Kanten. Explizite Ansichten für Ausführungsfluss und Abhängigkeiten anbieten; vorhandene Prozessprojektion aus O-292–O-295 auf Wiederverwendung prüfen. Ausführungsansicht verfolgt belegte Methoden-/Paragraphenaufrufe; gemeinsame Copybooks erzeugen keinen scheinbaren Aufrufpfad. Abnahme mit CardDemo-Incident und Syncope-Pull einschließlich Richtung, Einstieg und Unsicherheit. |
| 2 | O-350 | Relevante MCP-Graphpfade unter Antwortlimits erhalten und redundante Zugriffe bündeln. | **Teilweise umgesetzt; semantischer Fragefokus und echte Pagination offen.** Kanten werden vor den Limits deterministisch nach Aufruf-/Datenzugriffstyp, Auflösungsstatus und Quellzeile priorisiert; Antworten weisen weiter auf ausgelassene Daten hin. `SYNC-PULL-06_r1_with_mcp` liefert 120 Kanten, davon 53 mit unaufgelöstem Ziel, und wird gekürzt. Auswahl nach Einstieg, Distanz und explizitem Fragefokus statt Datenbank-ID; Getter, Logging und wiederholte Feldzugriffe bei Bedarf kompakt gruppieren, Originalbelege nachladbar halten. Abnahme prüft erhaltene Kernpfade für Connector-Aufruf, Token-Persistenz und Fehlerbehandlung sowie deterministische Auswahl, sichtbare Auslassungen und funktionierende Fortsetzung innerhalb fester Budgets. |
| 3 | O-351 | MCP-Suche und Call-Flow mit direkt nutzbaren Originalbelegen ausstatten. | **Teilweise umgesetzt; Flow-Belege und End-to-End-Abnahme offen.** `search_code` gibt beim ersten Quellchunk jetzt Chunk-ID, Quellbereich und `next_start_line` aus. `get_code_entity` liefert mehrere Originalchunks unter einem Zeichenbudget, weist gelieferte Zeilen aus und paginiert mit `next_chunk_id`/`next_char_offset`; ACL-Prüfung erfolgt vor dem Lesen. Ausführungsflows enthalten weiterhin keine Quellabschnitte samt Bedingung und Fehlerpfad. Abnahme: Belege decken die jeweilige Aussage ab, Rechte und Umfangsbudget bleiben gewahrt und zusätzliche lokale Leseaufrufe werden gemessen. |
| 4 | O-352 | Java-Aufrufketten anhand belegter Rückgabetypen auflösen und Auflösungsgründe über MCP erhalten. | **Parser-Fix umgesetzt, Reindex/Bestandsabnahme offen.** Deklarierte Rückgabetypen eindeutiger innerer Methodenaufrufe speisen die Auflösung äußerer Java-Receiver; MCP liefert erlaubte Ziel-/Receiver-Evidenz aus. Parser-Regression: `test_chained_call_receivers_resolve_from_declared_method_return_types`. Im Pull-Rohgraph bleiben unter anderem `pullTask.getResource().getPullPolicy()` und weitere verkettete Receiver unaufgelöst. Zunächst je Referenzfall Parserextraktion, Resolver, Persistenz, Indexrevision und MCP-Projektion getrennt prüfen; sichere Rückgabetypketten einschließlich belegbarer Generics/Vererbung ergänzen. Statische Deklaration und mögliche Laufzeitimplementierung unterscheiden; Mehrdeutigkeit bleibt sichtbar. Abnahme nach Reindex an Syncope und einem unabhängigen Mehrdateifall; Negativfälle dürfen keine erfundenen Ziele erhalten. MCP liefert vorhandene Receiver-Evidenz, Auflösungsgrund und Dispatch-Grenzen mit. |
| 5 | O-353 | Begrenzte Datenflussanalyse mit Reihenfolge und Bedingungen für Incident-Fragen liefern. | **Teilweise umgesetzt.** Neues `trace_data_access` listet begrenzte, indexierte `READS`/`WRITES` mit Zeilen und ACL-geprüftem Quellabschnitt in Quellreihenfolge. Pfadsensitive Reihenfolge, Bedingungen und der konkrete CardDemo-Incident-Fall bleiben offen. CardDemo-Rubrik verlangt unter anderem Befüllung/Verwendung von `PA-TRANSACTION-AMT`, XREF-Bedingung des Schreibpfads und fehlende Balancekorrektur im Batch. Quellennahen Ausschnitt für eine Variable mit Schreib-/Lesestellen, belegbarer Reihenfolge und umgebenden Bedingungen liefern; Paragraphenübergänge und unaufgelöste Pfade ausdrücklich begrenzen. Abnahme gegen manuell belegte Originalstellen sowie unabhängigen COBOL-Fall. Fehlende Indexkante darf nicht als Beweis eines fehlenden Schreibzugriffs gelten; Aussagen über ausbleibende Korrekturen benötigen vollständig untersuchten, ausgewiesenen Quellumfang. |
| 6 | O-354 | MCP-Nutzen mit fairer Bewertung und nachvollziehbarer Fehlerzuordnung erneut messen. | **Offen; nach Auslieferung der Änderungen erneut messen.** Fachliche Richtigkeit, Quellenqualität und MCP-spezifische Indexaussagen separat bewerten; nicht verfügbare Indexinformationen nicht als fachlichen Fehler der Kontrollgruppe zählen. Inhaltliche Vollständigkeit von Zitierformat unterscheiden, neue Rubrik vor Wiederholung einfrieren und Originalauswertung erhalten. Verblindete unabhängige Zweitbewertung soweit möglich; verbleibende erkennbare Toolhinweise dokumentieren. Gepaarte Wiederholung plus bisher ungenutzte Aufgaben; Modell, Prompts, Repo-/Indexrevision und Last festhalten. Wandzeit, Toolzeit/-anzahl, Antwortumfang, lokale Leseaufrufe und Tokenverbrauch soweit verfügbar ausweisen. Fehler je Fall Parser/Resolver, Index, Retrieval, MCP-Projektion oder Antwortbildung zuordnen; Qualitäts- und Zeitvorteile erst aus den neuen Messdaten ableiten. |

### MCP-Folgearbeiten aus Kapitel 2 des Codex-Benchmarks (28.09.2026)

Grundlage: `/root/codex_benchmark.html` und ausschließlich der saubere Lauf
`/root/doctus_ab_probe/official_luna_benchmark_chapter2/` mit 60 Sitzungen / 30 Paaren;
`results.json`, `scores.json`, `raw/*_with_mcp.jsonl` und die aktuellen Implementierungen
in `backend/mcp_server.py`, `backend/services/search.py` und
`backend/services/call_flow.py`. Der archivierte vermischte Lauf ist ausgeschlossen.
Die Prioritäten unten beruhen auf beobachteten Fehlern; eine kausale Wirkung der
vorgeschlagenen Änderungen ist noch nicht gemessen.

Kapitel 2 erreicht insgesamt 66,4 % Rubrikpunkte ohne und 71,1 % mit MCP;
MCP ist in 9/30 Paaren schneller, der mediane gepaarte Mehraufwand beträgt 12,1 s.
Die Bewertung stammt von einem einzelnen, nicht verblindeten Luna-Prüfer.
Besonders relevant sind die schwächeren MCP-Antworten bei `CARD-INCIDENT-02`
(54,5 % gegenüber 61,8 % ohne MCP) und `SYNC-UPDATE-05` (45,7 % gegenüber 48,6 %).
Bei `SYNC-CREATE-04` bleibt die Qualität bei 68,6 % gleich; die separaten
Arm-Mediane liegen bei 154,5 s mit und 93,9 s ohne MCP (keine gepaarte Effektgröße).
Architektur und einfacher Flow erreichen mit MCP dagegen 97,8 % bzw. 96,7 %.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 1 | O-355 | `research_project` für mehrere Symbole, verkürzte Methodennamen und fachliche Fragen nutzbar machen. | **Umgesetzt, End-to-End-Abnahme offen.** Explizite Symbolalternativen werden getrennt gesucht; `Class.method` und `Class#method(...)` werden für die exakte Kandidatenzuordnung normalisiert. Eindeutige Treffer liefern je einen begrenzten execution-Flow, Mehrdeutigkeit und leere Treffer bleiben pro Symbol sichtbar. Fachliche Freitextfragen benötigen weiterhin begrenztes Code-/Wissensretrieval statt Symbolauflösung. Abnahme mit allen 18 archivierten Fehlanfragen, unabhängigen Java-/COBOL-Fragen, gleichnamigen Methoden, Quellen-/Variantenkonflikten und ACL-Negativfällen; Recall, falsche Auflösung und Toolzahl messen. |
| 2 | O-356 | Beleg- und Datenzugriffswerkzeuge aus Such-/Flow-Ergebnissen gezielt erreichbar machen. | **Offen; ergänzt O-351/O-353.** In allen 30 MCP-Sitzungen kein Aufruf von `get_code_entity`, `trace_data_access` oder `search_knowledge`. Vorhandene Fähigkeiten helfen deshalb im Benchmark bisher nicht nachweisbar. Toolbeschreibungen mit konkreten Einsatzzwecken und Antwortverträge mit strukturierten, budgetierten Folgeaktionen samt Toolname und gültigen Argumenten ergänzen: Quellbereich nachlesen, Variable verfolgen, Einstieg auswählen oder leere Suche fachlich fortsetzen. Bei passenden Datenentitäten belegte READS/WRITES optional direkt bündeln; keine pauschale Pflichtkette zusätzlicher Tools. Abnahme: Incident-Fragen erreichen tatsächliche Lese-/Schreibbelege; Annotationen und Rückgaben werden gelesen; Mehrdeutigkeit führt zur Auswahl statt Abbruch. Anzahl sinnvoller Folgeabrufe, lokale Ersatzlesevorgänge, Antwortumfang, Qualität und Gesamtzeit vergleichen; bloße Toolnutzung ist kein Erfolgskriterium. |
| 3 | O-357 | Java-Methodenkontext für Argumente, Rückgaben und Transaktionsdeklarationen belegbar liefern. | **Teilweise umgesetzt; Laufzeitabgrenzung und End-to-End-Abnahme offen.** Java-Entities erfassen jetzt Annotationen mit Attributwerten als Quellausdrücke, Methoden-Rückgabeausdrücke mit Zeilen sowie begrenzte CALLS-Argumentausdrücke. `search_code`, `research_project`, `get_code_entity` und Call-Flow geben diese strukturierten Belege aus. Ausdrücke sind statische Quellbelege; sie lösen keinen Wertefluss auf und beweisen keine Proxy-/Laufzeitwirkung. CREATE/UPDATE- und unabhängige Java-Abnahme stehen aus; Overloads, Annotationen oberhalb des Methodenbereichs und Delegation explizit prüfen. |
| 4 | O-358 | MCP-Mehrkosten und leere bzw. doppelte Recherche getrennt messen und reduzieren. | **Offen; ergänzt die Nutzenmessung O-354.** Wandzeiten beweisen keine langsame Serverausführung. Je Tool monotone Dauer, Payloadgröße, Ergebnis-/Kürzungsstatus und verwendeten Indexstand erfassen; getrennt von Modellzeit, lokalen Leseaufrufen und Antworttokens auswerten. `research_project` liefert teils bereits einen Flow; gleichwertige Folgeabrufe von `get_call_flow` nach Argumenten/Scope/Revision erkennen und durch Wiederverwendung oder gezielte Vertiefung vermeiden. Such-, Flow- und Belegbündel nur unter einem gemeinsamen Antwortbudget anbieten; bestehende Pflichtaufrufe der eingefrorenen Suite nicht nachträglich entfernen. Abnahme an archivierten Anfragefolgen und vorregistrierten neuen Paaren: weniger leere/doppelte Aufrufe und geringere gepaarte Gesamtzeit bei erhaltener Quellenqualität. Keine unbelegte Latenzzusage und kein Cache ohne Berechtigungs-, Varianten- und Revisionsbindung. |

Bestehende Tickets bleiben die Eigentümer der folgenden Restarbeiten; keine
zweiten Implementierungstickets für dieselbe Lücke anlegen:

- **O-350 – Graphfortsetzung und Relevanz:** Kapitel 2 enthält 8 gekürzte
  `get_call_flow`-Antworten unter 33 Aufrufen und 4 Fälle
  `entry_point_selection_required`. Der MCP-Adapter begrenzt nach ID sortierte
  Knoten auf 80 und Kanten auf 120, der darunterliegende Dienst auf 150/500;
  `next_cursor` bleibt `None`. Auswahl vom Einstieg und relevanten Pfaden her
  durchgängig vor beiden Limits durchführen. Eine Fortsetzung muss gezielt
  ausgelassene Kanten erreichen; bloß denselben Root enger abzufragen kann
  weiterhin dieselben Ergebnisse liefern. Kürzung durch Budgets und durch
  Sichtbarkeitsfilter auseinanderhalten, ohne verborgene Daten preiszugeben.
- **O-351 – Originalbelege:** `search_code`/`get_code_entity` schneiden Text nach
  1600 Zeichen ab, `trace_data_access` nach 1200, während `end_line` weiterhin
  die Chunk-Grenze bezeichnet. Der Such-/Entity-Pfad weist Chunk-IDs und
  gelieferte Zeilenbereiche inzwischen aus und erlaubt Chunk-Fortsetzung. Noch
  offen sind zentrierte Belege für Flow-Kanten und der dazugehörige Bedingungs-
  und Fehlerpfad; `trace_data_access` kürzt weiterhin nach 1200 Zeichen.
- **O-353 – Datenfluss:** In 5/5 MCP-Incident-Antworten fehlen das Risiko der
  vorzeitigen Verwendung von `PA-TRANSACTION-AMT`, die vollständige
  Datumsrekonstruktion/Defaultfrist und die unveränderte Batch-Kreditbalance;
  3/5 nennen einen nicht belegten konkreten Onlinebetrag. Die vorhandene
  READS/WRITES-Liste ist noch keine Analyse von Zuweisungen, Kontrollbedingungen
  oder paragraphenübergreifender Ausführungsreihenfolge. Indexabdeckung zunächst
  gegen die Originalstellen prüfen; die belegbare Kette von Zuweisung und
  Verwendung mit XREF-Bedingung und MQ-/IMS-Reihenfolge liefern. Grenzen und
  nicht untersuchte Pfade sichtbar halten, unbekannte Werte nicht konkretisieren.
- **O-354 – Bewertungs- und Laufqualität:** Kapitel 2 als unveränderte Baseline
  erhalten. Vor neuer Messung Rubriken auf Toolzugangsbonus, reine Zitierformfehler
  und die Unterscheidung deklarierter Annotation versus tatsächlicher
  Transaktionswirkung prüfen; auffällige Abwertungen unabhängig nachbewerten.
  Neues Protokoll samt Hashes für alle sechs Rubriken einfrieren: Die aktuelle
  `scores.json` enthält Bewertungen für alle sechs Fälle, im Feld
  `rubric_sha256` jedoch nur `SYNC-PULL-06`. Ein exklusives Runner-Lock, eindeutige
  Run-ID, atomare Ergebnisdateien und geprüftes Resume gegen das Manifest
  verhindern erneute Vermischung durch konkurrierende Runner. JSON-Schemavalidierung
  vor Übernahme jeder Bewertung; Rohantwort und Reparaturprotokoll erhalten.
  Pro abgeschlossenem Sitzungspaar Zeiten ohne/mit MCP, Differenz und Status
  ausgeben; Datenvollständigkeit vor dem nächsten Fall prüfen.

### Parser-/Indexabdeckung für den MCP-Benchmark (28.09.2026)

Lesender Abgleich des laufenden PostgreSQL-Index (Projekte 1246/1247), der
entschlüsselten Quellchunks und der aktuellen Parser-/MCP-Implementierung.
Zusätzlich `COPAUA0C.cbl` mit dem aktuellen lokalen Parser ausschließlich im
Speicher neu geparst, ohne Import oder Indexänderung. Ergebnis: **Die benötigten
Informationen sind noch nicht vollständig strukturiert oder als Quellchunks
vorhanden.** Einzelheiten: [Parser-Abdeckungsprüfung](MCP_PARSER_COVERAGE_2026-09-28.md).

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
| 1 | O-359 | Unvollständige COBOL-Struktur- und Chunkabdeckung erkennen und fehlenden Originaltext zugänglich halten. | **Abgeschlossen (28.09.2026).** Fehlerursache in `antlr_bridge.py` behoben (Punkt-Injektion bei maskierten EXEC-Blöcken im IF/PERFORM-Kontext entfernte nachfolgende Paragraphen). `COPAUA0C.cbl` parst nun fehlerfrei alle 43 Paragraphen bis Zeile 1025; Chunks decken Zeile 885 und 913–919 vollständig ab. DECLARATIVES-Visitor in `divisions.py` ergänzt. Fallback-Chunking für unvollständige Grammatik-/Syntaxfehlerbereiche in `parse.py` ergänzt. Regressionstests in `test_cobol_parse.py` hinzugefügt. |

Weitere Befunde erweitern vorhandene Tickets:

- **O-353:** `PA-TRANSACTION-AMT` ist als Entity 119377 vorhanden, die Verwendung
  bei `COPAUA0C.cbl:821` jedoch nur als aufgelöste `USES`-Kante. `trace_data_access`
  filtert ausschließlich `READS`/`WRITES` und liefert diese Stelle nicht.
  COBOL-XREF klassifiziert Feldreferenzen derzeit ohne Lese-/Schreibrichtung;
  MOVE-/ADD-/COMPUTE-Operanden und umgebende Laufzeitbedingungen strukturiert
  erfassen. O-359 muss zuerst die Zuweisung in Zeile 885 zugänglich machen.
  Vorhandene `condition`-Metadaten stammen aus bedingter Vorverarbeitung und
  ersetzen keinen Laufzeit-IF-/ELSE-Kontext.
- **O-357:** Java-Methoden speichern Annotationsnamen und Rückgabetyp, aber bei
  den geprüften Manager-Methoden nicht die Annotationswerte. `Transactional`
  ist indexiert; `propagation = Propagation.REQUIRES_NEW` steht nur im
  entschlüsselten Originalchunk. CALLS-Metadaten enthalten Argumentanzahl und
  teils Typen, nicht die konkreten Argumentausdrücke bzw. deren Wertefluss.
  Vorhandene Originalbelege zuerst korrekt liefern; für strukturierte Abfragen
  Annotationseigenschaften, Argumentausdrücke und Return-Verknüpfungen ergänzen.
- **O-351:** Die Entity-Definition liefert nur den ersten überlappenden Chunk.
  `PullJobDelegate#doExecuteProvisioning` umfasst 213–395, geliefert wird
  zunächst nur 213–239; beim Manager-create 88–112 zunächst 88–108. Zusätzlich
  greift das MCP-Zeichenlimit. Bereichsweises Nachladen und eindeutige
  Vollständigkeitsangaben sind erforderlich, auch wenn alle Java-Chunks bereits
  gespeichert sind.
- **O-355:** Methoden sind tatsächlich vorhanden, aber mit Qualified Names wie
  `PullJobDelegate#doExecuteProvisioning(...)`; die Punktnotation der fünf
  Benchmark-Anfragen passt nicht zur aktuellen Substring-Suche. Dies ist eine
  Such-/Normalisierungslücke, kein fehlender Methoden-Parse.
- **O-352:** Im Live-Index bleibt `pullTask.getResource().getPullPolicy`
  ungelöst, während `pullTask.getResource` aufgelöst ist. Vor Behauptung einer
  abgeschlossenen Bestandskorrektur Resolverstand, Neuauflösung und Reindex
  am konkreten Fall prüfen; aus diesem Audit allein ist die Ursache nicht
  zwischen altem Index und verbleibender Resolverlücke entschieden.
- **O-306:** Die lokale Operation `COPAUA0C.EXEC-DLI-BLOCK@825.REPL@825`
  existiert als Entity 122174; die zugehörige `EXECUTES`-Kante trägt den exakten
  Ziel-Qualified-Name, bleibt aber `unresolved` mit leerer Ziel-ID. Lokale
  EXEC-Operationen in Persistenz/Nachauflösung tatsächlich verknüpfen, getrennt
  von dynamischen externen Ressourcen. Abnahme mit Projekt-/Quellen-/Varianten-
  Bindung und passendem Operationsbeleg. Keine Laufzeitverfügbarkeit ableiten.

### COBOL-Analyse: strukturelle und semantische Lücken (28.09.2026)

Prüfung der vollständigen Pipeline von Vorverarbeitung über Parserextraktion bis
zu Persistenz/MCP. Fünf neue Arbeitspakete; vorhandene Tickets weiterverwenden,
wo dieselbe Lücke bereits beschrieben ist. Nachweise und Grenzen stehen in
[COBOL-Analyseprüfung](COBOL_ANALYSIS_AUDIT_2026-09-28.md). Kleine In-Memory-Proben
reproduzieren die Fehler; CardDemo-Live-Index zusätzlich lesend abgeglichen.
Die ersten drei vollständigen Programmproben liefern keine Parserdiagnosen,
obwohl Informationen verloren gehen oder falsche Beziehungen entstehen.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 1 | O-360 | COBOL-Aufruf- und Sprungkanten an echte Anweisungsgrenzen binden; Kontrollkontext erhalten. | **Abgeschlossen (28.09.2026).** Statement-Begrenzer (`_STATEMENT_DELIMITERS`) in `procedure.py` eingeführt, sodass Schlüsselwörter (`ELSE`, `DISPLAY`, `END-IF`) nicht als GOTO-Ziele erfasst werden. `src_end_line` für GO TO, PERFORM und CALL korrigiert. Inline-Perform-Zählvariablen (`TIMES-N TIMES`) von Prozedurzielen getrennt. Kontrollkontext (`IF/ELSE/WHEN/EVALUATE`) an Kantenmetadaten angehängt. 10/10 Tests in `test_cobol_procedure.py` erfolgreich. |
| 2 | O-362 | Embedded-SQL-Ziele und Lese-/Schreibrichtung korrekt extrahieren. | **Abgeschlossen (28.09.2026).** SQL-Kommentare (`--`, `/* */`) und String-Literale in `sql.py` bereinigt, um Scheintabellen (`'JOIN FAKE-TABLE'`) auszuschließen. Schema-qualifizierte Tabellen (`BANK.ACCOUNTS`) zugelassen. Hostvariablen zwischen `INTO` und Folgeklauseln als WRITES, Prädikate als READS erfasst. Tabellenrollen klauselspezifisch zugeordnet. 13/13 Tests in `test_cobol_sql.py` erfolgreich. |
| 3 | O-361 | COBOL-Datendeklarationen vollständig genug für Feld-, Layout- und Bedingungsanalyse speichern. | **Abgeschlossen (28.09.2026).** `LOCAL-STORAGE SECTION` Visitor in `data_division.py` hinzugefügt. Level 66 `RENAMES`/`THRU` in `DataItem.renames`/`renames_thru` erfasst. Level 88 Mehrfachwerte und Intervalle (`1 THRU 3, 7`) in `DataItem.values` und `value` erfasst. `USAGE` (z.B. `COMP-3`) extrahiert und in Metadaten propagiert. 16/16 Tests in `test_cobol_data_division.py` erfolgreich. |
| 4 | O-363 | COBOL-Datei-I/O an einzelne Anweisungen und vollständige Dateideklarationen binden. | **Abgeschlossen (28.09.2026).** `_associated_record` an Statement-Grenzen gebunden (verhindert Übernahme fremder FROM/INTO-Operanden ohne Satzpunkt). Multi-File-`CLOSE` Statements in `io.py` unterstützt. `FILE-CONTROL` Deklarationen (`SELECT ... ASSIGN TO ... FILE STATUS IS ...`) in `FileDescriptor` und Entity-Metadaten übernommen. Tests in `test_cobol_parse.py` erfolgreich. |
| 5 | O-364 | Ausführbare Copybooks und deren Verwendung im Programm strukturiert analysieren. | **Abgeschlossen (28.09.2026).** `parse_copybook` um Erkennung von ausführbaren (Procedure-) Copybooks erweitert (`_is_procedure_copybook`). Synthetische `PROCEDURE DIVISION`-Kapselung für ANTLR erzeugt, Paragraphen, CALL/PERFORM-Kanten, SQL- und EXEC-Blöcke ohne Syntaxfehler-Abbruch extrahiert. Bug in `_COPY_START_RE` (fälschlicher Match auf Bezeichner wie `COPY-PARA`) behoben. Regressionstest in `test_cobol_parse.py` erfolgreich. |

Bereits offene Arbeit, durch diese Prüfung weiter konkretisiert:

- **O-305/O-359:** Recovery und lückenlose Originaltext-Abdeckung bleiben die
  erste Voraussetzung. Auch ohne Parserabbruch werden bei vorhandenen Paragraphen
  ausschließlich Paragraphen gechunkt; DATA/ENVIRONMENT-Bereiche sind dadurch
  nicht automatisch als Originalchunks zugänglich. Fallback greift derzeit nur,
  wenn überhaupt keine Paragraphenchunks entstanden sind.
- **O-353:** MOVE/ADD/COMPUTE und weitere Feldoperationen benötigen getrennte
  Lese-/Schreiboperanden und Kontrollbedingungen; allgemeines USES reicht nicht.
  CALL-USING-/RETURNING-Bezüge und Parameterrollen bei Bedarf quellenbelegt
  anbinden; fehlende Laufzeitwerte nicht aus dem statischen Graphen erfinden.
- **O-306/O-307:** EXEC CICS READ erfasst FILE, aber nicht INTO-/RESP-Zugriffe;
  EXEC DLI ISRT erfasst SEGMENT, aber nicht FROM-Puffer als gelesene Daten.
  Beide Fälle in kleinen Proben bestätigt. Dialektspezifische Operandenrollen
  und Status-/Fehlerpfade ergänzen, zusätzlich zur bereits offenen Verknüpfung
  vorhandener EXEC-Operationen. Vorhandene Namen allein belegen noch keine
  vollständige I/O-Semantik.
- **O-124/O-135/O-139–O-143:** Präprozessor-, Compiler-, Bibliotheks- und
  Dialektabdeckung bleibt begrenzt. `conditional.py` wertet aktuell lediglich
  numerische Gleichheit und DEFINED aus; komplexere Bedingungen bleiben mit
  Bedingungshinweis erhalten. Das ist eine bewusst konservative Grenze und
  keine vollständige Compilerpräprozessierung. Neue Dialektunterstützung mit
  bestätigten Profilen und realen Fixtures abnehmen.

### Java-Parsing und Zielauflösung: belegte Restlücken (28.09.2026)

Lesender Code-/Indexabgleich plus zehn kleine Java-In-Memory-Proben mit
`parse_java_file`, ohne Import oder Bestandsänderung. Die Proben erzeugten
keine Syntaxdiagnosen. Einfache lokale Java-Aufrufe und ein einteiliger
`getB().work()`-Rückgabetyp-Flow funktionieren bereits; die folgenden Fälle
sind zusätzliche, reproduzierte Lücken. Details und Beispielcode stehen in
[Java-Analyseprüfung](JAVA_ANALYSIS_AUDIT_2026-09-28.md).

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
| 1 | O-365 | Ausführbare Beziehungen in Lambdas und anonymen Klassen ihrem tatsächlichen Typ-/Methodenkontext zuordnen. | **Abgeschlossen (28.09.2026).** `JavaRelationshipVisitor` in `relationships.py` um Scopes für `visitLambdaExpression` und `visitCreator` (anonyme Klassen) erweitert. Aufrufe in Lambdas erhalten das Lambda als `src_name`. Aufrufe in anonymen Klassenmethoden erhalten die innere Methode als `src_name`. `this.helper()` in anonymer Klasse bindet an die lokale Hilfsmethode der anonymen Klasse; unqualifizierte Aufrufe fallen bei Bedarf lexikalisch auf die äußere Klasse zurück (`resolution.py`). Unit-Tests in `test_java_relationships.py` erfolgreich. |
| 2 | O-366 | Lokale Java-Variablen anhand lexikalischem Block und Verwendungsposition auflösen. | **Scope-basierte Auflösung umgesetzt; Regression/Abnahme offen.** Lokale Variablen tragen jetzt Block-/`for`-/`catch`-/Lambda-Scope und Deklarationsposition. Der Resolver wählt nur vor der Verwendung deklarierte, dort sichtbare Variablen; innere Scopes und spätere Deklarationen werden berücksichtigt. Catch- und Enhanced-`for`-Variablen werden als Variablen erfasst; Lambda-Code kann auf sichtbare äußere Methodenvariablen zurückgreifen. Mehrdeutigkeit bleibt unresolved. Regressionen für Shadowing, geschachtelte Scopes, Lebensdauer, `for`/`catch`/Lambda und Negativfälle sowie Zielbestandsabnahme ergänzen. Kein globaler Name-only-Fallback. Ergänzt O-309/O-352. |
| 3 | O-367 | Java-Methodenreferenzen auf belegte Zieldeklarationen beziehen. | **Kantenprojektion und eindeutige Zielauflösung umgesetzt; Regression/Bestandsabnahme offen.** `REFERENCES_METHOD` verbindet `this::m`, `Type::static`, `obj::m` und `Type::new` mit einer eindeutigen Repository-Deklaration und speichert Receiver, Referenzart und Quellort. Überladene oder externe Ziele bleiben unresolved. Die Kante bezeichnet eine Methodenreferenz, keinen ausgeführten Aufruf. Abnahme mit Ambiguität, generischen funktionalen Interfaces und externem Classpath; Regressionen ergänzen. Ergänzt O-310. |
| 4 | O-368 | Java-Feldzugriffe über andere Repositorytypen sicher auflösen. | **Resolver umgesetzt, Regression/Bestandsabnahme offen.** Unqualifizierte Zugriffe sowie `receiver.field` werden im globalen Resolver gegen die belegte Felddeklaration aufgelöst. Der Receiver muss eindeutig über Parameter/lokale Variable/Feld oder `this`/`super` bestimmbar sein; Vererbung und Modul-/Source-Set-Grenzen werden über die bestehende Typauflösung berücksichtigt. Mehrdeutige Receiver oder Felder bleiben unresolved und erhalten einen Auflösungsgrund. Abnahme mit eindeutigem Ziel, gleichnamigen Klassen, vererbten/verdeckt deklarierten Feldern, generischen Receivern und nicht auflösbarem externen Typ; Regressionen ergänzen. Ergänzt O-309/O-310. |
| 5 | O-369 | Java-Ausnahme- und Abschlusswege als begrenzte, belegte Beziehungen erhalten. | **Offen, Syntax vorhanden, Semantik nicht projiziert.** `run() throws IOException { try { work(); } catch(IOException ex){ recover(); } finally { close(); } }` erzeugt drei einfache CALLS-Kanten ohne Throws-/Catch-/Finally-Rollen; die Method-Entity enthält kein `throws`-Metadatum. Kontroll- und Ausnahmewege mit Quellstellen und deklarierter Ausnahme getrennt vom tatsächlich geworfenen Fehler modellieren; `try` mit Ressourcen, Mehrfach-Catch und verschachtelte Finally-Blöcke berücksichtigen. Abnahme: Prozess-/Impact-Anfragen dürfen `recover()` nicht als unbedingten Folgeaufruf des Erfolgspfads darstellen; dynamische Ausnahmen und Bibliothekscode bleiben sichtbar unsicher. Nach O-365 priorisieren, weil korrekter Scope für diese Projektion vorausgesetzt ist. |

Bestehende Tickets bleiben zuständig für angrenzende Lücken:

- **O-357:** Annotationen sind nur als Namen strukturiert gespeichert.
  Die Probe `@Flag("critical")` ergibt `annotations=["Flag"]` ohne Wert;
  `@Transactional(propagation = Propagation.REQUIRES_NEW)` ist in Syncope
  ebenfalls nur im Originalchunk vollständig. Attribute aus dem Syntaxbaum
  getrennt vom Laufzeiteffekt erhalten; Quellbelege und Annotationstyp prüfen.
- **O-352:** Einfache Rückgabetypkette `getB().work()` löst in der Probe sicher
  auf. Der Syncope-Bestandsfall `pullTask.getResource().getPullPolicy()` bleibt
  unresolved. Reindex/Resolverstand und mehrstufige Kette gezielt abnehmen,
  bevor eine generelle Parserlücke behauptet wird.
- **O-351:** Java-Quellchunks decken Methoden ab, die MCP-Definition nimmt
  derzeit jedoch nur den ersten überlappenden Chunk und schneidet zusätzlich
  nach Zeichenbudget ab. Die Evidenzlücke wird nicht allein durch Reparse gelöst.

### Sprachlogik und anklickbare Codeobjekte

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 12 | O-306 | `EXEC CICS`, `EXEC DLI`/IMS und belegte weitere `EXEC`-Dialekte als anklickbare Blöcke, Operationen und Ressourcenbeziehungen erhalten. | **Umgesetzt, Bestandsabnahme offen.** Blöcke, Operationen und explizite CICS-/IMS-Ressourcen sind adressierbar; `DL/I` und `DLI` haben dieselbe Identität. CICS-`LINK`/`XCTL` mit `PROGRAM(...)` erzeugen zusätzlich einen belegten Programmaufruf, variable Operanden bleiben `dynamic`, unbekannte Dialekte sichtbar. Reale Kundenvarianten gemäß O-141–O-143 noch abnehmen. |
| 13 | O-307 | COBOL-I/O, SQL, Datenstruktur und Lese-/Schreibzugriffe fachlich verbinden. | **Umgesetzt, Bestandsabnahme offen.** SQL-Tabellen/Hostvariablen sowie COBOL-READ/WRITE/REWRITE/OPEN/CLOSE sind richtungsbehaftet verbunden. Standard-`WRITE`/`REWRITE` auf einen FD-Satz verknüpfen den Absatz mit dem Satzlayout und den `FROM`-Puffer als Lesezugriff; unbekannte oder mehrdeutige Ziele bleiben unresolved. Reale CardDemo-Abnahme folgt. |
| 14 | O-308 | Java-Records, Parameter, relevante lokale Variablen, lokale/anonyme Klassen, Lambdas und Methodenreferenzen adressierbar machen. | **Umgesetzt, Bestandsabnahme offen.** Alle genannten Elemente erhalten quellennahe Java-Entities und stabile Qualified Names; gleichnamige lokale Typen in getrennten Blöcken bleiben über ihre Quellposition getrennt persistierbar. Auflösung ihrer fachlichen Beziehungen bleibt bei O-309/O-310. Graphübersicht größenbegrenzt halten. |
| 15 | O-288 | COBOL-`PERFORM THRU`, `EXEC SQL INCLUDE` und `file_fd`-Beziehungen vervollständigen. | **Umgesetzt, Bestandsabnahme offen.** `THRU`-Endpunkte tragen neben dem Quellenbeleg eine lokale Qualified-Name-Identität samt Auflösungsstatus, ohne eine falsche Direktkante zu behaupten. SQL-Include und FD→Satzlayout sind explizite lokale Beziehungen. An CardDemo mit Originalzeilen abnehmen. |
| 16 | O-287 | Maven-Kanten dateilokal und über Module/Source-Sets korrekt auflösen. | **Umgesetzt, Bestandsabnahme offen.** Der Java-Resolver bevorzugt gleichnamige Typen aus dem Modul und passenden Source-Set des Aufrufers; `main` referenziert nie test-only Typen. Bei mehrfachen Qualified Names wird der konkret gewählte Zielpfad persistiert, damit die Datenbankkante auf die richtige Modulinstanz zeigt. Externe Maven-Abhängigkeiten werden weiterhin nicht geraten. Mehrmodul-/Source-Set-Regressionen vorhanden; am Zielbestand abnehmen. |
| 17 | O-289 | Shell-Funktionen per `DECLARES` und lokale Aufrufe mit dem Skript verbinden. | **Umgesetzt, Bestandsabnahme offen.** Shell-Funktionen sind als `DECLARES` vom Skript und mit stabilen Qualified Names erfasst; Aufrufe einer bereits deklarierten lokalen Funktion werden als quellennahe, aufgelöste `CALLS`-Kante zum korrekten Funktionsobjekt persistiert. Unbekannte Kommandos bleiben unbelegt. Parser- und Git-/DB-Regressionen mit realistischer Shell-Fixture vorhanden. |
| 18 | O-243 | Java-Syntax und Strukturunterstützung am Zielbestand absichern. | **Technische Referenzabdeckung umgesetzt, Bestandsabnahme offen.** Versionierter Offline-Korpus prüft Java 8, Java 21, Lombok, Maven-Pfade, Quellpositionen und Syntaxfallback; der vereinbarte O-240-Referenzbestand fehlt weiterhin und muss die fachliche Abnahme ergänzen. |
| 19 | O-245 | Java-Aufrufauflösung und Unsicherheit an belegten Referenzfällen messen. | **Technische Messbasis umgesetzt, Bestandsabnahme offen.** Read-only Audit und versionierter Mehrdatei-Korpus zählen Auflösungsstatus/-gründe, Receiver-Evidenz und Zielmethoden; sichere, mehrdeutige und offene Aufrufe sind regressionsgesichert. Gegen den O-240-Referenzbestand messen und dortige Fälle ergänzen. |
| 20 | O-253 | Mischsprachen in Editor, Graph, Zitaten und Agentenantworten korrekt anzeigen. | **Technisch umgesetzt, Bestandsabnahme offen.** Editor, Graphsprache/-status, Zitatwarnungen und belegorientierte Agentenanweisungen sind abgestimmt. Offline-Ende-zu-Ende-Fixture für Java, XSLT, XML, JSP und Shell sowie UI-/Prompt-Regressionen vorhanden. Am freigegebenen Zielbestand fachlich bestätigen. |
| 21 | O-254 | Qualität und Last des tatsächlichen Mischbestands vor der Pilotfreigabe messen. | Offline-Parserlauf samt reproduzierbarem Messskript und Regressionen je Sprache plus realem Java→XSLT-Fall vorhanden. Betreibergrenzwerte, Remote-Qwen-Retrieval und parallele Lastprobe bleiben offen. |

### Wissensgraph, Wissen und Suche

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 26 | O-273 | Änderungsfolgenanalyse um Diff, Revision und belastbare Test-/Owner-Bezüge abschließen. | **Entwicklung abgeschlossen; fachliche Bestandsabnahme in O-300 offen.** Diff-Eingabe im Änderungsdialog und in der API; Analyse nur bei vollständig indiziertem Zielcommit. Gleichnamige Dateien verschiedener Git-Quellen bleiben getrennt. Das Paket enthält begrenzte Codepfade, freigegebene Dokument-/Vorgangsbezüge, statisch belegte Testreferenzen und CODEOWNERS-Hinweise. Fehlende Belege, Kürzungen und Grenzen der Dateianalyse sind sichtbar. |
| 27 | O-274 | PR-/MR-Diskussionen und ADRs mit Herkunft, Version und Prüfstatus erschließen. | Erst nach stabilem Erkenntnismodell O-271/O-301. |
| 28 | O-275 | Fachbereichsübersichten aus Zweck, Systemen, Regeln, Sonderfällen und Verantwortung bilden. | Bestätigte Quellen und Verantwortlichkeiten erforderlich. |
| 29 | O-276 | Geprüfte, widersprüchliche und veraltete Erkenntnisse in Chat und Ansichten sichtbar machen. | **Chat-Anzeige umgesetzt (nur Evidenzmodus):** Antwort- und Quellenprovenienz sowie die Aktion zum Speichern als Erkenntnisentwurf erscheinen nur bei Evidenzantworten. Der normale Chat zeigt diese Provenienzhinweise nicht und kann Antworten nicht als Erkenntnisentwurf speichern. Die fachliche Abnahme der Erkenntnisstatus bleibt bei O-272/O-302. |
| 30 | O-277 | Repräsentative Such- und Antwortfragen mit erwarteten Fundstellen versionieren. | Grundlage für O-284/O-304. |
| 31 | O-278 | Pilotaufgaben und Ausgangswerte für Fehleranalyse, Einarbeitung und Änderungsvorbereitung erfassen. | Pilotteam erforderlich. |
| 32 | O-279, O-280 | Entity-Kontext und semantische Linkprüfung fachlich am Referenzbestand abnehmen und Restlücken schließen. | Teilweise umgesetzt; harte Kontextgrenzen beibehalten. |
| 33 | O-284 | EVALRUN_1 um feste Java-/COBOL-Positionen, erwartete Dokumentpassagen und Negativfälle erweitern. | Nach O-277. |

### Link-Berechnung und Laufzeit

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 34 | O-179 | Run-Budget, Kostenschätzung, Fortschritt und Abbruch für Link-Läufe liefern. | **Technisch umgesetzt, Live-Abnahme offen.** Entity- und Cross-Source-Läufe begrenzen die Zahl geprüfter Entitäten bzw. Abschnitte je Lauf (1–5000), dokumentieren Fortschritt im Job Center und lassen sich nach Erreichen des Budgets fortsetzen; aktiver Abbruch bleibt verfügbar. Die Startansicht zeigt eine Obergrenze für Embedding- und LLM-Aufrufe. Kein Remote-Modelllauf für diese Abnahme ausgeführt. |
| 35 | O-181 | Kandidatenbildung über begrenzten, verschlüsselungskonformen Vorfilter skalieren. | Repräsentative Korpusmessung. |
| 36 | O-182 | Entity-Embeddings persistent cachen und per Inhalt sowie Modellversion invalidieren. | Aktives Embedding-Profil berücksichtigen. |
| 37 | O-183 | Top-k, Deduplizierung, Schwellen, Batch-Review und Parallelität als Run-Parameter führen. | Nach O-179/O-182. |
| 38 | O-184 | Kandidaten und Persistenz bündeln; Unique-Constraints und Bulk-Upserts ergänzen. | Nach O-183. |
| 39 | O-185 | Kontingente für Import, Linking und globale Batch-Läufe trennen. | SLOs mit Betreiber vereinbaren. |
| 40 | O-186 | Versionierten Benchmark für Import, Delta-Sync, Linking, Suche und Speicher erstellen. | Nach O-179 bis O-185. |

### Chat-Agent: Ansichten während der Arbeit

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 41 | O-199 | Ziel-Qwen, Streaming, Berechtigungen und Panel-Regeln gezielt abnehmen. | **Teilabnahme 28.09.2026:** aktives RunPod-Qwen-Profil 58 lieferte zehn SSE-Chatantworten; unauthentifizierter `POST /chat` wurde mit HTTP 401 abgewiesen. J5 Quellen und Antworten sichtbar. Nicht-Admin-Projektisolierung sowie Panel-Öffnen/-Schließen-Regeln in der UI nicht erneut geprüft. |
| 42 | O-193 | Suchergebnisse mit nachvollziehbarem Projekt- und Quellenfilter öffnen. | **Live-Abnahme fehlgeschlagen 28.09.2026:** Projekt + Quelle 1005 + Entityfilter für `COPAUA0C` ergaben HTTP 200, aber 0 Treffer; Suche nur nach Projekt hatte zuvor 198 Entities geliefert. Bug O-348. |
| 43 | O-194 | Begrenzte Wissensgraph-Nachbarschaft mit Fokus und Beziehungsfiltern öffnen. | **API-Bugverdacht reproduziert; Agentenansicht/UI offen.** 28.09.2026: `GET /graph/neighborhood` für Entity 121997 und `code_dependency` lieferte HTTP 200, nur einen Dateiknoten, null Kanten/`total_edges=0` und gleichzeitig `has_more=true`, Cursor `10`, `truncated={incoming:true,outgoing:true}`. Fokusdatei stimmt (`COPAUA0C.cbl`), aber die Graphkanten fehlen. Agenten-Tool und Panel nicht live bedient; Umfangs-/Fortsetzungssignal und Filterverhalten weiter prüfen. Details in [EVALRUN_1.md](EVALRUN_1.md). |
| 44 | O-197 | Link-Manager auf eine konkrete Verknüpfung und ihre Belege fokussieren. | O-190 bis O-192 sind umgesetzt. |
| 45 | O-198 | Quellen- und Jobstatus im Job Center lesend öffnen. | Niedrigere Produktpriorität. |
| 46 | O-258 | Import und Chat parallel gegen das Zielmodell testen und First-Token-SLO abnehmen. | Betreiber und Zielmodell erforderlich. |
| 47 | O-187, O-259 | Profil-Verfügbarkeitsprüfung und Mismatch-Telemetrie abschließen; Remote-Qwen-Tool-Aufrufe und belastbare Zitation live abnehmen. | **Teilabnahme 28.09.2026:** Profile 58 (`qwen3:32b`) und 4 (`bge-m3`, 1024d) waren aktiv; direkte RunPod-Smokes bestätigten Tags und Embedding-Dimension. Zehn Chats erzeugten native Doctus-Tool-Aufrufe, aber J2/J4 und C1/C3/C4/C6 lieferten leere oder fehlende Zitation trotz vorhandenem Kontext. Belastbare Zitation bleibt offen; Profil-Readiness-Mismatch-Test nicht separat wiederholt. |
| 48 | O-250, O-260, O-261, O-262, O-263 | Umgesetzte Mischsprachen-, Shell-, HTML-, Ablauf- und Intent-Fixes ausrollen, reindizieren und an den realen Beständen abnehmen. | Rollout/Reindex und Remote-Qwen erforderlich. |
| 49 | O-264 | Datenbankmigration für Kantenrichtung beim Rollout anwenden. | Technisch umgesetzt; Migrationsnachweis offen. |

### Entwickler-Workflow & IDE-Integration

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 50 | O-324 | Headless MCP-Server (Model Context Protocol) zur Anbindung lokaler Offline-IDEs bereitstellen. | MCP-Sicherheitsprüfung am 24.09.2026: zwei Befunde zu `search_knowledge`-Projektisolation und Call-Flow-Ressourcenlimits behoben; 27 isolierte Prüfungen und 9 Regressionen bestanden, siehe [Sicherheitsbericht](MCP_SECURITY_REVIEW_2026-09-24.md). Backend, Tokens, sechs lesende Tools, Migration und Rollout sind implementiert; Remote-VS-Code-MCP-Client ist konfiguriert. Direkte fremde Projekt-/Entity-Zugriffe, abgelaufene/widerrufene Tokens und deaktivierte Konten werden korrekt abgewehrt. `search_knowledge` kann wegen des unabhängigen Embedding-HTTP-Fehlers aus O-251 noch funktional fehlschlagen. **O-171 abgeschlossen:** Die strategische Entscheidung für Doctus als schreibgeschütztes Werkzeug-Backend bleibt abgeschlossen. |
| 51 | O-325 | IDE-Integration & Deep Links (VS Code / JetBrains / Eclipse) für nahtlose Navigation liefern. | VS-Code-Extension und tokengebundene IDE-API für `CALL`/`COPY` sind implementiert; ein stdio-Language-Server bietet Hover, CodeLens und Graph-Deep-Links für LSP-Clients. JetBrains/Eclipse-Abnahme mit realen Clients und Zielbestand offen. Für Eclipse LSP4E ist Hover grundsätzlich passend; CodeLens, `workspace/executeCommand` und externes Öffnen über `window/showDocument` müssen in der konkreten Eclipse-Version geprüft werden. Falls CodeLens/Commands dort nicht nutzbar sind, Eclipse-Plugin mit Secure-Storage-Einstellungen und Browser-Command als native Integration ergänzen. Einrichtung: `ide/README.md`. |

## P2 – Pilot- und Mainframe-Fähigkeit

### Agenten- und MCP-Nutzbarkeit

Die folgenden Punkte stammen aus den bisherigen Agenten-Benchmarkläufen. Sie
sind Hypothesen zur Verbesserung der Werkzeugnutzung; ein Laufzeit- oder
Qualitätsvorteil gilt erst nach einer passenden Vergleichsmessung als belegt.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 77 | O-342 | MCP-Recherche über Projekt, Code-Entität und Call-Flow in weniger Agentenschritten ermöglichen. | **Teilabnahme 28.09.2026 mit Qwen `qwen3:32b` als MCP-Client.** Server meldete 7 lesende Tools. `research_project` löste `COPAUA0C.MAIN-PARA` in einem Aufruf mit Root und Call-Flow auf; Qwen berichtete resolved/unresolved korrekt. Für Java brachte `UserServiceImpl.create` `no_exact_match`; der exakte Klassenname lieferte `entry_point_selection_required` und Methodenkandidaten. Normale gleichlautende C1-Antwort: 75,5 s, 1 lokaler Toolschritt, unbelegt/`sources=[]`; erfolgreicher semantisch gleicher MCP-Fall: 65,0 s, korrekte Kantenbelege. Der wortgleiche MCP-A/B-Versuch endete mit HTTP 524, Retry ohne Toolaufruf; strikter A/B daher unvollständig. Java-Methode muss separat über Entity-ID verfolgt werden. **Ergänzung Codex-Benchmark 28.09.:** Natürlichsprachliche Incident-Frage an `research_project` ergab `no_exact_match`; Symbolsuche und inhaltliche Recherche explizit unterstützen. Projekt-/Quellenfokus, Klassenmethoden und Überladungen gezielt auflösen; passende Einstiegskandidaten, Flow und Originalbelege gebündelt liefern, bei Mehrdeutigkeit keine automatische Zufallsauswahl. Abnahme an Syncope-Pull/Create und CardDemo-Incident: weniger notwendige Agentenaufrufe bei gleicher oder besserer fachlicher Abdeckung (O-351/O-354). |
| 78 | O-343 | COBOL-Programmeinstieg und interne Paragraphen für Call-Flow-Abfragen nachvollziehbar auflösen. | **Eindeutigen Einstieg live bestanden; Grenzfälle offen.** Qwen rief `get_call_flow(project_id=1247, entity_id=121997)` auf. Ergebnis `entry_resolution=unique_cobol_entry`, Root `COPAUA0C.MAIN-PARA` (Zeile 220), 7 Knoten/8 Kanten, kein Kürzen. Qwen gab den Wert unverändert wieder. Mehrdeutiger und fehlender Einstieg wurden nicht am Bestand geprüft. |
| 79 | O-344 | Begrenzte MCP-Graphantworten mit Umfang und Fortsetzungshinweisen erklären. | **Teilabnahme mit Fehlerfund.** Qwen rief `get_graph_neighbors` mit Limit 3 auf, bekam `has_more=true` und Cursor `3`; nach einem absichtlich ungültigen `abc123`-Cursor (MCP antwortete `invalid cursor`) nutzte es Cursor `3` und erhielt Cursor `6`. Beide gültigen Seiten hatten 1 Dateiknoten, 0 Kanten und weiterhin `has_more=true`. Qwen ließ den Zwischenfehler in der Zusammenfassung aus. Seitenfortsetzung funktioniert; aussagekräftige Nachbarschaft/Edge-Befunde sind am COBOL-Fall nicht bestätigt. **Ergänzung Codex-Benchmark 28.09.:** `get_call_flow` meldet Kürzung, aber `next_cursor=null`; auch dieser Pfad benötigt tatsächlich nutzbares Nachladen oder eine konkrete fokussierte Folgeabfrage. Einheitlicher Begrenzungs-/Fortsetzungsvertrag auch für den in `research_project` eingebetteten Flow; Sicherheits- und Quellenfilter erhalten. Relevanzauswahl separat in O-350. |
| 80 | O-345 | MCP-Verfügbarkeit und tatsächliche Werkzeugnutzung vor Agentenläufen messbar machen. | **Teilabnahme 28.09.2026.** MCP `tools/list` meldete 7 Tools; Admin-Audit protokollierte die gezielten Toolaufrufe als `success`, den ungültigen Cursor als `error` (ValueError, 1 ms). Anfrage ohne Token erhielt HTTP 401. In den Doctus-Chatläufen bleibt der optionale MCP-Preflight `not_configured`; „available but not called“ wurde deshalb nicht im Chat-Agentenpfad abgenommen. Temporärer Admin-Testtoken nach der MCP-Abnahme widerrufen. **Ergänzung Codex-Benchmark 28.09.:** 99 MCP-Aufrufe, davon 3 ungültige `direction=downstream` im selben Lauf; Enum-Schema nach dem Benchmark korrigiert (Commit `dc6e635`), kein offener Implementierungsauftrag dafür. Vor Folgemessung ausgeliefertes Schema prüfen. Pro Aufruf Dauer, Ergebnisumfang, Kürzung, Auflösungsstatus und Fehler erfassen; Serverzeit und zusätzliche Agentenschritte getrennt auswerten (O-354). |

### Mainframe-/COBOL-Kompatibilität

Die detaillierten Abnahmeregeln stehen in
[MAINFRAME_KOMPATIBILITAET.md](MAINFRAME_KOMPATIBILITAET.md).

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 51 | O-117 | Zielumgebung mit Compiler, Format, CCSID, Bibliotheken, SCM und Subsystemen erfassen. | Kundenangaben; Vorlage sofort möglich. |
| 52 | O-129, O-134 | Versioniertes Mainframe-Manifest und belastbare Dateiklassifikation einführen. | Vor nativen Importadaptern. |
| 53 | O-130 | Gemeinsamen Vertrag für lesende Mainframe-Exporte festlegen. | O-042 und O-117. |
| 54 | O-135, O-137 | Compilergetreue Copybook-Suchfolge und variantenabhängige transitive Invalidierung abschließen. | Buildprofil und Manifest. |
| 55 | O-139, O-140 | Benötigte COBOL-Sprachmerkmale, Programm-/Entry-/Aliasauflösung und dynamische Calls absichern. | Reale Kundenfixtures. |
| 56 | O-141, O-142, O-143 | Benötigte SQL-, CICS- und IMS/DL-I-Varianten samt Metadaten prüfen. | Mit O-306/O-307 bündeln. |
| 57 | O-145, O-146, O-147 | JCL/PROC, Build-/Binder-Manifest und Program-Dataset-Zuordnung strukturieren. | Bestätigte Umfangserweiterung. |
| 58 | O-149 | Externe Sprachgrenzen und Symbol-/Build-Mappings im Graph erhalten. | Nur belegte Ziele auflösen. |
| 59 | O-151, O-152 | Preflight, Profilimport/-export, Offline-Weg, Auth, CA und Teilberechtigungen absichern. | Zielumgebung und Importweg. |
| 60 | O-153, O-154 | Ressourcenverbrauch und Analysequalität am Kundenbestand messen. | Repräsentative Stichprobe. |
| 61 | O-155, O-156 | Dialekterweiterung, Generatorstände, Provenienz und CI reproduzierbar dokumentieren. | Nach erstem zusätzlichen Kundenprofil. |
| 62 | O-313 | EBCDIC-Datendateien optional, kontrolliert erschließen. | CardDemo-Dateien unter `app/data/EBCDIC/` bleiben aktuell korrekt als Nicht-UTF-8 übersprungen. Erst bei fachlichem Bedarf CCSID, Record-Format (FB/VB, LRECL) und Zweck je Dataset belegen; dann einen Decoder für lesbare Daten-/Testfallansichten ergänzen. Daten niemals als COBOL-Quellcode parsen oder daraus unbelegte Kontrollfluss-/Strukturkanten ableiten. |
| 63 | O-329 | Strukturparser für JCL-Jobs, Steps, PROC-Aufrufe und DD-Datasets implementieren. | Parser, lokale/cross-file Zielauflösung, IDE-Referenzen und Call-Flow-Anbindung implementiert. `DISP`-basierte `READS`/`WRITES` bleiben ausdrücklich als mögliche Zugriffe markiert; Corpus-Abnahme mit repräsentativen JCL/PROC-Dateien bleibt offen. |
| 64 | O-330 | Native EBCDIC-Quelltextautokonvertierung für Host-Dateien und Copybooks umsetzen. | Automatische CCSID-Erkennung (z. B. IBM-273 / 1141) und transparenter Decoder im Connector-Vorlauf, um manuelle Vorabkonvertierung von Mainframe-Quellen zu vermeiden. |
| 65 | O-337 | Subsystem- und Schnittstellenbeziehungen für Assembler, PL/I und dynamische CICS-Links erfassen. | Auflösung von `EXEC CICS LINK/XCTL PROGRAM(...)`-Zielen und Erfassung von Aufrufen zu externen Assembler-Makros bzw. PL/I-Modulen mit explizitem Unresolved-/Dynamic-Status. |

### On-Prem-Deployment und Zielbestand

Details und Checkboxen stehen ausschließlich in
[ONPREM_TEST_READINESS.md](ONPREM_TEST_READINESS.md).

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 62 | O-200–O-215 | Zielhost, Netzwerk, Remote-Modelle, Pilotdaten, Verantwortungen und Betriebsvarianten verbindlich klären. | Kunde/Betreiber. |
| 63 | O-216–O-227 | Remote-/Offline-Compose, Installer, Modellkonfiguration, CA, Updates, Backup und Lieferpaket produktionsfest machen. | Ergebnisse aus O-200–O-215. |
| 64 | O-228–O-239 | Offline-Generalprobe auf leerem Zielhost durchführen und exakt das geprüfte ZIP freigeben. | O-216–O-227; separate Testmaschine. |
| 65 | O-240, O-241 | Bestandssteckbrief und vollständigen Git-/Snapshot-Importweg absichern. | Pilotbestand. |
| 66 | O-246 | Framework-Einstiegspunkte und Konfiguration nur bei belegtem Pilotbedarf verbinden. | Nach Java-Grundabnahme. |
| 67 | O-251 | Remote-Qwen-Embedding-Vertrag live abnehmen. | Der konfigurierte Host lieferte zuletzt 404; Betreiberaktion nötig. |
| 68 | O-252 | Fingerprint-/Reembedding-Verhalten vollständig gegen PostgreSQL abnehmen. | Isolierte Integrationsumgebung. |
| 69 | O-157 | Vollständigen Offline-Installationslauf mit aktuellem Versionsstand wiederholen. | Bewusst vorgemerkt; erst mit freigegebener Testinstanz ausführen. |
| 70 | O-333 | Gehärtete Kubernetes- und OpenShift-Helm-Charts für Enterprise-Bereitstellung erstellen. | Bereitstellung der Compose-Dienste als standardisierte Helm-Charts mit Non-Root SecurityContext, ServiceAccounts, NetworkPolicies und persistenten StorageClasses für Air-Gapped K8s/OpenShift-Cluster. |
| 71 | O-334 | Inkrementelle Delta-Offline-Bundles für wartungsarme Air-Gap-Updates einführen. | Skript und Spezifikation für differenzielle Update-Archive (nur geänderte Container-Layer, DB-Migrationen und App-Assets) zur Vermeidung wiederholter 5-GB-Volltransfers. |
| 72 | O-335 | Ressourcen-Governance und Quoten-Management (Multi-Team / Multi-Projekt) umsetzen. | Durchsetzung konfigurierbarer Quoten für Festplattenplatz, Repository-Anzahl und Inferenz-Slots pro Benutzer/Team gemäß `OPERATIONS_LIMITS.md`. |

### Introduce vLLM next to Ollama (High-Throughput Inferenz)

Ollama bleibt der standardmäßige, vorkonfigurierte Container für lokale Entwicklung, CPU-only-Umgebungen und den Offline-Standby auf Machine A. Parallel dazu wird **vLLM neben Ollama** als optionale High-Throughput-Inferenzoption für dedizierte Enterprise-GPU-Umgebungen (Machine B) eingeführt, um PagedAttention, Continuous Batching, Tensor Parallelism und Automatic Prefix Caching (APC) für parallele Mehrbenutzerlasten bereitzustellen.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 73 | O-338 | Introduce vLLM next to Ollama: Inferenz-Backend für Chat und Tool-Calling zertifizieren. | vLLM-Profil, `/health`-/`/v1/models`-Prüfung, nativer Tool-Calling-Probe und GPU-/KV-Cache-Kapazitätsfehler umgesetzt. Live-Abnahme mit vLLM und Qwen 2.5 Coder (14B/32B/72B) auf GPU-Host bleibt offen. |
| 74 | O-339 | Introduce vLLM next to Ollama: Prompt-Prefix-Stabilität für Automatic Prefix Caching (APC) optimieren. | System-Prompt, Tool-Definitionen, Sicherheitsanweisungen und statischen Projekt-/Quellenkontext im Chat-Agenten deterministisch an den Anfang des Prompts stellen (strikte Trennung von statischem Prefix und variablem Chatverlauf/Fragetext). Dadurch erreicht vLLM maximale KV-Cache-Wiederverwendung und senkt die Time-to-first-token (TTFT) bei paralleler Nutzung auf wenige Millisekunden. |
| 75 | O-340 | Introduce vLLM next to Ollama: Admission-Control & Concurrency-Skalierung auslegen. | In `inference_admission.py` dynamische Slot-Zuweisung je nach Backend-Typ implementieren: Erkennung von vLLM-Endpoints zur Freigabe höherer Nebenläufigkeitsgrenzen (`INFERENCE_MAX_CONCURRENCY` 16–32 statt 4 bei Ollama) dank Continuous Batching und PagedAttention; getrennte Kontingente für Chat-Streaming und Embeddings. |
| 76 | O-341 | Introduce vLLM next to Ollama: Bereitstellungsprofil & Helm-/Compose-Option für Enterprise-GPU-Hosts (Machine B) liefern. | Dokumentiertes und versioniertes `docker-compose.vllm.yml` sowie Helm-Subchart für Machine B mit Tensor Parallelism (`--tensor-parallel-size`), AWQ/FP8-Quantisierung und vLLM-Image zur Bereitstellung auf Nvidia A100/H100/RTX 6000 Ada als performante Alternative zum Ollama-Host. Dokumentation in `REMOTE_INFERENCE.md` erweitern. |

## P3 – Entscheidung oder bestätigter Bedarf

| Rang | ID | Entscheidung / möglicher Folgeschritt | Auslöser |
|---:|---|---|---|
| 70 | O-001 | Formale Lasttest-Abnahme mit repräsentativem DRV-COBOL-Bestand. | Bestand und Abnahmekriterien von Fujitsu/DRV. |
| 71 | O-002 | Formale BITV-Abnahme organisieren. | Auftraggeber/Prüfstelle. |
| 72 | O-003 | Fujitsu-Farbkontraste prüfen und Design-Tokens gegebenenfalls ändern. | Markenfreigabe. |
| 73 | O-007 | CSV-Unterstützung bestätigen oder als veraltet schließen. | Fachliche Entscheidung. |
| 74 | O-008 | Ollama-Strategie für CI festlegen. | Teamentscheidung und CI-Ressourcen. |
| 75 | O-033 | Schutzbedarf von Chat-Metadaten und Feedback klären; bei Bedarf verschlüsseln. | Datenschutz-/Fachentscheidung. |
| 76 | O-035 | Prozessglobale Modellwahl auf Profil-/Request-Scope umstellen. | Nur bei relevantem Mehrmandantenbetrieb. |
| 77 | O-042 | Endevor-/Git-Bridge-Importweg festlegen. | Kundenumgebung. |
| 78 | O-043 | Datenbankumfang festlegen und Connector/Resolver zuschneiden. | Schema-Metadaten versus Laufzeitdaten. |
| 79 | O-045–O-049 | SharePoint-, S3-, ServiceNow-, GitHub-/GitLab-Issue- und Teams/Slack-Anbindungen einzeln nach Pilotbedarf priorisieren. | Bestätigter Zielkundenbedarf. |
| 80 | O-050 | Benötigte Ausschreibungsnachweise, Pentest und Whitepaper festlegen. | Vertrieb/Zielausschreibung. |
| 81 | O-051 | Installer/Wizard, Upgrade-Pfad und Lizenzmodell für breiteren Vertrieb liefern. | Mehr als vereinzelte Pilotkunden. |
| 82 | O-074 | Vision-Modell/Bildbeschreibung oder dauerhaften Bild-Skip entscheiden. | Fachliche Entscheidung. |
| 83 | O-161 | RP-initiated OIDC-Logout ergänzen. | IdP-Anforderung und ID-Token-/`sid`-Strategie. |
| 84 | O-163 | SSO-Sitzungsdauer und erneute IdP-Prüfung festlegen. | Sicherheitszusage des Betreibers. |
| 86 | O-172 | Interviewbasierte Wissensquelle mit zwingender menschlicher Freigabe zuschneiden. | Fachliche Priorisierung. |
| 87 | O-173 | Keyword-/Volltext-Fallback unter Verschlüsselung evaluieren. | Belegter Recall-Fehler. |
| 88 | O-174 | Strukturtreue PDF-Extraktion evaluieren. | Belegter Qualitätsfall mit komplexen PDFs. |
| 89 | O-328 | Pre-Commit- & CI-Impact-Analyse CLI für Entwickler-Workstations liefern. | Standalone-CLI/Hook zur schnellen lokalen Überprüfung von Git-Diffs gegen den Doctus-Callgraphen mit Ausgabe des betroffenen Explosionsradius vor dem Commit. |
| 90 | O-332 | Persistentes RAG- und Erklärungs-Caching im Wissensgraphen evaluieren. | Wiederkehrende Erklärungen zu Modulen, Paragraphen und Datenstrukturen persistent als Graph-Knoten ablegen, um lokale Inferenz-Slots nachhaltig zu entlasten. |

## Bewusst zurückgestellt

| ID | Punkt | Wiederaufnahme |
|---|---|---|
| O-006 | Git-Performance mit `repack`/`fetch --refetch` messen. | Nach providerübergreifender GitHub-/Bitbucket-Absicherung und an einem großen Bestand. |
| O-089 | Lokales Fine-Tuning aus Chatfeedback. | Erst bei ausreichendem Volumen und ausdrücklicher Kundenzustimmung. |
| O-128 | Native Mainframe-Rekordformate. | Sobald ein nativer Mainframe-Connector statt normalisierter Git-Texte existiert. |
| O-131–O-133 | Native z/OS-/BS2000-/SCM-Adapter. | Erst nach O-042/O-130 und belegter Lücke in vorhandenen Export-/Git-Bridges. |
| O-144 | Weitere Mainframe-Subsysteme wie openUTM, UDS, SESAM, Adabas, IDMS oder MQ. | Je bestätigtem Zielsystem ein eigenes Folge-Ticket. |
| O-148 | Scheduler-, SDF- und Utility-Steuerkarten. | Nach O-117 anhand eines konkreten Exportformats. |
| O-158 | Upgrade von `mcp-atlassian`/`fastmcp`. | Nach OSS-Freigabe der MPL-2.0-Transitive `orjson` und `pathspec`. |
| O-166 | Serverseitige Link-Manager-Pagination. | Bei fünfstelliger Linkmenge oder wieder spürbarer Ladezeit. |
| O-316 | Chat-Startpfad unter Importlast verschlanken. | Zurückgestellt: Chat-Reserve und Fair-Batching aus O-314 verhindern Slot-Blockaden bereits effektiv; heuristische Smalltalk-Trennung birgt Fehlklassifikationsrisiko bei minimalem Latenzgewinn. |
| O-326 | Deterministische Unified-Diff- & Patch-Vorschläge. | Zurückgestellt: Produkt bleibt strikt rein lesend/analysierend; vorerst keine Codegenerierung. |
| O-327 | Automatische Testfall- und Testtreiber-Generierung. | Zurückgestellt: Fokus liegt auf Code-Verständnis und Navigation, vorerst keine Codegenerierung. |
| O-331 | Leichtgewichtiges CPU-Coder-Modell für reine CPU-Hosts. | Zurückgestellt: CPU-only Inferenz wird nicht verfolgt; GPU-Inferenz ist für produktiven Chatbetrieb gesetzt. |
| O-336 | Automatisierter Living-Documentation-Export ins Repository. | Zurückgestellt: Doctus schreibt keine generierten Dokumentationsdateien in Kunden-Repositories. |

## Pflege

- Neue Aufgaben erhalten die nächste freie O-Nummer und werden sofort in eine
  Priorität und Rangfolge einsortiert.
- Teilweise umgesetzte Punkte bleiben aktiv, bis ihr offener Abnahmeschritt
  nachgewiesen ist.
- Nach Abschluss wird der Punkt aus dieser Datei entfernt; dauerhafte
  Architekturentscheidungen gehören in [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md),
  fachliche Detailnachweise in die jeweils verlinkte Dokumentation.
