# Review: Codex-Benchmark Kapitel 3, 29.09.2026

## Grundlage und Ergebnis

Geprüft wurde der letzte vollständige Lauf unter
`/root/doctus_ab_probe/official_luna_benchmark_chapter3/`, der auch im aktuellen
`/root/codex_benchmark.html` als Kapitel 3 dargestellt ist. Frühere Teilversuche
und `chapter3_luna_30pairs_run2` gehören nicht zu dieser Auswertung.

Lesend ausgewertet: `protocol.json`, `results.json`, `scores.json`, MCP-Ereignisse
aller `raw/*_with_mcp.jsonl`, ausgewählte Originalantworten und Rubriken.
Abgleich mit `backend/mcp_server.py`, `backend/services/search.py`,
`parser/java/declarations.py` und Syncope-Originalquellen im vorhandenen Checkout.
Keine Live-Anfragen, Reindizierung oder erneuten Modellläufe durchgeführt.
Codebefunde beziehen sich auf den beim Review vorhandenen Checkout; der Lauf
benutzte ausdrücklich den bestehenden Index ohne Neuaufbau.

60 Sitzungen (6 Aufgaben × 5 Wiederholungen × 2 Arme), alle Exitcode 0.
Modell laut Protokoll: `gpt-6-luna`, Reasoning `high`, CLI `0.158.0`.
Die Rohbewertung ergibt 127/235 Punkte ohne und 157/235 mit MCP, also
54,0 % gegenüber 66,8 %. Median der 30 gepaarten Zeitdifferenzen
**mit minus ohne MCP: +6,1 s**; in 14 Paaren ist MCP schneller.

| Aufgabe | Punkte ohne MCP | Punkte mit MCP |
|---|---:|---:|
| CARD-ARCH-01 | 30/45 | 40/45 |
| CARD-INCIDENT-02 | 35/55 | 36/55 |
| CARD-FLOW-03 | 20/30 | 29/30 |
| SYNC-CREATE-04 | 18/35 | 21/35 |
| SYNC-UPDATE-05 | 4/35 | 4/35 |
| SYNC-PULL-06 | 20/35 | 27/35 |

Ein einzelner, nicht verblindeter Luna-Prüfer bewertete alle Antworten. Die
Rubriken enthalten MCP-spezifische Kriterien; insbesondere UPDATE zeigt
auffällige Zitierabwertungen. Die Zahlen sind die archivierte Rohbewertung,
kein unabhängig bestätigtes Maß fachlicher Richtigkeit. Laut Lauf-README lief
zeitweise Entwicklungsarbeit auf demselben Host. Unterschiede zu Kapitel 2
sind deshalb kein kausaler Nachweis einer Produktverbesserung oder Regression.

## Konkrete Befunde

### 1. Java-Methodensuche normalisiert zu spät — O-355

`research_project` ruft `search_nodes(q=term)` auf, bevor `_symbol_matches`
`#` und `.` vereinheitlicht. `search_nodes` sucht per `ILIKE` nach dem
unveränderten Text. Der Java-Parser bildet Qualified Names als
`Owner#method(ParameterTypes)`. Damit kann `UserLogic.create` die passende
Methode bereits im Vorfilter verlieren. Die nachgelagerte Normalisierung
behebt das nicht. Sie entfernt zudem Parameterlisten und kann überladene
Methoden nicht anhand der angefragten Signatur unterscheiden.

Archivbelege: `sync-update-05_r1_with_mcp` liefert für `UserServiceImpl.update`
und `UserLogic.update` jeweils null Kandidaten; `sync-pull-06_r1` bis `r4`
für `PullJobDelegate.doExecuteProvisioning` ebenfalls. CREATE r1/r4/r5 findet
`UserLogic.create` nicht. Das belegt ein Nutzungsproblem; welche zusätzlichen
Lücken vom konkreten Indexstand kommen, ist separat abzugleichen.

### 2. Freitext wird erfolglos als Symbol oder Wortliste gesucht — O-342/O-355

Vier Incident-Sitzungen rufen `research_project` mit einer fachlichen Frage
auf und erhalten keine exakten Treffer. In r4 genügt `approval/decline`, damit
`_research_terms` die Prosa als Symbolliste behandelt und auf acht Wörter
begrenzt. Bei CREATE r4 werden neben den Symbolen auch `REST`, `user` und
`creation` als Suchbegriffe verarbeitet. Explizite Recherchemodi und ein
begrenzter inhaltlicher Suchweg sind hier sinnvoller als weitere allgemeine
Punkt-/Slash-Heuristiken. Abnahme und konkrete Fälle stehen unter O-355.

### 3. Cursorfehler sind Agentenfehler mit unbrauchbarer Rückmeldung — O-370

Von 119 MCP-Aufrufen scheitern drei. Zwei sind Flow-Fortsetzungen in
`card-arch-01_r1_with_mcp` und `card-arch-01_r4_with_mcp`.
Der Vergleich der zurückgegebenen und wieder eingesendeten Base64-Cursor
zeigt in beiden Fällen: Der Agent veränderte den Schlüssel `include_source`
zu `nclude_source`. Die Antwort enthielt zuvor den korrekten Cursor und eine
vollständige `follow_up_actions`-Anfrage. In r1 funktioniert der anschließende
Retry mit dem unveränderten Cursor; r4 lädt nach einem neuen Flow erfolgreich
weiter. **Kein Beleg für grundsätzlich defekte Serverpagination.**

Die Schnittstelle verwirft den Cursor zu Recht, maskiert jedoch den eigenen
Fehler `cursor does not match this call-flow query` in `_tool_context` als
`MCP request failed or access denied`. Ein sicherer, verständlicher
Validierungsfehler soll eine gezielte Korrektur ermöglichen.

24 Flow-Anfragen verlangen außerdem mehr als 15 Kanten pro Seite; 17
MCP-Anfragen verlangen mehr als drei Hops. Die Funktionsparameter sind bloße
`int`-Felder mit stiller Begrenzung. Schema und Beschreibungen sollen die
tatsächlichen Grenzen vermitteln; deren Schutzwirkung bleibt erhalten.

### 4. Quellenwerkzeuge werden nicht genutzt; Fortsetzung ist uneinheitlich — O-350/O-351/O-356

Werkzeugzählung: 43 `get_call_flow`, 30 `list_visible_projects`,
23 `research_project`, 22 `search_code`, eine `search_knowledge`.
**Null `get_code_entity`, null `trace_data_access`.** Von 41 erfolgreichen
Flow-Antworten sind 25 als gekürzt markiert, 20 bieten weitere Seiten.
Nur fünf erfolgreiche Flow-Anfragen enthalten einen Cursor.

`research_project` liefert direkt den Dienst-Flow aus `trace_call_flow`,
während `get_call_flow` eine eigene Projektion mit Quellbelegen und
Cursorfortsetzung erzeugt. Diese Verträge sollten gemeinsam abgenommen
werden. Verfügbare Folgeaktionen allein belegen noch keine Nutzung der
benötigten Originalquellen.

Zusätzlicher statischer Codebefund: `get_code_entity` fragt bei gesetzter
`chunk_id` nur diesen Chunk ab. Nach dessen Rest kann die Liste enden, obwohl
spätere Chunks zur Entity existieren. Im Benchmark wurde das Werkzeug nicht
aufgerufen, daher ist dies **kein dort beobachteter Laufzeitfehler**.
O-351 um eine Regression mit mindestens drei Chunks und einem innerhalb des
ersten Chunks erschöpften Zeichenbudget ergänzen.

### 5. Semantische Suche nicht betriebsbereit — O-251/O-345/O-356

`card-incident-02_r3_with_mcp` erhält von `search_knowledge`:
`embedding endpoint returned HTTP 404; check the active embedding profile URL and path`.
Die generische Folgeaktion aus einer leeren Symbolsuche hilft hier nicht.
Die bereits bekannte Profil-/Endpunktabnahme bleibt offen; zusätzlich muss
ein lesender Ersatzweg für nicht verfügbares semantisches Retrieval bestehen.

### 6. Fachliche Beleglücken bleiben — O-353/O-357

Alle fünf MCP-Incident-Antworten verfehlen laut Einzelkriterien den belastbaren
Summary-Betrag und die vollständige Ablaufdatumsrekonstruktion samt Default.
r1 setzt den Summary-Zuwachs unbelegt mit 150,00 an. Zuweisungen,
Verwendungsreihenfolge und Batch-Nachwirkungen benötigen Quellenabdeckung
über einzelne Kanten hinaus. Fehlende Kanten sind kein Negativbeweis.

Alle fünf MCP-CREATE-Antworten verfehlen die vollständigen Managerargumente
und Rücklesen/`afterCreate`; alle fünf MCP-UPDATE-Antworten lassen die
`REQUIRES_NEW`-Deklaration aus. Die Annotation ist im lokalen
`DefaultUserProvisioningManager.java` unmittelbar über dem betreffenden
Overload vorhanden. Das rechtfertigt gezielte Belegpakete und Bestandsabnahme,
aber keine Behauptung, sämtliche Informationen fehlten bereits im Parser.

### 7. UPDATE-Scores sind als Fehlersignal nur eingeschränkt brauchbar — O-354

8/10 UPDATE-Antworten erhalten 0/7. `sync-update-05_r2_with_mcp.md` beschreibt
trotzdem den REST-Diff, beide Managerpfade, Failure-Report, Statuskorrektur und
anschließenden Taskversuch. Die Bewertung zieht mehrfach die zu kurzen
Zeilenanker heran. Echte Auslassungen wie `REQUIRES_NEW` bleiben bestehen;
fachliche Korrektheit und präzise Zitierabdeckung müssen getrennt werden.

Noch deutlicher: r1 mit MCP beschreibt `update(UserPatch)` → `doUpdate` und
zitiert `UserServiceImpl.java:81–83`. Kriterium 1 wird dennoch mit der
Begründung abgewertet, diese Delegation sei nicht belegt. Eine unabhängige,
kriteriumsweise Nachprüfung ist notwendig. Die vorhandene Datei
`validation/chapter2-sync-update-05.rescore.json` betrifft Kapitel 2 und
validiert diese Kapitel-3-Bewertungen nicht. Originalscores erhalten.

## Konsequenz

Zuerst die konkrete Symbolsuche und den öffentlichen Eingabevertrag verbessern,
dann Quellenfortsetzung und fachliche Belegpakete am passenden Indexstand
abnehmen. CREATE kostet im Median der Paare zusätzliche 90,8 s, UPDATE
18,6 s; Serverzeit, Modellzeit und lokale Ersatzrecherche sind dabei noch
nicht getrennt. Optimierungswirkung anschließend mit korrigiertem,
eingefrorenem Bewertungsvertrag und unabhängigen Aufgaben messen.
Priorisierte Aufgaben und Abnahmekriterien stehen ausschließlich in
[TODO.md](TODO.md) unter „MCP-Folgearbeiten aus Kapitel 3“.
