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
| 1 | O-271, O-301 | Durchgängigen Erkenntnis-Workflow liefern: aus Chat, Code oder Prozessschritt einen belegten Entwurf sichern und durch einen zweiten berechtigten Nutzer freigeben. | Offen. O-301 setzt das Daten- und Statusmodell aus O-271 als kleinsten vertikalen Schnitt um. |
| 2 | O-272, O-302 | Erkenntnisstatus und Provenienz durchgängig anzeigen; Quellenänderungen erzeugen eine Review-Aufgabe. | Teilweise. Technische Provenienz ist vorhanden; `draft`, `verified`, Widerspruch und veraltet werden mit O-301 abnehmbar. |
| 3 | O-303 | Priorisierte Prüfliste für neue Links, widersprüchliche, abgelehnte und veraltete Erkenntnisse bereitstellen. | Offen. Bestehenden Link-Manager und Review-Status wiederverwenden. |
| 4 | O-305 | COBOL-Syntax-Recovery an realen Dialektfällen stabilisieren, damit lokale Fehler nicht ganze Divisions-, Paragraphen- und Feldstrukturen vernichten. | Teilweise. Recovery-Fix für EXEC-Blöcke in DATA/COPYBOOK und mehrzeilige IDENTIFICATION-Metadaten umgesetzt und Regressionen ergänzt; Reindex der drei Bestände läuft bzw. ist beim externen RunPod-Embedding-Endpunkt wegen 404 noch nicht abnahmefähig. |
| 5 | O-309 | Java-Aufrufe über Parameter, lokale Variablen, Felder, Vererbung und Interfaces belegbar auflösen. | Offen. Referenzfälle und Auditbericht ohne Auflösung nur nach Methodennamen. |
| 6 | O-310 | Deklarationen und Referenzvorkommen in Java und COBOL direkt anklickbar machen; Hierarchie als begrenzte `CONTAINS`-Struktur zeigen. | Offen. Unresolved und dynamische Stellen dürfen kein Ziel behaupten. |
| 7 | O-292 | Begrenzten, sprachneutralen Backendvertrag für die Process View bereitstellen. | Offen. Serverseitige Limits, Zyklen, Kürzung und Locator gehören in den Vertrag. |
| 8 | O-293, O-294, O-295 | COBOL- und Java-Kanten in denselben Prozessvertrag projizieren und Sicherheit, Reihenfolge sowie Unsicherheit belegen. | Offen. Keine erfundene lineare Reihenfolge; `certain`, `possible` und `unresolved` unterscheiden. |
| 9 | O-299 | Workflow „Was macht dieses Element?“ von Frage bis Originalbeleg verbinden. | Offen. Je eine Java- und COBOL-Aufgabe vollständig abnehmen. |
| 10 | O-300 | Workflow „Änderung untersuchen“ fachlich an Java und COBOL abnehmen. | Teilweise. Technischer Impact-Schnitt ist umgesetzt; Bestandsabnahme fehlt. |
| 11 | O-304 | Produktschnitt mit versionierten Java-/COBOL-Szenarien und Ground Truth messen. | Offen. Erst starten, wenn O-299 bis O-303 fachlich abnehmbar sind. |

## P1 – danach umsetzen

### Sprachlogik und anklickbare Codeobjekte

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 12 | O-306 | `EXEC CICS`, `EXEC DLI`/IMS und belegte weitere `EXEC`-Dialekte als anklickbare Blöcke, Operationen und Ressourcenbeziehungen erhalten. | Nach O-305; dynamische Operanden und unbekannte Dialekte sichtbar lassen. |
| 13 | O-307 | COBOL-I/O, SQL, Datenstruktur und Lese-/Schreibzugriffe fachlich verbinden. | Nach O-288 und O-305/O-306; mehrdeutige Ziele unresolved lassen. |
| 14 | O-308 | Java-Records, Parameter, relevante lokale Variablen, lokale/anonyme Klassen, Lambdas und Methodenreferenzen adressierbar machen. | Entlang des Bedarfs von O-309 umsetzen; Graphübersicht größenbegrenzt halten. |
| 15 | O-288 | COBOL-`PERFORM THRU`, `EXEC SQL INCLUDE` und `file_fd`-Beziehungen vervollständigen. | Vor O-307; an CardDemo mit Originalzeilen abnehmen. |
| 16 | O-287 | Maven-Kanten dateilokal und über Module/Source-Sets korrekt auflösen. | Abnahme mit gleichen Qualified Names in getrennten Modulen. |
| 17 | O-289 | Shell-Funktionen per `DECLARES` und lokale Aufrufe mit dem Skript verbinden. | Reale Shell-Fixture plus Persistenztest. |
| 18 | O-243 | Java-Syntax und Strukturunterstützung am Zielbestand absichern. | Referenzbestand und Sprachbericht aus O-240/O-242. |
| 19 | O-245 | Java-Aufrufauflösung und Unsicherheit an belegten Referenzfällen messen. | Mit O-309 zusammenführen, damit keine zweite Resolver-Arbeit entsteht. |
| 20 | O-253 | Mischsprachen in Editor, Graph, Zitaten und Agentenantworten korrekt anzeigen. | Nach O-287 bis O-289 und vorhandenen XSLT-/Shell-/JSP-Parsern. |
| 21 | O-254 | Qualität und Last des tatsächlichen Mischbestands vor der Pilotfreigabe messen. | Nach O-251 bis O-253. |

### Wissensgraph, Wissen und Suche

| Rang | ID | Ergebnis | Abhängigkeit / Abnahme |
|---:|---|---|---|
| 22 | O-269 | Wahre Kantenrichtung in Fokus-API, Schemas, Serializer und Link-Manager durchgängig erhalten. | Auf O-264–O-266; API- und View-Regressionen. |
| 23 | O-267 | Richtung im Detail-Drawer, manuellen Linkdialog und Fokusfilter anzeigen. | Nach O-269. |
| 24 | O-268 | Richtungs-Taxonomie, Tests und Graph-Dokumentation ergänzen. | Nach O-267. |
| 25 | O-270 | Hierarchisches DAG-Layout und Upstream-/Downstream-Traversierung ergänzen. | Nach O-267; Zyklen explizit behandeln. |
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
| 48 | O-187, O-259 | Profil-Verfügbarkeitsprüfung und Mismatch-Telemetrie abschließen; Remote-Qwen-Tool-Aufrufe und belastbare Zitation live abnehmen. | Remote-Endpunkt mit Tool-Call-Unterstützung. |
| 49 | O-250, O-260, O-261, O-262, O-263 | Umgesetzte Mischsprachen-, Shell-, HTML-, Ablauf- und Intent-Fixes ausrollen, reindizieren und an den realen Beständen abnehmen. | Rollout/Reindex und Remote-Qwen erforderlich. |
| 50 | O-264 | Datenbankmigration für Kantenrichtung beim Rollout anwenden. | Technisch umgesetzt; Migrationsnachweis offen. |

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
| 85 | O-171 | Doctus als schreibgeschütztes Werkzeug-Backend/MCP-Server strategisch bewerten. | Roadmap-Entscheidung. |
| 86 | O-172 | Interviewbasierte Wissensquelle mit zwingender menschlicher Freigabe zuschneiden. | Fachliche Priorisierung. |
| 87 | O-173 | Keyword-/Volltext-Fallback unter Verschlüsselung evaluieren. | Belegter Recall-Fehler. |
| 88 | O-174 | Strukturtreue PDF-Extraktion evaluieren. | Belegter Qualitätsfall mit komplexen PDFs. |

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

## Pflege

- Neue Aufgaben erhalten die nächste freie O-Nummer und werden sofort in eine
  Priorität und Rangfolge einsortiert.
- Teilweise umgesetzte Punkte bleiben aktiv, bis ihr offener Abnahmeschritt
  nachgewiesen ist.
- Nach Abschluss wird der Punkt aus dieser Datei entfernt; dauerhafte
  Architekturentscheidungen gehören in [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md),
  fachliche Detailnachweise in die jeweils verlinkte Dokumentation.
