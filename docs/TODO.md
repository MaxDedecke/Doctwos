# Doctus – priorisierte TODO-Liste

Stand: 22.09.2026

Diese Datei ist die kanonische Liste der noch offenen Arbeit. Die Reihenfolge
innerhalb einer Priorität ist zugleich die empfohlene Ausführungsreihenfolge.
`teilweise` bedeutet, dass der verbleibende Abnahmepunkt weiterhin offen ist.
Erledigte Punkte stehen nicht mehr im aktiven Backlog; ihr Nachweis bleibt in der
Git-Historie und in den verlinkten Fachunterlagen erhalten.

## P0 – jetzt umsetzen

| Rang | ID | Ergebnis | Status / Abnahme |
|---:|---|---|---|
| 1 | O-271, O-301 | Durchgängigen Erkenntnis-Workflow liefern: aus Chat, Code oder Prozessschritt einen belegten Entwurf sichern und durch einen zweiten berechtigten Nutzer freigeben. | **Umgesetzt, E2E-Abnahme offen.** API, persistentes Status-/Auditmodell, Vier-Augen-Sperre und UI-Aktionen für Chat, Code und Process View sind vorhanden. Mit zwei echten Projekt-Admins abnehmen. |
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
| 13 | O-312 | Remote-Ollama während langer Imports stabil betreiben: Modellresidenz, Admission und Verbindungsabbrüche beobachten. | Der laufende CardDemo-Import fängt einzelne Dateifehler korrekt ab. Vor weiterer Lastabnahme prüfen, dass `qwen3-embedding:4b` nicht unnötig entladen/neu geladen wird und keine EOF-/Verbindungsabbrüche an der Ollama-/Proxy-Grenze auftreten; `/api/ps`, GPU-Telemetrie, Queue-Wartezeit und Container-Logs gemeinsam protokollieren. Keine Container-Rollouts während eines aktiven Imports. |
| 14 | O-314 | COBOL-Importdurchsatz gezielt optimieren. | **Umgesetzt.** Parsezeit, Chunk-Anzahl, Embedding-Batchgröße und Admission-Wartezeit je Datei werden erfasst und im Sync-Log protokolliert; Chunks großer Text-/Datenartefakte werden in bounded Fair-Batches (Standard 20) mit kooperativen Event-Loop-Yields unterteilt. Embedding-Parallelität ist standardmäßig auf die freie Admission-Batch-Kapazität (3 Slots bei Chat-Reserve) begrenzt; Abhängigkeitsauflösung (`_analysis_dependency_paths`) nutzt gezielte SQL-Joins statt speicherintensiver Python-Dictionaries. Regressionen in `test_o314_fair_batching_and_analysis_deps.py`, `test_git_connector.py` und `test_inference_admission.py`. |
| 15 | O-315 | Automatischen Link-Builder vom normalen Quellenimport entkoppeln. | **Umgesetzt.** Kein automatischer Link-Build nach Quellenimport; statische Parserkanten, Chunks und Quellenbelege bleiben ohne ihn vollständig nutzbar. Link-Build als separat start-/abbruchbarer Job im Job-Center (auch für abgebrochene Läufe wiederaufnehmbar), Deduplizierung aktiver Läufe sowie Kosten-/Umfangshinweis (`/link-recommendations/estimate` und Dialog im Link-Manager) umgesetzt. Regressionen in test_entity_links.py, test_jobs.py und test_sync_decoupled_link_builder.py. |
| 16 | O-316 | Chat-Startpfad unter Importlast verschlanken und messbar machen. | Der Produktionstest erhielt dank Chat-Reserve sofort einen Inference-Slot, führte für eine triviale Antwort aber trotzdem Query-Embedding und den vollständigen 20-Entity-Repository-Bootstrap aus. Bootstrap nur bei repositorybezogenen Fragen bzw. bei explizitem Projektkontext ausführen oder progressiv nachladen; Time-to-first-token, Bootstrap-/Retrieval-Zeit, Modellzeit und Abschlussereignis im SSE-Stream separat messen und anzeigen. |
| 17 | O-317 | Datei- und Projektfokus im Eval-Retrieval erzwingen. | **Umgesetzt, Bestandsabnahme offen.** Explizite Pfade, Dateinamen und COBOL-Programm-IDs begrenzen Retrieval und lokale Repo-Werkzeuge; auch durch Graph-Erweiterung hinzugekommene fremde Dateien werden verworfen. J1/J2/C1/C4/C6 am Zielbestand erneut messen. |
| 18 | O-318 | Quellenkonsistenz vor Chat-Antwort validieren. | **Umgesetzt, Bestandsabnahme offen.** Vor dem finalen SSE-Answer werden Dateizitate und Zeilen gegen den gelieferten Recherchekontext geprüft; explizite Aufrufbehauptungen benötigen eine aufgelöste `trace_call_flow`-Kante. Bei fehlendem Beleg wird eine Index-/Parserlücke statt einer plausiblen Ersatzquelle/-kante ausgegeben. |
| 19 | O-319 | Zielpfad aus der Nutzerfrage vor dem allgemeinen Repository-Bootstrap extrahieren. | **Umgesetzt, Bestandsabnahme offen.** Backtick-Pfade, Dateinamen und Programm-IDs begrenzen den Bootstrap; zusätzlich werden explizit genannte Klassen, Methoden, Paragraphen und Templates vor dem Modelllauf als exakte, dateigebundene Indexentitäten aufgelöst. J1–J4 und C1/C3 am Zielbestand erneut messen. |
| 20 | O-320 | COBOL-Dateisuche quellenweit statt verzeichnislokal machen. | **Umgesetzt, Bestandsabnahme offen.** Rekursive Repo-Suche und Listing verwenden dieselben gefilterten, stabil sortierten Pfade. Nach einem Import ist das Scan-Journal maßgeblich für den Projekt-Dateibaum, sodass auch übersprungene/partielle Dateien sichtbar bleiben; vor dem ersten Journal-Eintrag dient der vollständige Worktree als Fallback. C6 am Zielbestand erneut messen. |
| 21 | O-321 | Exakte Entity-Auflösung vor `trace_call_flow` erzwingen. | **Umgesetzt, Bestandsabnahme offen.** Bei explizitem Datei-/Symbolfokus akzeptiert `trace_call_flow` nur zuvor exakt und dateigebunden aufgelöste Entitäten; abweichende IDs oder Namen liefern die Kandidaten samt Auflösungsstatus statt eines zufälligen Flows. C1 am Zielbestand erneut messen: `COPAUA0C.MAIN-PARA`, nie `PAUDBUNL.MAIN-PARA`. |
| 22 | O-322 | Eval-Fragen mit Ground-Truth-Datei regressionssichern. | **Umgesetzt, Bestandsabnahme offen.** Offline-Ground-Truth-Suite deckt J1–J5 und C1–C6 mit Primärdatei, Zeile, Kante und Ersatzdatei ab. Sie verhindert insbesondere, dass ein fremder Pfad mit gleichem Basename als Quelle durchgeht; die Messung am echten Zielbestand bleibt offen. |
| 23 | O-323 | Chat-SSE-Telemetrie für Eval und Betrieb vervollständigen. | **Umgesetzt.** Der SSE-Stream liefert relative monotone Meilensteine für `request_received`, ersten Tool-Call, First-Token, Tool-Ende, Modell-Ende und `message_saved`; sein Abschlussprotokoll sowie die gespeicherte Antwort enthalten Antwortzeit, First-Token, Tool-Anzahl und Retrieval-Wartezeit. |

## P1 – danach umsetzen

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
| 20 | O-253 | Mischsprachen in Editor, Graph, Zitaten und Agentenantworten korrekt anzeigen. | Nach O-287 bis O-289 und vorhandenen XSLT-/Shell-/JSP-Parsern. |
| 21 | O-254 | Qualität und Last des tatsächlichen Mischbestands vor der Pilotfreigabe messen. | Nach O-251 bis O-253. |

### Wissensgraph, Wissen und Suche

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 22 | O-269 | Wahre Kantenrichtung in Fokus-API, Schemas, Serializer und Link-Manager durchgängig erhalten. | Auf O-264–O-266; API- und View-Regressionen. |
| 23 | O-267 | Richtung im Detail-Drawer, manuellen Linkdialog und Fokusfilter anzeigen. | Nach O-269. |
| 24 | O-268 | Richtungs-Taxonomie, Tests und Graph-Dokumentation ergänzen. | Nach O-267. |
| 25 | O-270 | Hierarchisches DAG-Layout und Upstream-/Downstream-Traversierung ergänzen. | **Umgesetzt.** Gerichtete Codekanten bleiben im Knowledge Graph erhalten; die begrenzte Nachbarschaft unterstützt Upstream, Downstream oder beide Richtungen über bis zu fünf Hops. Zyklensichere BFS und ein schichtweises Traversierungs-Layout machen die Richtung sichtbar. |
| 26 | O-286 | Dokumentknoten nur bei einer echten genehmigten Beziehung in den Graph aufnehmen. | Backendtest für verbundene und unverbundene Chunks. |
| 27 | O-273 | Änderungsfolgenanalyse um Diff, Revision und belastbare Test-/Owner-Bezüge abschließen. | Teilweise umgesetzt; mit O-300 fachlich abnehmen. |
| 28 | O-274 | PR-/MR-Diskussionen und ADRs mit Herkunft, Version und Prüfstatus erschließen. | Erst nach stabilem Erkenntnismodell O-271/O-301. |
| 29 | O-275 | Fachbereichsübersichten aus Zweck, Systemen, Regeln, Sonderfällen und Verantwortung bilden. | Bestätigte Quellen und Verantwortlichkeiten erforderlich. |
| 30 | O-276 | Geprüfte, widersprüchliche und veraltete Erkenntnisse in Chat und Ansichten sichtbar machen. | Mit O-272/O-302 abschließen. |
| 31 | O-277 | Repräsentative Such- und Antwortfragen mit erwarteten Fundstellen versionieren. | Grundlage für O-284/O-304. |
| 32 | O-278 | Pilotaufgaben und Ausgangswerte für Fehleranalyse, Einarbeitung und Änderungsvorbereitung erfassen. | Pilotteam erforderlich. |
| 33 | O-279, O-280 | Entity-Kontext und semantische Linkprüfung fachlich am Referenzbestand abnehmen und Restlücken schließen. | Teilweise umgesetzt; harte Kontextgrenzen beibehalten. |
| 34 | O-284 | EVALRUN_1 um feste Java-/COBOL-Positionen, erwartete Dokumentpassagen und Negativfälle erweitern. | Nach O-277. |

### Link-Berechnung und Laufzeit

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 35 | O-179 | Run-Budget, Kostenschätzung, Fortschritt und Abbruch für Link-Läufe liefern. | Vor breiter Lastabnahme. |
| 36 | O-181 | Kandidatenbildung über begrenzten, verschlüsselungskonformen Vorfilter skalieren. | Repräsentative Korpusmessung. |
| 37 | O-182 | Entity-Embeddings persistent cachen und per Inhalt sowie Modellversion invalidieren. | Aktives Embedding-Profil berücksichtigen. |
| 38 | O-183 | Top-k, Deduplizierung, Schwellen, Batch-Review und Parallelität als Run-Parameter führen. | Nach O-179/O-182. |
| 39 | O-184 | Kandidaten und Persistenz bündeln; Unique-Constraints und Bulk-Upserts ergänzen. | Nach O-183. |
| 40 | O-185 | Kontingente für Import, Linking und globale Batch-Läufe trennen. | SLOs mit Betreiber vereinbaren. |
| 41 | O-186 | Versionierten Benchmark für Import, Delta-Sync, Linking, Suche und Speicher erstellen. | Nach O-179 bis O-185. |

### Chat-Agent: Ansichten während der Arbeit

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 42 | O-199 | Ziel-Qwen, Streaming, Berechtigungen und Panel-Regeln gezielt abnehmen. | Begleitend zu allen Agentenansichten. |
| 43 | O-193 | Suchergebnisse mit nachvollziehbarem Projekt- und Quellenfilter öffnen. | O-190 ist umgesetzt. |
| 44 | O-194 | Begrenzte Wissensgraph-Nachbarschaft mit Fokus und Beziehungsfiltern öffnen. | O-190 ist umgesetzt. |
| 45 | O-197 | Link-Manager auf eine konkrete Verknüpfung und ihre Belege fokussieren. | O-190 bis O-192 sind umgesetzt. |
| 46 | O-198 | Quellen- und Jobstatus im Job Center lesend öffnen. | Niedrigere Produktpriorität. |
| 47 | O-258 | Import und Chat parallel gegen das Zielmodell testen und First-Token-SLO abnehmen. | Betreiber und Zielmodell erforderlich. |
| 48 | O-187, O-259 | Profil-Verfügbarkeitsprüfung und Mismatch-Telemetrie abschließen; Remote-Qwen-Tool-Aufrufe und belastbare Zitation live abnehmen. | **O-187 teilweise umgesetzt:** Der Profiltest prüft jetzt zusätzlich zur Endpoint-Erreichbarkeit, dass Chat- und Embedding-Modell tatsächlich am Endpoint verfügbar sind; abweichende Modellkennungen werden als Readiness-Mismatch geloggt und als Fehler zurückgegeben. Der Embedding-Profiltest prüft weiterhin die konfigurierte Dimension. Remote-Qwen-Tool-Aufrufe und belastbare Zitation (O-259) am bereitgestellten Endpunkt live abnehmen. |
| 49 | O-250, O-260, O-261, O-262, O-263 | Umgesetzte Mischsprachen-, Shell-, HTML-, Ablauf- und Intent-Fixes ausrollen, reindizieren und an den realen Beständen abnehmen. | Rollout/Reindex und Remote-Qwen erforderlich. |
| 50 | O-264 | Datenbankmigration für Kantenrichtung beim Rollout anwenden. | Technisch umgesetzt; Migrationsnachweis offen. |

### Entwickler-Workflow & IDE-Integration

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 51 | O-324 | Headless MCP-Server (Model Context Protocol) zur Anbindung lokaler Offline-IDEs bereitstellen. | Stellt Wissensgraph, AST-Entitäten, Call-Flows und semantisches Retrieval als standardisierte MCP-Tools im internen Netz bereit (für Continue.dev, VS Code, Cursor). Konkrete Umsetzung zu O-171. |
| 52 | O-325 | IDE-Integration & Deep Links (VS Code / JetBrains / Eclipse) für nahtlose Navigation liefern. | Direktsprung von Quelltextzeilen in den Doctus-Graph sowie CodeLens-/Hover-Informationen für Cross-References (`CALL`, `COPY`) in der lokalen IDE. |

## P2 – Pilot- und Mainframe-Fähigkeit

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
| 63 | O-329 | Strukturellen JCL-Parser für Batch-Abläufe und Programm-Dataset-Verknüpfungen ergänzen. | Parser-Erweiterung für JCL/PROCs zur Extraktion von Job-Steps, `EXEC`-Programmen und Datasets (`EXECUTES`-, `READS`-, `WRITES`-Kanten), um Batch-Ablaufketten im Call-Graph zu schließen (Erweiterung zu O-145–O-147). |
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

### High-Throughput-Inferenz & vLLM-Unterstützung

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 73 | O-338 | vLLM als High-Throughput-Inferenz-Backend für Chat und Tool-Calling zertifizieren. | Validiere vLLMs OpenAI-kompatiblen Endpunkt (`/v1/chat/completions`) für Qwen 2.5 Coder (14B/32B/72B) inkl. nativer Tool-Aufrufe (`tools`, `tool_choice`). Healthcheck-Adapter für `/health` und `/v1/models` in die Profil-Erreichbarkeitsprüfung integrieren; Fehlerverhalten bei GPU-Memory-Exhaustion abfangen. |
| 74 | O-339 | Prompt-Prefix-Stabilität für vLLM Automatic Prefix Caching (APC) optimieren. | System-Prompt, Tool-Definitionen, Sicherheitsanweisungen und statischen Projekt-/Quellenkontext im Chat-Agenten deterministisch an den Anfang des Prompts stellen (strikte Trennung von statischem Prefix und variablem Chatverlauf/Fragetext). Dadurch erreicht vLLM maximale KV-Cache-Wiederverwendung und senkt die Time-to-first-token (TTFT) bei paralleler Nutzung auf wenige Millisekunden. |
| 75 | O-340 | Admission-Control & Concurrency-Skalierung für vLLM-Cluster auslegen. | In `inference_admission.py` dynamische Slot-Zuweisung je nach Backend-Typ implementieren: Erkennung von vLLM-Endpoints zur Freigabe höherer Nebenläufigkeitsgrenzen (`INFERENCE_MAX_CONCURRENCY` 16–32 statt 4 bei Ollama) dank Continuous Batching und PagedAttention; getrennte Kontingente für Chat-Streaming und Embeddings. |
| 76 | O-341 | vLLM-Bereitstellungsprofil & Helm-/Compose-Option für Enterprise-GPU-Hosts (Machine B) liefern. | Dokumentiertes und versioniertes `docker-compose.vllm.yml` sowie Helm-Subchart für Machine B mit Tensor Parallelism (`--tensor-parallel-size`), AWQ/FP8-Quantisierung und vLLM-Image zur Bereitstellung auf Nvidia A100/H100/RTX 6000 Ada als performante Alternative zum Ollama-Host. Dokumentation in `REMOTE_INFERENCE.md` erweitern. |

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
| 85 | O-171 | Doctus als schreibgeschütztes Werkzeug-Backend/MCP-Server strategisch bewerten. | Roadmap-Entscheidung; konkrete Umsetzung in O-324. |
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
