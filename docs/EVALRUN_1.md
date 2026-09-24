# EVALRUN_1 – Apache Syncope und AWS CardDemo mit RunPod

**Zweck:** Reproduzierbare fachliche und technische Evaluation der bestehenden
Doctus-Projekte Apache Syncope (Java) und AWS CardDemo (COBOL), sobald der
RunPod-Endpunkt bereitgestellt wird. Bei der Aufforderung „Schau dir
`EVALRUN_1.md` an und let's go – hier ist der Pod“ dieses Dokument als
Arbeitsablauf verwenden.

**vLLM-Status:** Für den nächsten RunPod-Termin vorbereitet, aber gegen diesen
Eval-Korpus noch nicht live abgenommen. Die weiter unten dokumentierten
Ollama-Werte bleiben die Referenz; diese Dokumentationsänderung selbst hat
keinen RunPod-Aufruf oder Reindex ausgelöst.

## Festgelegte Projekte und Indexstand

Stand der Doctus-Datenbankabfrage: 20.09.2026. Beide Quellen waren vollständig
abgeschlossen; die Synchronisation lief zuletzt am 18.09.2026.

| Sprache | Projekt-ID | Quelle-ID | Branch | Git-Commit | Dateien / geparst | Entities | Kanten | Chunks |
|---|---:|---:|---|---|---:|---:|---:|---:|
| Java | 727 – Apache Syncope 2.1.14 | 563 | `syncope-2.1.14` | `84ed68fb63cb05a723a90325aee8d2a2f081b4eb` | 4.648 / 4.458 | 31.036 | 246.468 | 43.829 |
| COBOL | 728 – AWS CardDemo (Mainframe Modernization Reference App) | 564 | `main` | `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e` | 329 / 254 | 10.400 | 6.987 | 3.635 |

Die Chunks beider Quellen sind mit `qwen3-embedding:4b`, Dimension 1024,
gespeichert. Das aktuell aktive Doctus-Profil heißt „RunPod Ollama – Qwen 32B“
(`qwen3:32b`, Protokoll `ollama`); als Embedding-Profil ist „RunPod Qwen
Embedding 4B (1024d)“ mit Kontext 8100 aktiv. Endpunkte und Schlüssel stehen
absichtlich nicht in dieser Datei. Beim Start den tatsächlich bereitgestellten
Pod mit diesen Profilen abgleichen und Zugangsdaten ausschließlich in Doctus'
Profilverwaltung verwenden.

Compose-Dienste waren bei der Vorbereitung gesund. Der Code-Branch stand auf
`65c86f1`; im Worktree lagen Änderungen zu O-273. Für den Lauf zählt der
tatsächlich ausgerollte Stand: Version/SHA aus der laufenden API festhalten und
nicht annehmen, dass der lokale Worktree bereits deployed ist.

### Ollama im RunPod vorbereiten

Der Ollama-Container im bereitgestellten Pod ist zunächst leer. Vor dem
Evaluationstart müssen die beiden in den Doctus-Profilen eingetragenen Qwen-
Modelle in genau diesem Ollama geladen sein:

```sh
ollama pull qwen3:32b
ollama pull qwen3-embedding:4b
ollama list
```

Die großen Modell-Downloads können durch Unterbrechungen der Verbindung oder
Sicherheitslimits gestoppt werden. Ollama verwaltet den Pull in Modell-Layern
und setzt abgebrochene Pulls beim erneuten Aufruf mit demselben Modellnamen
fort. Daher nach einer Unterbrechung denselben `ollama pull`-Befehl wiederholen
und den Ollama-Modell-Speicher des Pods auf einem persistenten Volume erhalten.
Den Container oder das Volume zwischen Versuchen nicht neu anlegen und keine
unvollständigen Ollama-Download-Dateien löschen. Die Ollama-API-Dokumentation
beschreibt das Fortsetzen abgebrochener Pulls ([Pull API](https://github.com/ollama/ollama/blob/main/docs/api.md#pull-a-model)).
Nach einer Security-Unterbrechung im Fortschritt prüfen, dass der Pull beim
vorhandenen Stand weiterläuft; ein harter Pod-Neustart ohne erhaltenes Volume
kann den Teilfortschritt verlieren.

Jedes Modell einzeln bis zum erfolgreichen Abschluss laden; erst wenn beide in
`ollama list` erscheinen, Doctus-Chat und Embedding prüfen und die Evaluation
starten. Modellkennung und bestätigten Ladezustand im Ergebnisprotokoll
festhalten. Zugangsdaten und vollständige Pod-URLs gehören weiterhin nur in die
Doctus-Profilverwaltung.

### vLLM im RunPod vorbereiten (Chat-/Tool-Calling-Eval)

Für den vLLM-Vergleich wird derselbe Doctus-Index verwendet. Das vermeidet eine
unnötige Neueinbettung: Chat- und Embedding-Profil sind getrennt. Das bestehende
Embedding-Profil `qwen3-embedding:4b` mit 1024 Dimensionen aktiv lassen, solange
der Lauf nur den Chat-Backendwechsel evaluiert. Ein Embedding-Modellwechsel
erfordert dagegen einen eigenen, konsistenten Reindex-Lauf.

**Modell und Startkonfiguration vor dem Pod-Start festhalten.** Als konkreter
Ausgangspunkt eignet sich `Qwen/Qwen2.5-Coder-14B-Instruct`; vLLM stellt es
unter einem stabilen Namen bereit. Falls im RunPod ein anderes Modell oder eine
quantisierte Variante gewählt wird, den exakten Repository-Namen, Revision und
Quantisierung dokumentieren und die Vergleichbarkeit entsprechend
einschränken.

Beispiel für einen vLLM-Server mit Qwen2.5-Tool-Calling:

```sh
vllm serve Qwen/Qwen2.5-Coder-14B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen2.5-coder-14b \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

Der Hermes-Parser ist für Qwen2.5 vorgesehen. Auto-Tool-Calling benötigt in
vLLM sowohl `--enable-auto-tool-choice` als auch `--tool-call-parser`; ohne
diese Optionen kann normaler Chat funktionieren, während Agenten-Tool-Aufrufe
fehlschlagen. Siehe die [vLLM Tool-Calling-Dokumentation](https://docs.vllm.ai/en/latest/features/tool_calling/).
Die konkrete Modell-Chat-Template-Kompatibilität mit der installierten vLLM-
Version gehört zur Abnahme.

Im Doctus-Backend-Netz (nicht nur im lokalen Browser) müssen vor den Evalfragen
diese API-Funktionen erreichbar sein:

1. `GET /health` liefert HTTP 200.
2. `GET /v1/models` liefert als Modell-ID genau den konfigurierten Namen
   `qwen2.5-coder-14b`.
3. `POST /v1/chat/completions` mit kurzem Prompt, registrierten Tools,
   `tool_choice: "required"` und `stream: false` liefert einen strukturierten
   `tool_calls`-Eintrag.

Der Doctus-Test des vLLM-Chatprofils soll diese Prüfungen ausführen. Erst wenn
auch der erzwungene Tool-Aufruf bestanden ist, mit J1–C6 beginnen. Der Test
erzeugt echte Inferenz und kann RunPod-GPU-Zeit verbrauchen. Bei Fehlern zuerst
Modell-ID, Parser/Chat-Template und die beiden vLLM-Flags prüfen; Fehler nicht
durch stilles Entfernen der Tools oder durch Wechsel auf einen anderen Index
kaschieren.

**Doctus-Profil:** ein Remote-Chatprofil mit Provider `vllm`, OpenAI-Chat-
Protokoll, Basis-URL des Pods mit `/v1`, Modell-ID exakt wie
`--served-model-name` und passendem API-Key, falls aktiviert. Der API-Key gehört
nur in die Profilverwaltung. Das separate Embedding-Profil bleibt auf dem
aktuellen Ollama-Modell, solange die Chunks unverändert bleiben. In den
Ergebnisdaten nur den nicht geheimen Host-/Pod-Bezeichner notieren, niemals
Token oder URL mit eingebettetem Token.

**Netzgrenze:** vLLM dokumentiert, dass der API-Key die API-Routen schützt,
`/health` jedoch nicht. Den RunPod-Endpunkt deshalb auf vertrauenswürdige
Netze beziehungsweise den benötigten Doctus-Zugriff beschränken und nicht
ungeschützt öffentlich lassen. Details: [vLLM Security](https://docs.vllm.ai/en/latest/usage/security/).

**RunPod-Preflight protokollieren:** GPU-Modell, Anzahl und VRAM, Treiber/CUDA,
vLLM-Version, Modell-Revision, dtype/Quantisierung, `--max-model-len`,
`--tensor-parallel-size`, GPU-Speichergrenze, Start-/Ladezeit sowie kalte und
warme Antwortzeiten notieren. OOM, KV-Cache-Fehler oder lange Queue-Zeiten mit
geheimnisfreier Fehlermeldung und den tatsächlich gesetzten Modellparametern
festhalten.

Dieser vLLM-Lauf prüft zunächst Chat und Agenten-Tools, nicht die Qualität eines
anderen Embedding-Raums. Die bestehende Ollama-Referenz nutzt `qwen3:32b`, der
vorgeschlagene vLLM-Start ein Qwen2.5-Coder-Modell. Daher ist der erste Vergleich
ein System-/Workflowvergleich und kein isolierter Benchmark des Inferenz-
Backends. Modell- und Größenunterschiede bei jeder Interpretation nennen.

### Lessons Learned und Run-2-Preflight (22.09.2026)

Der erste RunPod-Start benötigte bis zum betriebsbereiten Ollama-/Doctus-Setup
etwa 15 Minuten. Der Modell-Download war dabei nicht der Hauptverursacher und
dauerte ungefähr 5 Minuten. Für Run 2 ist eine Vorbereitungszeit von etwa 10
Minuten realistisch, wenn die folgenden Punkte als feste Checkliste verwendet
werden:

1. **Pod-Readiness zuerst prüfen:** Nach dem Start zunächst wiederholt
   `/api/version` und `/api/tags` gegen die RunPod-Proxy-URL prüfen. Erst bei
   HTTP 200 und erreichbarer Ollama-API die Modell-Pulls starten. Ein leerer
   `/api/tags`-Bestand ist beim ersten Start erwartbar.
2. **Modelle unverändert verwenden:** `qwen3-embedding:4b` und `qwen3:32b`.
   Die Pulls einzeln ausführen; bei Unterbrechung denselben Modellnamen erneut
   verwenden. Das persistente Ollama-Volume des Pods nicht löschen oder neu
   anlegen. Vor dem Profilaufbau mit `ollama list` beziehungsweise `/api/tags`
   beide Modelle bestätigen.
3. **Embedding-Vertrag fest einplanen:** Das Modell liefert nativ 2560
   Dimensionen. Für den bestehenden Doctus-Vektorraum muss der Ollama-Request
   das Top-Level-Feld `"dimensions": 1024` enthalten; `options.dimensions` und
   `truncate` sind dafür nicht ausreichend. Der produktive Doctus-Client sendet
   dieses Feld bereits. Vor dem Import einen echten `/api/embed`-Smoke-Test mit
   `dimensions: 1024` aus dem Backend-/Parser-Netz ausführen und die Länge der
   Antwort prüfen.
4. **GPU-Rechenlast getrennt vom VRAM prüfen:** `size_vram > 0` in Ollamas
   `/api/ps` beweist nur, dass das Modell (teilweise oder vollständig) im VRAM
   resident ist. Im aktuellen Lauf meldet der RunPod-Container gleichzeitig
   CPU-Load 100 % und etwa 3/32 GiB VRAM; damit ist GPU-Offload vorhanden, eine
   ausreichende GPU-Rechenauslastung aber noch nicht bewiesen. Für Run 2
   während einer aktiven `/api/embed`-Anfrage `nvidia-smi` beziehungsweise die
   RunPod-GPU-Telemetrie sampeln und CPU-Load, GPU-Utilization, VRAM und
   Prozessnamen zusammen protokollieren. `size_vram=0` oder dauerhaft nahezu
   null GPU-Utilization bei gleichzeitig gesättigter CPU bedeutet: Pod-/CUDA-
   Konfiguration und Ollama-Runner prüfen, bevor der Import bewertet wird.
5. **Embedding-Concurrency messen statt nur GPU-Präsenz abzuleiten:** Der
   Parser behandelt bereits jedes `size_vram > 0` als GPU-Beschleunigung und
   kann bis zu `EMBED_CONCURRENCY=20` Tasks erzeugen. Die gemeinsame Admission
   begrenzt diesen Lauf bei `INFERENCE_MAX_CONCURRENCY=4` und einem Chat-
   Reserve-Slot praktisch auf drei Batch-Requests. Im aktuellen Log gab es
   deshalb Batch-Wartezeiten bis rund 540 Sekunden. Für Run 2 einen kurzen
   Durchsatztest mit 1, 2 und 3 parallelen Embedding-Requests durchführen und
   den Wert nur übernehmen, wenn GPU-Utilization steigt und die Latenz pro
   Dokument nicht durch Queueing verschlechtert wird.
6. **Remote-Profil vorbereiten:** Kein lokales Ollama-Profil umstellen. Das
   kombinierte Remote-Profil verwendet `provider=ollama`, `protocol=ollama`,
   Chat-Pfad `/api/chat`, Embedding-Pfad `/api/embed`, Modell `qwen3:32b`,
   Embedding `qwen3-embedding:4b`, Embedding-Dimension `1024`,
   Embedding-Kontext `8100` und Chat-Kontext `8192`. Zusätzlich bleibt das
   unabhängige Embedding-Profil aktiv, weil Parser/Import und Retrieval diese
   Auswahl separat verwenden. Ein vorhandenes Profil mit altem Pod nur
   aktualisieren, nicht als Dublette neu anlegen.
7. **Profiltest vervollständigen:** Der allgemeine Profiltest prüft vor allem
   Erreichbarkeit und Modellnamen. Zusätzlich ist der echte Chat-Smoke-Test
   (`stream=false`, kurze Antwort) und der 1024-dimensionierte Embedding-Test
   erforderlich. Das verhindert, dass ein erreichbarer, aber dimensionsfalscher
   Endpunkt in den Import gelangt.
8. **Parser-Version vor Import abgleichen:** Backend- und Parser-Image-SHA
   festhalten und vor dem Lauf eine kleine Parser-Regression beziehungsweise
   einen Testimport ausführen. Im ersten Lauf war der Connector bereits auf das
   neue Fingerprint-Feld `decoder_policy` angepasst, während die Funktion
   `analysis_fingerprint()` im Parser-Image das Argument noch nicht akzeptierte.
   Dieser Mismatch wurde in `parser/core/analysis_fingerprint.py` behoben und
   der Parser-Worker neu gebaut. Der Fix muss Bestandteil des ausgerollten
   Parser-Images sein.
9. **Quellen nacheinander importieren:** Pro Pod nur einen großen Projektimport
   gleichzeitig starten. Der erste Versuch startete Syncope und CardDemo
   parallel; dadurch konkurrierten beide Läufe um die Embedding-Aufnahme und
   erschwerten die Statusdiagnose. Run 2 startet Syncope vollständig, prüft
   Fehler und Parserstatus, und startet CardDemo erst danach. Ein unterbrochener
   Lauf wird vor dem Neustart über einen vollständigen Reindex bereinigt.
10. **Datenbankzustand vorab prüfen:** Nicht auf die im Dokument genannten IDs
   `727/728` beziehungsweise `563/564` vertrauen. Diese IDs beschreiben den
   historischen Bestand. In einer leeren oder neu bereitgestellten Instanz
   Projekte und Git-Quellen zuerst anlegen, die dokumentierten Branches und
   Commits hinterlegen und anschließend die tatsächlich erzeugten IDs ins
   Ergebnisprotokoll schreiben.

Damit ist der Run-2-Ablauf: Pod/API bereit → beide Modelle vorhanden → Remote-
Profile aktualisieren/aktivieren → echte Chat-/Embedding-Smokes → Parser-SHA
prüfen → Syncope importieren → Syncope abnehmen → CardDemo importieren.

### Bekannte Indexlücken vor der Bewertung

- **Syncope:** 87 `.properties`-Dateien stehen im aktuellen Journal noch auf
  `skipped`; der ISO-8859-1-Fallback wurde erst nach der letzten Synchronisation
  ergänzt. Außerdem sind 6 Maven-Dateien als `error` und 15 XML-Dateien als
  `partial` markiert. Vor einer Qualitätsbewertung muss geprüft werden, ob der
  Parser-Worker mit den aktuellen Änderungen ausgerollt ist. Danach Syncope
  erneut verarbeiten und kontrollieren, ob die 87 Resource-Bundles jetzt
  dekodiert und indexiert sind. Die sechs Maven-Fehler bleiben einzeln zu
  prüfen.
- **CardDemo:** 21 COBOL-Dateien sind `complete`, 13 `partial` und 10
  `text_fallback`; 57 Copybooks sind `complete`, 5 `partial`. 61 JCL-Dateien
  liegen als `text_fallback` vor. 13 Binär- und 62 sonstige Textdateien sind
  übersprungen. Das ist der dokumentierte Ist-Stand, kein pauschales
  Parser-Pass/Fail-Kriterium. 62 `COPY`-Kanten sind aktuell unaufgelöst; ein
  Teil davon verweist auf nicht mitgelieferte MQ-Copybooks.
- Beide Quellen zuletzt am 18.09.2026 synchronisiert. Für einen Lauf gegen den
  aktuellen Parserstand zuerst Synchronisationsstatus und Deploy-SHA prüfen.
  Keine Datenbank oder Quelle löschen. Bei einer Reindexierung jeweils nur die
  betroffene Quelle verwenden und den Abschluss samt Fehlerstatus abwarten.
- Das aktive Embedding-Modell entspricht bereits dem in den Chunks gespeicherten
  Modell. Falls der Pod ein anderes Embedding-Modell oder eine andere Dimension
  nutzt, nicht einfach mit gemischten Vektorräumen fortfahren: Profilwechsel
  und notwendige Neueinbettung beider Testquellen zuerst klären.

## Startablauf, sobald der Pod vorliegt

1. **Pod-Daten aufnehmen:** erreichbare Basis-URL, Chat- und Embedding-Pfad,
   Modellkennungen, Protokoll, Auth-Verfahren und Laufzeitfenster erfassen.
   Keine Schlüssel in dieses Markdown oder Git schreiben.
2. **Doctus-Zustand aufnehmen:** laufende API-Version/SHA, Compose-Health,
   aktives Chat- und Embedding-Profil, Quellstatus, letzter Commit und
   Chunk-Modell/Dimension für Projekt 727 und 728 festhalten.
3. **Profile separat prüfen:** Bei Ollama Chat-Antwort und Embedding-Aufruf
   verifizieren. Bei vLLM zusätzlich `/health`, `/v1/models` und den erzwungenen
   Tool-Calling-Profiltest bestehen lassen. Das unabhängige Embedding-Profil
   muss weiterhin 1024 Dimensionen liefern. Erst dann den Fragenkatalog starten.
4. **Indexstand aktualisieren:** aktuelle Parseränderungen ausrollen, falls sie
   noch nicht aktiv sind; danach Syncope wegen der 87 übersprungenen
   `.properties`-Dateien reindizieren. CardDemo nur dann reindizieren, wenn der
   Quellen-/Parserstand nicht dem vereinbarten Laufstand entspricht. Vorher
   aktuellen Status und mögliche Laufzeit prüfen; der frühere CardDemo-Erstlauf
   dauerte laut Backlog etwa 75 Minuten.
   Für den O-305-Fall muss vor dem Fragenkatalog zusätzlich geprüft werden, dass
   `COPAUA0C.cbl` und `COTRTLIC.cbl` mit dem aktuellen COBOL-Parser verarbeitet
   wurden. Die beiden Dateien dürfen nicht als reiner Textfallback vorliegen;
   Divisionen, Paragraphen, Datenfelder und eingebettete SQL-/EXEC-Blöcke müssen
   im Index sichtbar sein. Reindex und anschließende Embeddings mit dem
   bereitgestellten RunPod-Profil als einen zusammengehörigen Lauf protokollieren.
5. **Projektweise ausführen:** pro Frage das passende Projekt explizit im Chat
   auswählen. Java-Fragen ausschließlich in Projekt 727, COBOL-Fragen in
   Projekt 728. Je Frage Antwort, Quellenbelege, sichtbare Tool-Schritte und
   Zeiten im Ergebnisprotokoll sichern.
6. **Lastprobe separat kennzeichnen:** nach den Einzelabfragen optional einen
   begrenzten Import-/Chat-Paralleltest ausführen. Chat-First-Token-Zeit,
   Importfortschritt, Wartezeit, Fehler und – soweit vom Pod sichtbar – GPU-
   Auslastung erfassen. Kein unbegrenzter Lasttest.

## Fester Fragenkatalog

Die Fragen wörtlich stellen und Antworten mit Quellenbelegen bewerten. Die
erwarteten Fakten unten dienen als Prüfhilfe, nicht als Text, der dem Modell
vorab gegeben wird. Eine offene oder dynamische Kante darf korrekt als solche
benannt werden; sie darf nicht als aufgelöste Beziehung ausgegeben werden.

### Java – Projekt 727 Apache Syncope

**J1 – Klassen- und Typbeziehungen**

> Erkläre anhand des indizierten Codes, wie `UserServiceImpl` im Modul
> `core/rest-cxf` typisiert ist. Welche Klasse erweitert sie, welches Interface
> implementiert sie, und welche Syncope-Typen nutzt sie? Bitte mit Fundstellen
> und Zeilenangaben.

Prüfpunkte: Datei
`core/rest-cxf/src/main/java/org/apache/syncope/core/rest/cxf/service/UserServiceImpl.java`;
`AbstractAnyService<UserTO,UserPatch>`, `UserService`, `UserDAO` und
`UserLogic` sind im aktuellen Index als Beziehungen vorhanden.

**J2 – REST-Service zu Logik**

> Verfolge in Syncope den Weg von `UserServiceImpl.create` zur fachlichen
> Benutzerlogik. Zeige die belegten Methoden und Kanten. Kennzeichne ausdrücklich,
> welche Aufrufkante aufgelöst ist und welche im Index offen bleibt.

Prüfpunkte: `UserServiceImpl` nutzt `UserLogic`; der aktuelle Graph zeigt bei
`create` unter anderem `logic.create` als unaufgelösten Aufruf. Eine Antwort,
die eine vollständig aufgelöste Aufrufkette behauptet, ist ein Fehler.

**J3 – Maven-Modulbaum**

> Welche Untermodule deklariert `core/pom.xml`, und wie unterscheidet Doctus das
> Modul `logic` dort vom gleichnamigen Modul in `ext/flowable/pom.xml`? Zeige
> beide Quellfundstellen.

Prüfpunkte: Beide `logic`-Module existieren. Die Qualified Names enthalten den
jeweiligen POM-Pfad und dürfen nicht zusammenfallen. Maven wird statisch
analysiert, nicht ausgeführt.

**J4 – XSLT-Struktur**

> Zeige in `core/rest-cxf/src/main/resources/wadl2html/index.xsl` die Templates
> `wadl:resource`, `methods` und `wadl:method`. Welche statisch belegten
> Template-Aufrufe oder Beziehungen verbindet Doctus zwischen ihnen?

Prüfpunkte: Templates und Quellzeilen müssen aus genau dieser XSL-Datei stammen.
Nicht im Graph belegte Aufrufpfade als Lücke melden.

**J5 – Mehrdeutiger Namensraum / Unsicherheit**

> Es gibt mehrere Klassen mit dem einfachen Namen `UserServiceImpl`. Finde die
> Syncope-Kernklasse im Modul `core/rest-cxf`, grenze sie von gleichnamigen
> Klassen in Erweiterungen oder FIT-Tests ab und nenne den vollständigen Pfad.

Prüfpunkte: Erwartet wird die Klasse unter
`core/rest-cxf/src/main/java/org/apache/syncope/core/rest/cxf/service/`;
gleichnamige Erweiterungs- und Testklassen dürfen nicht vermischt werden.

### COBOL – Projekt 728 AWS CardDemo

**C1 – Kontrollfluss im Autorisierungsprogramm**

> Beschreibe den belegten Kontrollfluss von `COPAUA0C.MAIN-PARA`. Welche
> Paragraphen werden ausgeführt und welche Folgeschritte ruft
> `1000-INITIALIZE` auf? Bitte mit Datei- und Zeilenbelegen und mit dem Status
> der Kanten.

Prüfpunkte: Datei
`app/app-authorization-ims-db2-mq/cbl/COPAUA0C.cbl`. `MAIN-PARA` führt unter
anderem `1000-INITIALIZE` und `2000-MAIN-PROCESS` aus; `9000-TERMINATE` ist
unaufgelöst. `1000-INITIALIZE` führt zu `3100-READ-REQUEST-MQ` und
`1100-OPEN-REQUEST-QUEUE`. Der Aufruf `MQOPEN` ist im aktuellen Graph
unaufgelöst.

**C2 – COPY und Copybook-Grenzen**

> Welche Copybooks bindet `COPAUA0C` ein? Trenne aufgelöste Repository-
> Copybooks von nicht aufgelösten MQ-Copybooks und nenne Beispiele für beide
> Gruppen.

Prüfpunkte: Aufgelöste Beispiele sind `CCPAURQY`, `CCPAURLY`, `CCPAUERY`,
`CIPAUSMY`, `CIPAUDTY`, `CVACT03Y`, `CVACT01Y` und `CVCUS01Y`. `CMQODV`,
`CMQMDV`, `CMQV` und weitere MQ-Namen sind im aktuellen Graph unaufgelöst.
Keine externe Definition erfinden.

**C3 – DB2-Embedded-SQL**

> Finde in CardDemo ein konkretes COBOL-Programm mit eingebetteten DB2-SQL-
> Blöcken. Erkläre anhand eines ausgewählten Blocks, welche Tabellen/Felder und
> Operationen der Quelltext tatsächlich belegt; zitiere die Originalzeilen.

Prüfpunkte: `COTRTLIC.cbl` enthält mehrere persistierte `sql_block`-Entities.
Tabellen- und Feldnamen müssen aus dem geöffneten Originalauszug stammen; keine
fachliche Bedeutung allein aus Bezeichnern ableiten.

**C4 – Feldverwendung**

> Verfolge für `COPAUA0C` ein in einem Copybook definiertes Datenfeld bis zu
> einer Verwendung im Programm. Zeige Definition, aufgelöste `COPY`-Beziehung
> und `USES`-Fundstelle. Wenn sich keine durchgängige Kette belegen lässt,
> benenne genau die fehlende Kante.

Prüfpunkte: Definitionen und Verwendungen müssen mit korrekter Quell- und
Zeilenangabe belegt sein; gleiche Namen allein beweisen keine Verbindung.

**C5 – Grenzen und Indexvollständigkeit**

> Welche Teile der CardDemo-Analyse sind strukturell belegt, welche liegen nur
> als Textfallback vor und welche Ziele bleiben dynamisch oder unaufgelöst?
> Nutze ein konkretes Beispiel aus COBOL und eines aus JCL.

Prüfpunkte: JCL ist im aktuellen Import Textfallback; nicht behaupten, daraus
sei ein vollständiger JCL-Jobgraph abgeleitet. Dynamische oder unaufgelöste
Ziele als solche kennzeichnen.

**C6 – COBOL-Syntax-Recovery und Struktur-Erhalt (O-305)**

> Prüfe im Projekt AWS CardDemo die Programme `COPAUA0C.cbl` und
> `COTRTLIC.cbl` nach dem aktuellen Reindex. Zeige für beide Dateien die
> erkannten Programm-/Divisions-/Paragraphenstrukturen und mindestens ein
> Datenfeld. Weise anhand von Originalzeilen nach, dass eingebettete
> `EXEC`-/SQL-Blöcke und mehrzeilige `IDENTIFICATION`-Metadaten die umgebende
> DATA- und PROCEDURE-Struktur nicht zerstören. Trenne echte Parser-
> Diagnosen, unaufgelöste Kanten und Textfallbacks. Wenn eine Aussage nicht
> belegt werden kann, benenne sie als Index-/Parserlücke.

Prüfpunkte: `app/app-authorization-ims-db2-mq/cbl/COPAUA0C.cbl` muss weiterhin
als Programm mit DATA- und PROCEDURE-Struktur (u. a. Zeilen 29 und 218) sowie
Paragraphen wie `MAIN-PARA` und `1000-INITIALIZE` (u. a. Zeilen 220 und 230)
auffindbar sein. `app/app-transaction-type-db2/cbl/COTRTLIC.cbl` muss die
mehrzeilige IDENTIFICATION-Angabe in den Zeilen 24–30, die DATA DIVISION ab
Zeile 35 und persistierte `sql_block`-Entities aus den EXEC-SQL-Blöcken behalten.
Ein lokaler Syntaxhinweis darf nicht zur vollständigen Textfallback-Antwort für
die Datei führen. Die Antwort muss die Originaldatei und Zeilen nennen; aus
Bezeichnern allein dürfen keine fachlichen Beziehungen erfunden werden. Dieser
Fall zählt als Parser-/Index-Abnahme und nicht als reiner Chat-Qualitätstest.

## Bewertung je Frage

Jede Frage mit 0–2 Punkten in drei Kategorien bewerten (maximal 6 Punkte):

| Kategorie | 0 Punkte | 1 Punkt | 2 Punkte |
|---|---|---|---|
| Fundstellen | keine oder falsche Quelle | richtige Datei, aber ungenaue/unvollständige Zeilen | richtige Datei und überprüfbare Zeilen |
| Fachliche Richtigkeit | wesentliche Erfindung oder falsche Beziehung | überwiegend richtig, wichtige Lücke/Unsicherheit fehlt | korrekt und Grenzen passend benannt |
| Doctus-Nachvollziehbarkeit | keine passenden Treffer/Tools | teilweise passende Treffer oder unvollständige Tool-Schritte | passende Recherche, sichtbare Tool-Schritte und nachvollziehbarer Belegpfad |

Zusätzlich pro Antwort First-Token-Zeit, Gesamtdauer, Anzahl der Tool-Aufrufe,
Fehler/Timeout und benötigte Nutzerkorrektur erfassen. Bei nicht belegbaren
Erwartungen den Fall als „Index-/Parserlücke“ protokollieren, nicht als reinen
LLM-Fehler.

## Ergebnisprotokoll

Vor dem Start ausfüllen; RunPod-Schlüssel oder vollständige geheime URLs nicht
eintragen.

| Feld | Wert |
|---|---|
| Datum / Zeitzone | 2026-09-22 / UTC |
| Doctus API-Version und SHA | Offen |
| RunPod GPU / VRAM | Offen |
| Chat-Profil / exakte Modellkennung | Ollama / `qwen3:32b` |
| Embedding-Profil / exakte Modellkennung / Dimension | Ollama / `qwen3-embedding:4b` / 1024 |
| Chat- und Embedding-Erreichbarkeit bestätigt | Ja; direkte Smoke-Tests und echter `/chat`-SSE-Test erfolgreich |
| Syncope Reindex-Stand / 87 Properties geprüft | Quelle 1004: completed, 4.545/4.648 Dateien; 103 skipped (Ressourcen-/Indexlücken weiter offen) |
| CardDemo Reindex-Stand | Quelle 1005: completed, 254/329 Dateien; 75 skipped, 25 partial, 140 text_fallback |
| Import-/Parser-Metriken | Syncope 4.545/4.648, CardDemo 254/329; erforderliche COBOL-Dateien `partial` |
| Durchschn. / Median First Token | Nicht separat aufgezeichnet (Follow-up) |
| Durchschn. / Median Antwortzeit | Java: 57,1 s / 57,4 s; COBOL: 96,9 s / 90,3 s |
| Gesamtpunkte Java (30 mögliche Punkte) | Vorläufig 12/30 |
| Gesamtpunkte COBOL (36 mögliche Punkte) | Vorläufig 10/36 |
| Fehlerfälle, Indexlücken und Folge-Todos | Initial falscher Dateifokus bei Entity-/COBOL-Fragen; nach API-Fix werden `COPAUA0C.cbl` und `COTRTLIC.cbl` gefunden, SQL-/Tiefenbelege bleiben offen; siehe O-316 und O-317–O-323 |

### vLLM-RunPod-Vergleich (separat ausfüllen)

Die obigen Werte sind der Ollama-Referenzlauf. Diese Tabelle beim nächsten
RunPod-Termin für vLLM neu ausfüllen. Gleiche Projekte, Indexstände,
Fragenformulierungen und Bewertungsregeln verwenden. Jede Frage in einer
frischen Unterhaltung starten; keine parallelen Imports während der
Einzelabfragen.

| Feld | vLLM-Lauf |
|---|---|
| Datum / Zeitzone | Offen |
| Doctus API-Version und SHA | Offen |
| RunPod-Pod-Bezeichner (ohne geheime URL) | Offen |
| GPU / Anzahl / VRAM / Treiber / CUDA | Offen |
| vLLM-Version / Modell-Revision | Offen |
| Exakte Modell-ID / Served-Model-Name | Offen |
| dtype / Quantisierung / max-model-len / Tensor Parallel | Offen |
| Chat-Profil / Provider / Protokoll | vLLM / OpenAI Chat |
| Embedding-Profil / Modell / Dimension | Bestehendes Ollama-Profil / `qwen3-embedding:4b` / 1024 |
| `/health`, `/v1/models`, Tool-Calling-Profiltest | Offen; alle drei müssen bestehen |
| Server-Startzeit / Modell-Ladezeit / kalter Aufruf / warmer Aufruf | Offen |
| GPU-Auslastung / VRAM während aktiver Anfrage | Offen |
| Syncope- und CardDemo-Quell-/Parserstand | Wie Ollama-Referenz bestätigen |
| Gesamtergebnis Java (30 mögliche Punkte) | Offen |
| Gesamtergebnis COBOL (36 mögliche Punkte) | Offen |
| Abweichungen, Fehler und nächste Schritte | Offen |

Beim Ergebnisvergleich die Modellabweichung (Ollama `qwen3:32b` gegenüber dem
tatsächlich verwendeten vLLM-Modell) berücksichtigen. Ein Backendvergleich mit
gleichem Modell ist erst möglich, wenn dieselbe Modellfamilie und möglichst
dieselbe Präzision auf beiden Servern bereitgestellt werden.

### Einzelresultate

| Fall | Retrieval-Beleg / Datei + Zeile | Punkte (0–6) | First Token | Gesamtzeit | Tool-Schritte | Befund / Follow-up |
|---|---|---:|---:|---:|---:|---|
| J1 | falsche `ImplementationServiceImpl.java` statt `UserServiceImpl` | 0 | n/a | 39,7 s | 1 | Retrieval-/Entity-Fokusfehler |
| J2 | FIT-/Flowable-Umwege, direkte Zielklasse nicht belegt | 1 | n/a | 68,5 s | 1 | Aufrufkette nicht nachvollziehbar |
| J3 | nur `ext/flowable/pom.xml`, `core/pom.xml` fehlt | 1 | n/a | 52,7 s | 1 | Maven-Kontext unvollständig |
| J4 | `index.xsl`, Templates und Beziehungen mit Zeilen genannt | 4 | n/a | 57,4 s | 1 | vorläufig bestanden, Kanten fachlich prüfen |
| J5 | Kernklasse und FIT/SCIM-Abgrenzung korrekt | 6 | n/a | 67,4 s | 1 | bestanden |
| C1 | `PAUDBUNL.CBL` statt `COPAUA0C.cbl` | 1 | n/a | 125,1 s | 2 | falscher COBOL-Dateifokus |
| C2 | einzelne Copybooks korrekt, erwartete Gruppen unvollständig | 2 | n/a | 45,4 s | 1 | COPY-/MQ-Abdeckung unvollständig |
| C3 | echtes COBOL mit `EXEC SQL INCLUDE`, aber nicht der erwartete SQL-Block | 2 | n/a | 111,6 s | 2 | Tabellen-/Operationsbeleg unvollständig |
| C4 | `COPAUS0C`/`COPAU01` statt `COPAUA0C`-Kette | 1 | n/a | 69,0 s | 1 | falscher Programmkontext |
| C5 | Kategorien grundsätzlich erkannt, konkrete Belege fachfremd | 2 | n/a | 51,2 s | 1 | Teilbefund, JCL nicht direkt belegt |
| C6 | `COPAUA0C` teilweise, `COTRTLIC.cbl` fälschlich nicht gefunden | 2 | n/a | 179,4 s | 3 | Parser-/Retrieval-Abnahme fehlgeschlagen |

## Entscheidung nach dem Lauf

Ergebnis je Sprache getrennt bewerten. Vorab keine pauschale Freigabe aus einer
Gesamtpunktzahl ableiten. Für jede kritische Fehlantwort die Ursache als
Retrieval, Parser/Index, Agenten-Tool-Nutzung, Modellantwort oder fehlendes
Referenzwissen einordnen. Danach priorisierte Folge-Todos mit konkreten
Fundstellen und reproduzierbaren Fällen in `docs/TODO.md`
übernehmen.
