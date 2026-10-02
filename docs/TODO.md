# Doctus – priorisierte TODO-Liste

Stand: 02.10.2026

Diese Datei ist die kanonische Liste der noch offenen Arbeit. Die Reihenfolge
innerhalb einer Priorität ist zugleich die empfohlene Ausführungsreihenfolge.
`teilweise` bedeutet, dass der verbleibende Abnahmepunkt weiterhin offen ist.
Erledigte Punkte stehen nicht mehr im aktiven Backlog; ihr Nachweis bleibt in der
Git-Historie und in den verlinkten Fachunterlagen erhalten.

**MCP-Sicherheitsprüfung vom 24.09.2026:** Die zwei reproduzierten Befunde zu
Projektisolation der Wissenssuche und unbeschränkter Call-Flow-Abfrage wurden
behoben; 27 isolierte Sicherheitsprüfungen sowie 9 MCP-Regressionen bestanden.

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
| 2 | O-350 | Relevante MCP-Graphpfade unter Antwortlimits erhalten und redundante Zugriffe bündeln. | **Teilweise umgesetzt; semantischer Fragefokus und End-to-End-Abnahme offen.** `get_call_flow` paginiert sichtbare Kanten jetzt mit einem an Anfrageparameter gebundenen Cursor; Folgeseiten erhöhen bei Bedarf die Traversierungsgrenzen bis maximal 1.000 Knoten/3.000 Kanten. Seiten bewahren BFS-Kantenreihenfolge, ACL-gefilterte Mengen werden getrennt von Antwort-/Traversierungslimits ausgewiesen. Die Auswahl priorisiert noch nicht nach Fragefokus innerhalb der fachlichen Kanten. Getter, Logging und wiederholte Feldzugriffe bei Bedarf kompakt gruppieren. Abnahme prüft Connector-Aufruf, Token-Persistenz und Fehlerbehandlung sowie deterministische Seiten, sichtbare Auslassungen und Fortsetzung innerhalb fester Budgets. |
| 3 | O-351 | MCP-Suche und Call-Flow mit direkt nutzbaren Originalbelegen ausstatten. | **Quellbelege umgesetzt; Kontext-/End-to-End-Abnahme offen.** `search_code` gibt Chunk-ID und gelieferte Zeilen aus; `get_code_entity` liefert mehrere Originalchunks unter Budget und paginiert mit `next_chunk_id`/`next_char_offset`. `get_call_flow` liefert optional pro Kante einen kleinen, zeilenzentrierten Originalauszug mit Chunk-ID, tatsächlichem Zeilenbereich und `get_code_entity`-Folgeaktion; ACL wird vor der Quellabfrage geprüft und Flow-Seitenbudget begrenzt die Belegmenge. Bedingungs- und Fehlerpfade über mehrere Kanten hinweg sowie `trace_data_access`-Kürzung sind nicht vollständig abgedeckt. End-to-End-Abnahme muss Belegdeckung, ACL, Gesamtbudget und lokale Ersatzlesevorgänge prüfen. |
| 4 | O-352 | Java-Aufrufketten anhand belegter Rückgabetypen auflösen und Auflösungsgründe über MCP erhalten. | **Parser-Fix umgesetzt, Reindex/Bestandsabnahme offen.** Deklarierte Rückgabetypen eindeutiger innerer Methodenaufrufe speisen die Auflösung äußerer Java-Receiver; MCP liefert erlaubte Ziel-/Receiver-Evidenz aus. Parser-Regression: `test_chained_call_receivers_resolve_from_declared_method_return_types`. Im Pull-Rohgraph bleiben unter anderem `pullTask.getResource().getPullPolicy()` und weitere verkettete Receiver unaufgelöst. Zunächst je Referenzfall Parserextraktion, Resolver, Persistenz, Indexrevision und MCP-Projektion getrennt prüfen; sichere Rückgabetypketten einschließlich belegbarer Generics/Vererbung ergänzen. Statische Deklaration und mögliche Laufzeitimplementierung unterscheiden; Mehrdeutigkeit bleibt sichtbar. Abnahme nach Reindex an Syncope und einem unabhängigen Mehrdateifall; Negativfälle dürfen keine erfundenen Ziele erhalten. MCP liefert vorhandene Receiver-Evidenz, Auflösungsgrund und Dispatch-Grenzen mit. |
| 5 | O-353 | Begrenzte Datenflussanalyse mit Reihenfolge und Bedingungen für Incident-Fragen liefern. | **Teilweise umgesetzt.** `trace_data_access` listet begrenzte, indexierte `READS`/`WRITES` mit Zeilen und ACL-geprüftem Quellabschnitt in Quellreihenfolge. COBOL-XREF ordnet Referenzen in `MOVE`, `ADD`, `SUBTRACT`, `COMPUTE`, `SET`, `READ`, `WRITE`/`REWRITE`, `DISPLAY` und Kontrollbedingungen jetzt Operandrollen und Richtungen zu; IF-/EVALUATE-Kontexte werden an den Kanten erhalten. EXEC CICS `READ INTO`/`RESP` werden als Schreibzugriffe und IMS `ISRT FROM` als Lesezugriff an Datenentitäten projiziert. Pfadsensitive Werte-/Kontrollflussanalyse, Paragraphenübergänge, weitere EXEC-Parameterrollen und CardDemo-Abnahme bleiben offen. Die CardDemo-Rubrik verlangt unter anderem Befüllung/Verwendung von `PA-TRANSACTION-AMT`, XREF-Bedingung des Schreibpfads und fehlende Balancekorrektur im Batch. Fehlende Indexkante darf nicht als Beweis eines fehlenden Schreibzugriffs gelten; Aussagen über ausbleibende Korrekturen benötigen vollständig untersuchten, ausgewiesenen Quellumfang. |
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
| 2 | O-356 | Beleg- und Datenzugriffswerkzeuge aus Such-/Flow-Ergebnissen gezielt erreichbar machen. | **Werkzeughinweise und budgetierte Folgeaktionen umgesetzt; End-to-End-Abnahme offen.** `search_code` bietet für Treffer `get_code_entity` und bei Datenentitäten optional `trace_data_access` mit gültigen, begrenzten Argumenten an. `research_project` schlägt bei eindeutigen Symbolen den Quellenabruf und bei leeren Symboltreffern eine `search_knowledge`-Suche vor. `get_code_entity` liefert eine Fortsetzungsaktion mit Chunk-Cursor. Abnahme muss zeigen, dass Incident-Fragen die Belege auch tatsächlich abrufen und lesen; Toolzahl, lokale Ersatzlesevorgänge, Antwortumfang, Qualität und Gesamtzeit vergleichen. |
| 3 | O-357 | Java-Methodenkontext für Argumente, Rückgaben und Transaktionsdeklarationen belegbar liefern. | **Teilweise umgesetzt; Laufzeitabgrenzung und End-to-End-Abnahme offen.** Java-Entities erfassen jetzt Annotationen mit Attributwerten als Quellausdrücke, Methoden-Rückgabeausdrücke mit Zeilen sowie begrenzte CALLS-Argumentausdrücke. `search_code`, `research_project`, `get_code_entity` und Call-Flow geben diese strukturierten Belege aus. Ausdrücke sind statische Quellbelege; sie lösen keinen Wertefluss auf und beweisen keine Proxy-/Laufzeitwirkung. CREATE/UPDATE- und unabhängige Java-Abnahme stehen aus; Overloads, Annotationen oberhalb des Methodenbereichs und Delegation explizit prüfen. |
| 4 | O-358 | MCP-Mehrkosten und leere bzw. doppelte Recherche getrennt messen und reduzieren. | **MCP-Telemetrie teilweise umgesetzt; Benchmark-Abnahme offen.** Toolaudits erfassen bereits monotone Serverdauer und speichern jetzt zusätzlich die serialisierte Resultat-Payloadgröße als Proxy, Kürzungsstatus und einen Fingerprint der Projekt-Varianten, ohne Antwortinhalte abzulegen. Die Instrumentierung umfasst Such-, Flow-, Entity-, Datenzugriffs- und Knowledge-Tools. `research_project` gibt den Flow direkt zurück und bietet als Folgeaktion Quellenlesen statt eines redundanten identischen Flow-Aufrufs an. Trennung von Modellzeit, lokalen Leseaufrufen und Antworttokens sowie Messung leerer/doppelter Aufrufe bleiben offen. Abnahme an archivierten Anfragefolgen und vorregistrierten neuen Paaren; keine Latenzzusage und kein Cache ohne Berechtigungs-, Varianten- und Revisionsbindung. |

Bestehende Tickets bleiben die Eigentümer der folgenden Restarbeiten; keine
zweiten Implementierungstickets für dieselbe Lücke anlegen:

- **O-350 – Graphfortsetzung und Relevanz:** Kapitel 2 enthält 8 gekürzte
  `get_call_flow`-Antworten unter 33 Aufrufen und 4 Fälle
  `entry_point_selection_required`. `get_call_flow` paginiert sichtbare Kanten
  jetzt über Folgeseiten und erhöht die Dienstgrenzen pro Seite bis maximal
  1.000 Knoten/3.000 Kanten. Die aktuelle Auswahl priorisiert Kantenarten,
  Auflösungsstatus und Quellzeilen, aber noch nicht den fachlichen Fragefokus.
  Auswahl vom Einstieg und relevanten Pfaden her weiter schärfen. Kürzung durch
  Budgets und durch Sichtbarkeitsfilter werden mit getrennten Statusfeldern
  ausgewiesen, ohne verborgene Daten zu zählen oder zu benennen.
- **O-351 – Originalbelege:** `search_code`/`get_code_entity` schneiden Text nach
  1600 Zeichen ab, `trace_data_access` nach 1200, während `end_line` weiterhin
  die Chunk-Grenze bezeichnet. Der Such-/Entity-Pfad weist Chunk-IDs und
  gelieferte Zeilenbereiche inzwischen aus und erlaubt Chunk-Fortsetzung.
  `get_call_flow` liefert nun optional zentrierte Quellzeilen pro Kante und eine
  Chunk-Folgeaktion. Offen bleiben die End-to-End-Prüfung der Aussageabdeckung,
  mehrkantige Bedingungs- und Fehlerpfade sowie die 1200-Zeichen-Kürzung von
  `trace_data_access`.
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

### MCP-Folgearbeiten aus Kapitel 3 des Codex-Benchmarks (29.09.2026)

Review des letzten vollständigen Laufs `official_luna_benchmark_chapter3`
(60 Sitzungen, 30 Paare, bestehender Index ohne Reindex). Rohbewertung:
127/235 Punkte ohne und 157/235 mit MCP (54,0 % / 66,8 %), medianer gepaarter
Mehraufwand mit MCP 6,1 s; 14/30 Paare schneller. Die Einzelbewertung ist nicht
verblindet und enthält belegte Zitier-/Bewertungsprobleme; daraus keinen
kausalen Qualitätsgewinn oder Rückschritt gegenüber Kapitel 2 ableiten.
Die folgenden Zeilen konkretisieren bestehende Tickets; nur O-370 ist neu.
Die Rangfolge gilt innerhalb dieses Review-Pakets.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 1 | O-355 | Java-Symbolnormalisierung bereits bei der Kandidatensuche anwenden und echte Signaturen erhalten. | **Offen, konkreter Codebefund:** `research_project` übergibt `Class.method` unverändert an `search_nodes`; der Parser speichert `Class#method(...)`. Die spätere Normalisierung in `_symbol_matches` kann fehlende Kandidaten nicht reparieren und verwirft zudem Parameterlisten. UPDATE, CREATE und PULL zeigen leere Methodensuchen. Begrenzte owner-/method-/signaturbezogene Suche vor dem Kandidatenlimit ergänzen; Komma außerhalb von Signaturen als Listentrenner behandeln. Abnahme: `UserServiceImpl.update(UserTO)` / `update(UserPatch)` unterscheiden, `UserLogic.create` und `PullJobDelegate.doExecuteProvisioning` finden; ohne Signatur Mehrdeutigkeit bewahren, ACL/Quelle/Variante beachten. |
| 2 | O-342, O-355 | Fachliche Fragen zuverlässig von expliziten Symbollisten unterscheiden. | **Update 30.09.2026 (Code):** Freitext mit Schrägstrich wie `approval/decline` wird nicht mehr in Einzelwörter zerlegt (nur symbolartige Teile bilden eine Symbolliste); ohne exakten Treffer bietet `research_project` `search_code` und `search_knowledge` als Folgeaktion an. Abnahme am echten Incident-Fall offen. **Offen:** Vier Incident-Aufrufe liefern keine exakten Treffer; Freitext mit `approval/decline` wird sogar in acht Einzelwörter zerlegt. Symbol- und Inhaltssuche explizit unterscheidbar machen, Prosa nicht allein wegen `/` oder `.` tokenisieren. Freitext begrenzt in Code-/Wissensretrieval überführen; unbekanntes Symbol nicht als fehlenden Code ausgeben. Die vier archivierten Incident-Anfragen plus unabhängige Prosa-/Pfad-/Symbollistenfälle prüfen. |
| 3 | O-370 | MCP-Eingabegrenzen und korrigierbare Cursorfehler im öffentlichen Werkzeugvertrag ausdrücken. | **Update 30.09.2026 (Code):** `get_call_flow` weist `hops` (0–3), `page_size` (1–15) und die unveränderte Cursor-Übernahme im Schema aus; fehlerhafte oder abfragefremde Cursor liefern eine Wiederholungsanweisung. Die Cursorbindung ist nicht gelockert. Abnahme über echten `_tool_context` mit Auth-/ACL-Fehlern offen. **Neu, P1.** 24 Flow-Anfragen überschreiten `page_size=15`, 17 MCP-Anfragen `hops=3`; derzeit stille Begrenzung. Grenzen im Schema und in Beschreibungen ausweisen. Zwei Agenten veränderten den gelieferten Cursor (`include_source` wurde `nclude_source`); der Server meldete irreführend `MCP request failed or access denied`, da sein Validierungsfehler nicht freigegeben ist. Sicheren Eingabefehler samt Wiederholungsanweisung ausgeben; Cursor unverändert aus der Folgeaktion übernehmen lassen. Abnahme über echten `_tool_context`: unveränderter Cursor erfolgreich, veränderter/abfragefremder Cursor verständlich abgewiesen; Auth-/ACL-Fehler bleiben ohne Datenleak. Keine Lockerung der Cursorbindung. Ergänzt O-344/O-350. |
| 4 | O-350, O-351, O-356 | Vollständige Quellen- und Flow-Fortsetzung in der tatsächlichen Agentennutzung abnehmen. | **Update 30.09.2026 (Code):** `get_code_entity` setzt mit `chunk_id` in der geordneten Chunkliste fort und verliert keine späteren Chunks mehr (Test über vier Chunks); `research_project` nutzt für eindeutige Treffer denselben paginierten, ACL-gefilterten Call-Flow mit Quellbelegen wie `get_call_flow`. Abnahme in der Agentennutzung offen. **Offen:** 25/41 erfolgreiche Flow-Antworten sind gekürzt, 20 bieten weitere Seiten; nur fünf erfolgreiche Cursoranfragen. Kein einziger `get_code_entity`- oder `trace_data_access`-Aufruf bei 119 MCP-Aufrufen. `research_project` verwendet direkt `trace_call_flow` und umgeht die Beleg-/Pagination-Projektion von `get_call_flow`. Beide Einstiegspfade auf denselben begrenzten Antwortvertrag bringen; fehlende Bedingungs-, Rückgabe- und Fehlerbelege gezielt nachladen. Zusätzlich Quellpagination über mindestens drei Chunks prüfen: Bei gesetzter `chunk_id` liest `get_code_entity` derzeit nur diesen einen Chunk und kann nach dessen Rest spätere Chunks verlieren. Akzeptanz: vollständige, duplikatfreie Fortsetzung oder explizite Abdeckungsgrenze, ACL und Gesamtbudget erhalten. |
| 5 | O-251, O-345, O-356 | Embedding-Ausfall vor semantischen Folgeaktionen erkennen und nutzbaren Ersatzweg liefern. | **Update 30.09.2026 (Code):** `search_knowledge` fällt bei Embedding-Ausfall auf eine begrenzte, projektgebundene Schlüsselwortsuche zurück (`retrieval_mode: lexical_fallback`, ehrlicher Hinweis; Chunk-Inhalte sind verschlüsselt, daher Scan von höchstens 3000 Chunks in Python). Die Ursache des 404 im Embedding-Profil (Pfad/URL) ist weiterhin nicht geprüft. **Erneut bestätigt:** `CARD-INCIDENT-02_r3_with_mcp` erhält bei `search_knowledge` HTTP 404. Sichtbare MCP-Tools beweisen keine Retrieval-Bereitschaft. Projektgebundenes Embedding-Profil einschließlich Pfad prüfen; bei Ausfall Zustand und begrenzte Code-/Quellensuche anbieten, nicht dieselbe unbrauchbare Folgeaktion wiederholen. Abnahme mit funktionierendem und gezielt nicht verfügbarem Profil; keine erfundenen Treffer, keine fremden Projektinhalte. |
| 6 | O-353 | Incident-Belege für Betragsherkunft, Datumsrekonstruktion und Batch-Nachwirkungen vervollständigen. | **Bestandsabnahme offen:** Alle fünf MCP-Antworten verfehlen Rubrikkriterien 6 und 8 (Summary-Betrag / vollständige Ablaufdatumsregel); vier verfehlen Kriterium 1. In r1 wird der Summary-Zuwachs unbelegt mit 150,00 angesetzt. Zuweisung von `PA-TRANSACTION-AMT`, Verwendung, XREF-Bedingung, Datumsdefault sowie Batch-Abzüge und fehlendes Summary-REPL anhand vollständiger Originalbereiche prüfen. READS/WRITES-Verfügbarkeit und tatsächlich konsumierte Belege getrennt messen; neuer Parsercode ist durch den bestehenden Index nicht automatisch abgenommen. |
| 7 | O-357 | Java-Argumente, Rücklesen, Rückgaben und Transaktionsannotation am CREATE-/UPDATE-Bestand abnehmen. | **Update 30.09.2026 (Parser):** `return_expressions` war bei allen Java-Methoden leer, weil die Grammatik kein `returnStatement` kennt (`return` ist ein `statement` mit Token `RETURN`); behoben, Ausdruckstext behält Leerzeichen. Annotation liegt im Methodenbereich, Overloads bleiben getrennt (Tests `test_java_method_context.py`). Wirkt erst nach Reindex; Bestandsabnahme an CREATE/UPDATE offen. **Offen:** Alle fünf CREATE-MCP-Antworten verfehlen die Kriterien zu `provisioningManager.create`-Argumenten und Rücklesen/`afterCreate`; alle fünf UPDATE-Antworten lassen `REQUIRES_NEW` aus. Quellenpaket muss passenden Overload, Annotation oberhalb der Methode, vollständige Argumente und Rückgabebildung enthalten. Deklaration und tatsächliche Spring-/Laufzeitwirkung weiterhin trennen. Mit O-355/O-351 und passendem Indexstand prüfen; Zitierfehler separat unter O-354 bewerten. |
| 8 | O-354 | UPDATE-Nullbewertungen anhand der Originalantworten unabhängig prüfen und fachliche Richtigkeit von Zitierabdeckung trennen. | **Konkreter Review-Fund:** 8/10 UPDATE-Antworten erhalten 0/7; r2 mit MCP beschreibt trotzdem REST-Diff, beide Overloads, Fehlerreport und Taskversuch. Bei r1 mit MCP wird die `UserPatch`-Delegation als unbelegt abgewertet, obwohl Antwort und Zeilen 81–83 sie ausdrücklich nennen. Originalscores unverändert archivieren; separate Zweitbewertung mit kriteriumsweisem Antwort-/Quellbeleg, Inhaltswert und Zitierwert erstellen. Rubrikmängel vor neuer Messung einfrieren; die vorhandene Kapitel-2-Nachbewertung validiert Kapitel-3-Antworten nicht. |
| 9 | O-358 | Zusätzliche Recherchekosten an CREATE und erfolglosen Methodensuchen messen. | **Offen:** CREATE hat im letzten Lauf median gepaart 90,8 s Mehrzeit mit MCP; UPDATE 18,6 s. Diese Sitzungszeiten sind keine MCP-Serverlatenzen. Lokale Ersatzlesevorgänge, leere Suchen, doppelte Flows, Tool-/Modellzeit und Belegabrufe getrennt auswerten. Nach O-355/O-350/O-356 mit identischen eingefrorenen Aufgaben und zusätzlichen unbekannten Fällen neu messen; Nutzen der Änderungen nicht aus dem Vorher-Nachher-Kapitelvergleich behaupten. |

### Datenverlust bei geteilten Java-Packages behoben (30.09.2026)

`test_t51_integration` schlug zuletzt dauerhaft fehl. Ursache: Der Package-Eintrag
`com.acme` gehört formal der Datei, die ihn zuerst anlegte. Beim Löschen dieser
Datei wurde er auf ein beliebiges anderes Entity umgehängt, auch auf ein
COBOL-Programm; dessen nächster Reparse löschte das Package als veraltet und
kaskadierte über `parent_id` in alle unveränderten Java-Klassen, obwohl deren
Scan-Einträge auf „complete" standen. Behoben mit `rehome_shared_java_container`
(nur Java-Dateien, Kinder bevorzugt; auch bei Package-Wechsel der Ersteller-Datei).
Regressionen: `parser/tests/test_shared_java_container.py`. Offen: Reindex der
Bestandsprojekte, um bereits entstandene Lücken zu schließen.

### Parser-/Indexabdeckung für den MCP-Benchmark (28.09.2026)

Lesender Abgleich des laufenden PostgreSQL-Index (Projekte 1246/1247), der
entschlüsselten Quellchunks und der aktuellen Parser-/MCP-Implementierung.
Zusätzlich `COPAUA0C.cbl` mit dem aktuellen lokalen Parser ausschließlich im
Speicher neu geparst, ohne Import oder Indexänderung. Ergebnis: **Die benötigten
Informationen sind noch nicht vollständig strukturiert oder als Quellchunks
vorhanden.**

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
wo dieselbe Lücke bereits beschrieben ist. Kleine In-Memory-Proben
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
- **O-306/O-307:** EXEC CICS `READ INTO`/`RESP` werden jetzt als Schreibzugriffe,
  IMS `ISRT FROM` als Lesezugriff erkannt und über lokale Datenauflösung mit
  definierten COBOL-Feldern verbunden. In-Memory-Regressions belegen Richtung,
  Parameterrolle und Feldziel. Weitere dialektspezifische Operanden, Status-/
  Fehlerpfade, vorhandene EXEC-Operations-Verknüpfung im Live-Index und reale
  Kundenvarianten bleiben offen; diese Fälle belegen keine vollständige CICS-/IMS-I/O-Semantik.
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
sind zusätzliche, reproduzierte Lücken.

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
| 1 | O-365 | Ausführbare Beziehungen in Lambdas und anonymen Klassen ihrem tatsächlichen Typ-/Methodenkontext zuordnen. | **Abgeschlossen (28.09.2026).** `JavaRelationshipVisitor` in `relationships.py` um Scopes für `visitLambdaExpression` und `visitCreator` (anonyme Klassen) erweitert. Aufrufe in Lambdas erhalten das Lambda als `src_name`. Aufrufe in anonymen Klassenmethoden erhalten die innere Methode als `src_name`. `this.helper()` in anonymer Klasse bindet an die lokale Hilfsmethode der anonymen Klasse; unqualifizierte Aufrufe fallen bei Bedarf lexikalisch auf die äußere Klasse zurück (`resolution.py`). Unit-Tests in `test_java_relationships.py` erfolgreich. |
| 2 | O-366 | Lokale Java-Variablen anhand lexikalischem Block und Verwendungsposition auflösen. | **Scope-basierte Auflösung umgesetzt; gezielte Regression ergänzt, Bestandsabnahme offen.** Lokale Variablen tragen jetzt Block-/`for`-/`catch`-/Lambda-Scope und Deklarationsposition. Der Resolver wählt nur vor der Verwendung deklarierte, dort sichtbare Variablen; innere Scopes und spätere Deklarationen werden berücksichtigt. Regressionen belegen gleiche Namen in getrennten Blöcken, Enhanced-`for`, Catch-Variablen, Lambda-Capture und ungelöste Verwendung vor Deklaration. Verschachteltes Shadowing und Zielbestandsabnahme bleiben offen. Kein globaler Name-only-Fallback. Ergänzt O-309/O-352. |
| 3 | O-367 | Java-Methodenreferenzen auf belegte Zieldeklarationen beziehen. | **Kantenprojektion und eindeutige Zielauflösung umgesetzt; positive und Negativregressionen ergänzt, Bestandsabnahme offen.** Tests belegen `this::m`, `Type::static`, `obj::m` und `Type::new`; Überladungen bleiben mehrdeutig und externe Ziele unaufgelöst. Die Kante bezeichnet eine Methodenreferenz, keinen ausgeführten Aufruf. Generische funktionale Interfaces und externer Classpath bleiben Abnahmepunkte. Ergänzt O-310. |
| 4 | O-368 | Java-Feldzugriffe über andere Repositorytypen sicher auflösen. | **Resolver und gezielte Regression umgesetzt; Bestandsabnahme offen.** Eine Regression belegt READS und WRITES über einen Parameter mit eindeutig aufgelöstem Repositorytyp und Zielfeld. Unqualifizierte Zugriffe sowie `receiver.field` werden im globalen Resolver gegen die belegte Felddeklaration aufgelöst. Vererbung, verdeckte Felder, generische Receiver, gleichnamige Klassen und externe Typen sind noch gegen den Zielbestand abzusichern. Ergänzt O-309/O-310. |
| 5 | O-369 | Java-Ausnahme- und Abschlusswege als begrenzte, belegte Beziehungen erhalten. | **Update 30.09.2026:** Java-Methoden tragen `exception_flow` (throw-Stellen mit konstruiertem Typ oder Ausdruck und Region, catch-Typen, finally, try-with-resources mit implizitem `close()`); MCP gibt das Feld aus. Nicht abgedeckt bleiben Typen dynamisch gefangener/gerouteter Ausnahmen, verschachtelte Semantik und die Impact-Abnahme. **Quellrollen umgesetzt und Try-Erkennung korrigiert; Parserregression ergänzt, Prozess-/End-to-End-Abnahme offen.** Java-Methoden speichern deklarierte `throws`-Typen; CALLS-Kanten erhalten für `try`, `catch(T)` und `finally` Quellrolle und Zeilenbeleg. Regression belegt Try-Body, Catch-Typ, Handler und Cleanup; dabei wurde die Grammatikregel korrekt als `statement` statt `tryStatement` erkannt. MCP zeigt diese Angaben; Process View markiert Handler-/Cleanup-Kanten als `possible`. Dynamisch geworfene Typen, Ressourcen-Close-Wege, verschachtelte Ausnahmefluss-Semantik und Impact-Abnahme bleiben offen. |

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

### Befunde aus der Bestandsprüfung Syncope/CardDemo (02.10.2026)

Lesende Prüfung nach dem Neustart des Syncope-Syncs (Quelle 8, `completed`, 1.940/2.009
Dateien im Delta-Lauf) und des CardDemo-Bestands (Quelle 7, `completed`, letzter Sync
01.10.2026 16:01 UTC) gegen `source_scan_files`, `code_entities` und `code_edges`.
Es wurde nichts verändert. Die Zahlen sind Momentaufnahmen vom 02.10.2026.

| Rang | ID | Ergebnis | Status / Abnahme |
|---:|---|---|---|
| 1 | O-371 | Java-Parser darf bei einem leeren `return;` nicht abbrechen. | **Parser-Fix umgesetzt (02.10.2026), Reindex-Abnahme offen.** Leere Liste bei `return;` wird wie „kein Ausdruck“ behandelt; Regression `test_bare_return_does_not_abort_structure_parsing` (void-Methode, Lambda, `switch`). Alle 60 betroffenen Dateien parsen im Worker nun ohne Fehler. Offen: Reindex von Quelle 8 und Prüfung, dass die Dateien `complete` werden. Ursprünglicher Befund: 60 Syncope-Java-Dateien haben `parse_status=partial` mit `Strukturparser fehlgeschlagen: IndexError: list index out of range` und liegen nur als Textfallback vor, u. a. `RateLimitFilter.java`, `DismissMfa.java`, `CircularFifoQueue.java`, `RealmDirectoryPanel.java`. Im Worker reproduziert: `parser/java/declarations.py:288` in `_return_expressions` greift mit `expression[0]` auf eine leere Liste zu, wenn `node.expression()` bei `return;` `[]` liefert. Alle drei geprüften Dateien enthalten ein leeres `return;`; die übrigen 57 wurden nicht einzeln geprüft. Fix: leere Liste wie `None` behandeln. Regression mit void-Methode und frühem `return;`, auch in Lambda und `switch`. Danach die 60 Dateien reindizieren und prüfen, dass sie `complete` werden und Methoden-/Receiver-Kanten (O-352) erhalten. |
| 2 | O-372 | Strukturparser-Fehler mit Stacktrace protokollieren und im Scan-Eintrag diagnostizierbar machen. | **Umgesetzt (02.10.2026), Fehlerklassen-Zählung in O-380.** `parse_error` nennt jetzt die Fehlerstelle (`Typ: Meldung (datei.py:zeile in funktion)`, `parser/core/failure_location.py`), der Stacktrace steht als Warnung im Worker-Log. Regression: `test_failure_location.py`. Ursprünglicher Befund: `parser/connectors/git.py:721` schreibt nur `Typ: Meldung` in Log und `parse_error`. Der Stacktrace fehlte, deshalb war `IndexError: list index out of range` (O-371) ohne Reproduktion nicht lokalisierbar. Stacktrace im Worker-Log (gekürzt), im `parse_error` Datei/Zeile der Fehlerstelle ergänzen; Fehlerklassen im Diagnosebericht zählen, damit häufige Parserabstürze sichtbar werden. |
| 3 | O-373 | `parse_status` und tatsächlicher Index müssen übereinstimmen. | **Ursache gefunden und behoben (02.10.2026), Reindex-Abnahme offen.** Zwei Fehler: (1) Der Paragraph-`end_line` endete bei der Startzeile der letzten, mehrzeiligen Anweisung (z. B. `EXEC CICS RETURN … END-EXEC`), weil die Grammatik maskierte EXEC-Blöcke als eine Zeile sieht; `divisions.py` nimmt jetzt die physische Endzeile der logischen Zeile. Die angehängten Rest-Chunks (O-359) trugen `fallback`, deshalb stufte `classify_completeness` die ganze Datei als `text_fallback` mit der irreführenden Meldung „Keine PROCEDURE DIVISION gefunden“ ein. (2) `classify_completeness` unterscheidet nun Volltext-Fallback von Lückenchunks: Lücken innerhalb eines `exec_block`/`sql_block` gelten als abgedeckt, echte Lücken führen zu `partial` mit Zeilenangabe. Regressionen in `test_cobol_divisions.py` und `test_analysis_status.py`. Nachweis an den Originaldateien: `COSGN00C` und `COMEN01C` sind jetzt `complete` ohne Fallback-Chunks. Offen: Reindex von Quelle 7 und Prüfung der übrigen 22 Dateien; Dateien mit echten Syntaxfehlern bleiben bei O-374. Ursprünglicher Befund: In CardDemo stehen 27 von 44 COBOL-Dateien auf `text_fallback`, davon 24 mit „Keine PROCEDURE DIVISION gefunden“, darunter Kernprogramme wie `COSGN00C`, `COBIL00C`, `COACTVWC`, `COTRN00C`. Gleichzeitig existieren für sie Struktur-Entities: `COSGN00C` mit 6 Paragraphen, 10 `exec_block` und 14 `data_item`; `COBIL00C` mit 16 Paragraphen; `COACTUPC` mit 85 Paragraphen und 578 `data_item`. Entweder ist der Status falsch gesetzt oder die Entities stammen aus einem früheren Lauf und sind veraltet; beides wäre ein Fehler, weil der Nutzer dem Status vertraut. Zuerst klären, ob die `PROCEDURE DIVISION` tatsächlich nicht erkannt wird (Dialekt/Spaltenformat) und welcher Lauf die Entities erzeugt hat; dann Status, Entities und Chunks konsistent persistieren. Abnahme: Für jede Datei mit Entities steht kein `text_fallback`; umgekehrt keine Entities ohne Parser-Erfolg. Bezug zu O-305. |
| 4 | O-374 | COBOL-Grammatik an belegten Dialektfällen erweitern. | **Umgesetzt (02.10.2026), Reindex-Abnahme offen.** Alle belegten Syntaxfehler hatten dieselbe Ursache: Trenner-Kommas/-Semikolons (`STRING A, B …`, `CALL … USING A, B,`, `VALUES 0,`) kennt die Grammatik nicht überall. Die Grammatik-Eingabe ersetzt sie jetzt längen- und zeilentreu durch Leerzeichen (`antlr_bridge._blank_separators`; Literale wie `'A,B'` bleiben erhalten). Zusätzlich zählten Leerzeilen mit Sequenznummern (Spalte 73–80) und ein alleinstehender `.` als „unstrukturierter Code“ und stuften `COACCT01`/`CODATE01` auf `partial` (`_is_code_line`). Regressionen in `test_cobol_antlr_diagnostics.py` und `test_cobol_parse.py`. Nachweis an den Originaldateien: `CBACT04C`, `CSUTLDTC`, `COACCT01`, `CODATE01` sind jetzt `complete` ohne Syntaxfehler (vorher `partial`/`text_fallback`). Offen: Reindex von Quelle 7, `COACTUPC` prüfen. Ursprünglicher Befund (ursächlich vermutet: Literal-/Zeilenfortsetzung bei den MQ-Programmen war falsch, es waren Kommas): Fünf Programme scheitern an Syntaxfehlern: `CBACT04C` und `CSUTLDTC` (`partial`, `no viable alternative at input 'PARM-DATE,'` bzw. `'WS-DATE-TO-TEST,'`; Komma als Trenner in Parameterlisten), `COACTUPC` (`extraneous input ','`) und die MQ-Programme `COACCT01`, `CODATE01` (`no viable alternative at input 'MOVE 'CICS RETREIVE' TO MQ-E…'`, Ursache offen, vermutlich Literal-/Zeilenfortsetzung). Je Fall minimal reproduzieren, Grammatik/Preprocessing anpassen und Regression ergänzen. Lokale Fehler dürfen die Divisions- und Paragraphenstruktur nicht verwerfen (O-305). |
| 5 | O-375 | Lokale COBOL-Kanten sofort auflösen und Systemziele nicht als echte Lücken zählen. | **Umgesetzt (02.10.2026), Bestandsabnahme (Reindex) offen.** **Korrektur zum ersten Befund:** Die 266 unaufgelösten COBOL-`EXECUTES`-Kanten (`SEND`, `RETURN`, `XCTL`, …) sind keine externen Ziele. Jede zeigt auf eine vorhandene `exec_operation`-Entity derselben Datei; `structure_persist.py` stellte alle Kanten mit `target_qualified_name` für Pass 2 zurück, der sie nie auflöste. Das gilt auch für `INCLUDES` (11) und `USES` auf EXEC-Ressourcen (70). Jetzt werden nur noch Copybook-Kreuzverweise (`copybook_path`) zurückgestellt, Ziele derselben Datei sofort verdrahtet (`test_structure_persist_local_exec_edges.py`). **Systemziele:** Unaufgelöste `COPY`/`CALL`-Kanten auf CICS-/MQ-/DB2-Copybooks (`DFH*`, `CMQ*`, `SQLCA`), Language-Environment-, IMS-, MQ- und DB2-Routinen sowie JCL-`EXECUTES` auf IBM-Utilities (`IEBGENER` u. a.) tragen nun `meta.external = {category, kind}` (`core/external_targets.py`, Pass in `edge_resolver.py`; Tests `test_external_targets.py`). `resolution` bleibt `unresolved`, damit API-Vertrag und Pass 2 unverändert sind; das Merkmal erscheint in Entity-, Call-Flow- und Impact-Antworten über `meta`. Echte Lücken wie `COBDATFT` bleiben unmarkiert. Offen: Reindex von Quelle 7 und Zählung `unresolved` ohne `external` (siehe O-380); Anzeige im UI. Ursprünglicher Befund (teilweise überholt): CardDemo: 305 von 307 `EXECUTES`-Kanten sind `unresolved`; Ziele sind CICS-Verben und `IEBGENER` (11). Unaufgelöste `COPY`-Kanten (62): vor allem `DFHAID`/`DFHBMSCA` und MQ-Copybooks; unaufgelöste `CALL`-Kanten (45): vor allem `CEE3ABD`, `CBLTDLI`, `MQOPEN`. |
| 6 | O-376 | Interne Java-Importe auflösen. | **Umgesetzt (02.10.2026), Bestandsabnahme (Reindex) offen.** Ursache: Der Java-Resolver (`java/resolution.py`) hat `IMPORTS`-Kanten nie aufgelöst. In Syncope waren 0 von 41.515 `IMPORTS`-Kanten `resolved`, nicht nur die internen. Jetzt zeigen `import a.B`, `import static a.B.member` und `import static a.B.*` auf den Repository-Typ `a.B` (bei statischem Member mit `meta.imported_member`), `import a.*` auf das Package; mehrere Kandidaten (Module) bleiben `ambiguous_import`, Testtypen aus `main` bleiben unaufgelöst. Regressionen in `test_java_relationships.py` (Rückgabezähler der bestehenden Tests um die neuen Importauflösungen angepasst). JDK-/Fremdbibliotheks-Importe bleiben unaufgelöst und werden in O-377 als extern gekennzeichnet. Offen: Stichprobe nach Reindex, dass interne Importe `resolved` sind und die Restmenge eine benannte Ursache trägt. Ursprünglicher Befund: 19.297 der 41.515 unaufgelösten `IMPORTS`-Kanten in Syncope zeigen auf `org.apache.syncope.*`, also auf Typen im selben Projekt; weitere 8.783 auf `java.*`/`javax.*`/`jakarta.*`. Für interne Importe prüfen, ob die Zielklasse fehlt, ob nur der Auflösungsweg (Wildcard-, Static-, Modulgrenze, Source-Set) fehlt oder ob es Namensräume aus anderen Quellen/Varianten sind. Abnahme: Stichprobe interner Importe von Klassen, die im Index existieren, werden `resolved`; Rest erhält eine benannte Ursache. |
| 7 | O-377 | Externe Java-Bibliotheken und statisch importierte Testmethoden als solche markieren. | **Umgesetzt (02.10.2026), Bestandsabnahme (Reindex) offen; Testcode-Filter offen.** Unaufgelöste `IMPORTS`, `USES_TYPE`, `INSTANTIATES`, `EXTENDS`, `IMPLEMENTS`, `CALLS`, `READS`/`WRITES` und `REFERENCES_METHOD` tragen `meta.external = {category: jdk\|jakarta\|library, library: <qualifizierter Typ>, via}`, wenn der Quelltext das Ziel belegt: Import, paketqualifizierter Name, `java.lang`-Typ, deklarierter Receiver-Typ (z. B. `LOG` → `org.slf4j.Logger`), Typname als Receiver (`List.of`) oder statischer Import (`assertEquals` → `org.junit.jupiter.api.Assertions`). Statische Wildcard-Importe gelten nur als `certainty: possible`; nicht belegte Ziele bleiben ohne Kennzeichnung, `resolution` bleibt `unresolved` (`java/resolution.py::mark_external_edges`, `test_java_external_targets.py`). Veraltete Kennzeichnungen werden entfernt, sobald eine Kante aufgelöst wird. Stichprobe an drei Syncope-Dateien: `assertEquals` → JUnit, `Arrays.asList` → JDK, `MAPPER.readValue` → Jackson. Offen: Nach Reindex Anteil `unresolved` ohne `external` ausweisen (O-380); Testcode im Impact-/Call-Flow getrennt filtern; Variablen ohne ermittelbaren Typ (z. B. `var`, `defaultObj.setUser`) bleiben bewusst offen. Ursprünglicher Befund: 91.563 von 132.181 `CALLS`-Kanten (69 %) sind `unresolved`; häufigste Ziele: `assertEquals` (2.986), `assertNotNull` (2.155), `assertTrue` (1.294), `List.of` (830), `Optional.ofNullable` (761), `LOG.error` (740), `LOG.debug` (574). Das sind JDK-, Test-Framework- und Logger-Aufrufe ohne Repo-Ziel. Statische Importe auflösen und sie mit Bibliothek (z. B. JUnit, SLF4J, JDK) als `external` führen; `USES_TYPE` (42.503 unaufgelöst) gleichbehandeln. Echte projektinterne Lücken müssen danach als kleine, prüfbare Restmenge sichtbar werden. Testcode im Impact-/Call-Flow getrennt filterbar machen. |
| 8 | O-378 | `.properties`, Groovy, SQL und JavaScript strukturiert erschließen. | **Teilweise umgesetzt (02.10.2026): `.properties` fertig, Reindex-Abnahme offen; Groovy, SQL, JavaScript und Java-Verweise offen.** Neuer Parser `resources/properties.py` (`properties-structure-1`, im Dockerfile ergänzt): Wurzel `properties_file` mit `bundle`, `locale` und `property_count`; für Basis-Bundles je Schlüssel ein `property`-Entity mit Quellzeilen (inkl. Zeilenfortsetzung, doppelten Schlüsseln und maskierten Werten bei `password`/`secret`/`token`). Übersetzungsdateien (`messages_de.properties`) bekommen nur die Wurzel, damit der Bestand nicht mit der Sprachanzahl wächst. Alle 1.349 Syncope-Dateien parsen fehlerfrei als `complete` (3.892 Entities, davon 2.543 Schlüssel aus 289 Basis-Bundles). Tests: `test_properties_parse.py`. Offen: (a) Verweise aus Java (`getString`, `ResourceModel`, `@Value`) auf Schlüssel belegt auflösen, (b) Groovy-Plugins (`MyCommand.groovy` u. a.), (c) SQL und JavaScript. Ursprünglicher Befund: Syncope: 1.349 `.properties`, 70 Groovy, 8 JavaScript und 5 SQL-Dateien sind `text_fallback`. Keine Schlüssel-/Bundle-Entities, daher keine Verknüpfung zwischen Message-Keys und Java/Wicket-Verwendung (`ResourceBundle`, `@Value`, `getString`). Zuerst Properties-Schlüssel mit Bundle-Zuordnung (Basis- und Locale-Datei) als Entities; dann Verweise aus Java belegt auflösen. Groovy-Implementierungen (z. B. `MyCommand.groovy`) als Plugin-Beispiele verfolgen. Abnahme an einer Frage zu einem i18n-Schlüssel mit Beleg aus Properties und Java. Bezug zu den 87 übersprungenen `.properties` aus der Bestandsabnahme. |
| 9 | O-379 | XML mit DOCTYPE sicher verarbeiten statt auszuschließen. | **Offen.** 14 Syncope-XML-Dateien (`partial`, u. a. `core/persistence-jpa/.../indexes.xml`, `views.xml` für mariadb/mysql/oracle) werden mit „DOCTYPE/DTD-Deklarationen werden aus Sicherheitsgründen nicht verarbeitet“ abgelehnt. Das Ausschalten externer Entitäten und DTD-Ladens genügt für Sicherheit; die Datei selbst kann trotzdem strukturiert gelesen werden. DOCTYPE tolerieren, ohne externe Entities oder DTDs zu laden; Negativtest mit Entity-Expansion bleibt Pflicht. |
| 10 | O-380 | Statusbericht je Quelle mit Nutzen für Anwender: Anzahl und Ursachen nicht strukturierter Dateien. | **Offen.** Die Scan-Statistik verteilt sich über `parse_status` und `parse_error`; so sind 1.680 von 5.736 Syncope-Einträgen `text_fallback` (davon 1.349 `.properties`) und 89 `skipped` ohne Aufschlüsselung sichtbar, ohne die Tabelle abzufragen. Pro Quelle nach Sprache und Grund gruppiert anzeigen (erwartet nicht strukturierbar, z. B. Binär/EBCDIC-Daten; Lücke im Parser; Parserfehler wie O-371), damit Nutzer abschätzen können, was der Index nicht abdeckt. Bei Binär-/EBCDIC-Dateien (CardDemo `AWS.M2.CARDDEMO.*.PS`, Syncope Fonts/Keystore) ist `skipped` korrekt und kein Fehler. |

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
| 50 | O-324 | Headless MCP-Server (Model Context Protocol) zur Anbindung lokaler Offline-IDEs bereitstellen. | MCP-Sicherheitsprüfung am 24.09.2026: zwei Befunde zu `search_knowledge`-Projektisolation und Call-Flow-Ressourcenlimits behoben; 27 isolierte Prüfungen und 9 Regressionen bestanden. Backend, Tokens, sechs lesende Tools, Migration und Rollout sind implementiert; Remote-VS-Code-MCP-Client ist konfiguriert. Direkte fremde Projekt-/Entity-Zugriffe, abgelaufene/widerrufene Tokens und deaktivierte Konten werden korrekt abgewehrt. `search_knowledge` kann wegen des unabhängigen Embedding-HTTP-Fehlers aus O-251 noch funktional fehlschlagen. **O-171 abgeschlossen:** Die strategische Entscheidung für Doctus als schreibgeschütztes Werkzeug-Backend bleibt abgeschlossen. |
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
