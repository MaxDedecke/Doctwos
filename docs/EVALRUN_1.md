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

### RunPod-Vorbereitung am 28.09.2026 (BGE-M3)

Dieser Lauf verwendet den Pod `zlvxw8vam438nz` mit Ollama 0.34.4,
`qwen3:32b` für Chat und `bge-m3` für Embeddings. Beide Modelle wurden auf dem
Pod geladen. Der direkte Chat-Smoke antwortete korrekt; `/api/embed` und ein
Aufruf aus dem Doctus-Parser lieferten jeweils 1024 Dimensionen. Nach der
Profilumschaltung und dem Backend-Neustart meldete Doctus `/health` HTTP 200
mit `database`, `redis` und `ollama` jeweils `ok`. Das aktive Chatprofil ist
Nr. 58, das neue, separate RunPod-BGE-Profil Nr. 4. Das bisherige lokale
BGE-Profil Nr. 3 blieb erhalten.

Die aktuellen Projekte sind Syncope 1246 / Git-Quelle 1004 und CardDemo
1247 / Git-Quelle 1005. CardDemo wurde nicht reindiziert und behielt 2.857
`bge-m3`-Chunks mit 1024 Dimensionen. Syncope hatte vor dem Modellwechsel
46.649 `qwen3-embedding:4b`-Chunks. Der explizite BGE-Reindex wurde am
28.09.2026 gestartet, blieb aber bei `syncing`, 0/0 Dateien und 0 neuen Chunks
stehen. Auf Nutzeranweisung wurde der Celery-Task beendet; aktive Tasks und
Redis-Sync-Lock wurden als leer bestätigt. Danach wurde der vollständige
BGE-Reindex auf erneute Nutzeranweisung gestartet. Die Git-Vorbereitung
brauchte wegen wiederholter Dateilisten- und Abhängigkeitsberechnung zu lange;
beide Stellen wurden optimiert und der Worker neu gebaut. Der aktuelle Task
`e2c620e0-c354-4a84-90f3-2e453558f23c` läuft seit 09:34:34 UTC.
Um 09:34:37 waren 4.648 Dateien erfasst und die ersten Embeddings gestartet;
um 09:36 UTC waren 206 Dateien fertig. Syncope-Chatfragen warten auf den
vollständigen Index, CardDemo-Tests laufen parallel.

Nach knapp 20 Minuten Laufzeit (09:54 UTC) waren 2.180/4.648 Dateien und
16.897 BGE-Chunks fertig. Das vereinbarte 20-Minuten-Ziel ist damit nicht
erreicht. Die Rate schwankt mit Dateigröße und Chunkzahl; der Job bleibt aktiv.
Vier CardDemo-Chatfälle liefen in diesem Fenster parallel, ohne dass der
Syncope-Task anhielt. Ollama `/api/ps` zeigte dabei `bge-m3:latest` und
`qwen3:32b` vollständig im VRAM.

Beim abgebrochenen Lauf stufte der Parser BGE fälschlich als CPU-only ein:
Ollama nennt das Modell in `/api/ps` `bge-m3:latest`, der Parser verglich nur
mit `bge-m3`. Der Aliasvergleich in `parser/ollama_client.py` wurde korrigiert,
das Parser-Image neu gebaut und nur der Parser-Worker neu erstellt. Ein
anschließender Live-Aufruf von `is_gpu_accelerated('bge-m3')` **im neuen Worker**
lieferte `True`. Ollama meldete für BGE `size_vram=664000265` bei gleicher
Modellgröße, also vollständige VRAM-Residenz. Eine direkte `nvidia-smi`-Messung
war nicht möglich: der direkte SSH-Port verweigerte die Verbindung, der
RunPod-SSH-Proxy den vorhandenen Schlüssel. Die GPU-Rechenauslastung ist daher
nicht direkt messbar; die Zielzeit von 20 Minuten wurde verfehlt. Aus dem früheren
Syncope-Stand von 46.649 Chunks ergeben sich für 20 Minuten mindestens rund
39 Chunks pro Sekunde zuzüglich Parsing- und DB-Zeit.

**Laufende Messung:** Fortschritt, Chunkrate, Modellresidenz, Queue-Wartezeiten
und Fehler während des Imports prüfen. Die historischen Qwen-Embedding-
Anweisungen oben gelten für diesen BGE-Lauf nicht.

### RunPod-Abnahme der Agenten-MCP-Funktionen (O-342–O-345)

Für diese Abnahme Ollama in RunPod als **Chatmodell** im Doctus-Remote-Profil
verwenden und den Doctus-Agenten mit dem vorgesehenen, berechtigten MCP-Server
starten. RunPod stellt das Modell bereit; die MCP-Tools werden vom Doctus-
Agenten/Backend angeboten. Ein direkter MCP-Aufruf aus einem IDE-Client wäre
ein separater Client-Abnahmepfad und zählt nicht als Agentenlauf in dieser
Checkliste. Während des Vergleichs weder MCP-Konfiguration noch Modell,
Projekt-Index oder Frageformulierung wechseln.

1. **Sichere Erreichbarkeit:** Im RunPod-Pod Ollama auf `0.0.0.0:11434`
   binden und HTTP-Port 11434 beim Pod anlegen. Die Ollama-API nicht dauerhaft
   ungeschützt öffentlich lassen: Zugriff mit einer Authentifizierungsschicht
   und/oder zeitlich begrenzter, eng beschränkter Erreichbarkeit absichern.
   Geheimnisse nur in Doctus-Profilen beziehungsweise dem Secret Store
   hinterlegen. RunPod-URLs mit Query-/Token-Anteilen nie in Logs oder dieses
   Protokoll kopieren.
2. **API- und Modell-Readiness:** `/api/version` und `/api/tags` müssen HTTP
   200 liefern. Vorhandensein der exakten Kennungen `qwen3:32b` und
   `qwen3-embedding:4b` festhalten. Wenn der Pod neu ist, beide Modelle einzeln
   laden und ein persistentes Volume für Ollamas Modellbestand verwenden.
3. **Doctus-Profil-Smokes:** Remote-Ollama-Chatprofil aktivieren und eine kurze
   normale Chatantwort prüfen. Das unabhängige Embedding-Profil mit
   `qwen3-embedding:4b` und Dimension 1024 testen; zusätzlich im Backend-/Parser-
   Netz einen echten `/api/embed`-Aufruf mit `dimensions: 1024` ausführen und
   Antwortvektor-Länge 1024 bestätigen. Ein `404` auf `/api/embed` ist ein
   Stop-Kriterium für alle semantischen Retrieval- und Reindex-Tests. Nicht
   durch einen anderen Pfad oder ein anderes Modell stillschweigend umgehen.
   Bei diesem Fehler können rein symbol-/graphbasierte Diagnosen separat
   weiterlaufen, müssen aber als solche gekennzeichnet sein.
4. **MCP-Preflight:** Einen neuen Doctus-Agentenlauf starten und im sichtbaren
   Preflight prüfen, dass der erwartete Server `available` ist und `tools/list`
   die vorgesehenen lesenden Tools enthält. Zusätzlich kontrollieren, dass nur
   das ausgewählte Projekt sichtbar ist. `not_configured`, `unavailable` oder
   eine leere Tool-Liste bedeutet: Agenten-/MCP-Abnahme anhalten und erst die
   Konfiguration beziehungsweise Verbindung korrigieren.
5. **Einfacher Tool-Aufruf als Referenz:** Eine konkrete, quellengestützte
   Java- und COBOL-Frage stellen. Jeweils Tool-Name, Aufrufstatus, Dauer,
   Ergebnis, Quellenbeleg, Antwortdauer und sichtbare Nutzerkorrekturen
   protokollieren. Bei COBOL zuerst sicherstellen, dass die erwarteten Dateien
   strukturiert indiziert sind und kein relevanter Textfallback vorliegt.
6. **O-342 Vergleich:** Für mindestens drei typische Projektfragen pro Sprache
   zwei frische Unterhaltungen mit gleicher Frage, gleichem Modell, gleichem
   Index und gleichem MCP-Server ausführen: (a) mit den bisherigen Such-/Call-
   Flow-Tools und (b) mit `research_project`. Anzahl Tool-Aufrufe, Modell-Turns,
   Antwortzeit und Beleg-/Richtigkeitsbewertung vergleichen. Keine Antwort aus
   dem ersten Lauf in den zweiten Verlauf übernehmen.
7. **O-343 Einstiegsauflösung:** Im CardDemo-Bestand je einen vorab
   identifizierten Fall mit eindeutigem, mehrdeutigem und fehlendem
   Programmeinstieg prüfen. Erwartung anhand der MCP-Antwort festhalten:
   `unique_cobol_entry` benennt die eindeutige Wurzel; Mehrdeutigkeit gibt
   Kandidaten zurück; fehlender Einstieg behauptet keine automatisch gewählte
   Wurzel. Wenn die reale Quelle keinen dieser Fälle enthält, einen isolierten
   Fixture-Fall verwenden und ihn nicht als Bestandsabnahme ausweisen.
8. **O-344 Grenzfälle:** Einen bekannten Call-Flow mit hoher Kantenzahl und
   eine paginierbare Nachbarschaft prüfen. Antwort muss gelieferte/verfügbare/
   ausgelassene Knoten und Kanten, den Kürzungsgrund und gegebenenfalls
   `next_cursor` korrekt ausweisen. Eine Folgeseite mit Cursor anfordern und
   bestätigen, dass `no_indexed_calls` nicht mit einem gekürzten Ergebnis
   verwechselt wird.
9. **O-345 Lauftelemetrie:** Zwei Kontrollläufe durchführen: einmal ohne
   verfügbaren/konfigurierten optionalen MCP-Server, einmal mit Server bereit,
   aber einer Frage, die kein Tool braucht. Danach einen gezielten Call-Flow-
   Diagnoselauf ausführen, der ein MCP-Tool benötigt. Preflight und Tool-Logs
   müssen unterscheiden zwischen `not_configured`/`unavailable`, verfügbar aber
   nicht aufgerufen, und erfolgreich/fehlerhaft aufgerufen; Server, Status und
   Laufzeit festhalten.

**Abnahmereihenfolge:** Endpoint geschützt und bereit → Modelle bestätigt →
Chat-Smoke → 1024-d Embedding-Smoke → MCP-Preflight → einfacher Referenzaufruf
→ O-342 Vergleich → O-343 Fälle → O-344 Grenzfälle → O-345 Kontroll- und
Diagnoseläufe. Bei Fehlern an einem Gate nur die davon unabhängigen späteren
Prüfungen fortsetzen und die Einschränkung im Ergebnisprotokoll nennen.

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

### RunPod MCP-Agentenlauf – Ergebnisprotokoll

Vor dem Lauf kopieren/ausfüllen. Keine API-Schlüssel, vollständigen geheimen
URLs, Kundeninhalte oder unredigierten Prompt-/Tool-Inhalte eintragen.

| Feld | Wert |
|---|---|
| Datum / Zeitzone | 28.09.2026 / UTC |
| RunPod-Pod-Bezeichner (ohne URL) / Laufzeitfenster | `zlvxw8vam438nz` / MCP-Läufe ca. 5 Minuten, danach A/B-Retry |
| Endpoint-Zugriffsschutz / Auth-Schicht bestätigt | `/mcp` ohne Bearer-Token HTTP 401; authentifizierte Toolaufrufe erfolgreich; beide temporären Tokens widerrufen |
| Doctus API-Version und SHA | Lokaler Doctus-Build-SHA nicht erfasst; RunPod Ollama `0.34.4` |
| Aktives Chatprofil / Modell / Kontext | Profil 58 / `qwen3:32b`; tatsächliches Profil-Kontextlimit nicht erfasst |
| Aktives Embeddingprofil / Modell / Dimension | Profil 4 / `bge-m3` / 1024 |
| `/api/version`, `/api/tags`, Chat-Smoke | HTTP 200; Ollama `0.34.4`, `qwen3:32b` und `bge-m3` vorhanden; Doctus-Chat-SSE erfolgreich |
| `/api/embed` mit `dimensions: 1024`, Ergebnisdimension | HTTP 200, Ergebnisvektor 1024 Dimensionen |
| MCP-Serverstatus / Tool-Anzahl / sichtbare Projekt-ID | `doctus-inbound` verfügbar; 7 lesende Tools; Qwen-Aufrufe in Projekt 1246/1247 |
| O-342: Fragefall, alte Tools Aufrufe/Turns, `research_project` Aufrufe/Turns | COBOL `research_project`: 1 MCP-Toolaufruf; Java-Methode einfacher Name: `no_exact_match`, exakter Klassenname: `entry_point_selection_required` mit `create`-Kandidat. Vollständiger quantitativer Alt-Tool-Vergleich offen. |
| O-342: Antwortqualität/Belege und Zeit je Variante | COBOL MCP-Antwort korrekt mit Root/Kantenstatus: 65,0 s; normale gleichlautende C1-Antwort 75,5 s, `sources=[]`; wortgleiche MCP-Antwort am Proxy 524, gekürzter Retry ohne Toolaufruf. Qualitativer Vorteil beobachtet, striktes A/B unvollständig. |
| O-343: eindeutiger / mehrdeutiger / fehlender Einstieg | Eindeutig bestanden: `unique_cobol_entry`, `MAIN-PARA`, 7 Knoten/8 Kanten; mehrdeutiger und fehlender Einstieg offen. |
| O-344: Graphlimit / Kürzungsgrund / Cursor-Folgeseite | Limit 3, `relationship_page_has_more`, Cursor `3` → `6`; beide Seiten 0 Kanten und 1 Dateiknoten. Ungültiger Cursor vom MCP abgewiesen, Qwen verschwieg den Fehlversuch final. |
| O-345: ohne Server / verfügbar ohne Aufruf / erfolgreicher Aufruf | Ohne Token: HTTP 401; erfolgreicher MCP-Clientlauf und MCP-Audit `success`/`error` belegt. Interner Doctus-Chat meldete `not_configured`; verfügbar-aber-nicht-aufgerufen nicht separat geprüft. |
| Fehler / bekannte Einschränkungen / Abnahme je O-Nummer | Siehe Direktlauf O-342–O-345 und C1-Kontrollvergleich unten; MCP-Token wurden widerrufen. |

### Lauf 28.09.2026: allgemeine Bestandsabnahme parallel zum Syncope-Import

CardDemo blieb auf Quelle 1005 und ihrem vorhandenen BGE-M3-Index. Der
Syncope-BGE-Reindex von Quelle 1004 lief während der folgenden Abfragen.

| Fall | Live-Befund | Dauer / First Token / Tools | Bewertung / Folge |
|---|---|---|---|
| C1 (`COPAUA0C.MAIN-PARA`) | Doctus-Chat, Projekt 1247, Quelle 1005, Qwen-Profil 58: nur `view_repo_file` Zeilen 1–150 als Tool-Schritt; Antwort behauptete Zeilen 220 ff., lieferte 0 Quellenobjekte, verschwieg die aufgelösten Aufrufe `1000-INITIALIZE` → `1100-OPEN-REQUEST-QUEUE` (Zeile 244) und `3100-READ-REQUEST-MQ` (Zeile 246) und bezeichnete `MAIN-PARA` → `9000-TERMINATE` (Zeile 224) entgegen dem Index als aufgelöst. Die drei Kanten wurden direkt gegen `code_edges` von Quelle 1005 geprüft. | 171,2 s / 64,7 s / 1 | 1/6 (Fundstellen 0, Richtigkeit 0, Nachvollziehbarkeit 1). O-317/O-318/O-319/O-321 weiter offen; neuer Bug O-346. |
| C2 (`COPAUA0C`-Copybooks) | Der einzige Tool-Aufruf war `get_repo_entities(limit=20)` ohne Dateifokus; er lieferte nur Entities aus `PAUDBUNL.CBL`. Die Antwort meldete `COPAUA0C` fälschlich als im Index unbelegt und enthielt 0 Quellenobjekte. Direkt in Quelle 1005 bestehen aber 16 `COPY`-Kanten für `COPAUA0C.cbl`: acht aufgelöst (`CCPAURQY`, `CCPAURLY`, `CCPAUERY`, `CIPAUSMY`, `CIPAUDTY`, `CVACT03Y`, `CVACT01Y`, `CVCUS01Y`) und acht offen (u. a. `CMQODV`, `CMQMDV`, `CMQV`). | 123,8 s / 87,3 s / 1 | 0/6; O-317/O-319 bleiben offen, neuer Bug O-347. |
| C3 (DB2-SQL) | Chat-Bootstrap `get_repo_entities(limit=20)` zeigte wieder nur `PAUDBUNL.CBL`; zweiter Tool-Aufruf las dort Zeilen 157–170. Die Antwort erfand einen `EXEC SQL`/`SELECT AUTH_TYPE, AUTH_STATUS FROM AUTHORIZATION_SUMMARY`-Block in Zeilen 207–247 und gab 0 Quellenobjekte zurück. Der Originaltext dieser Zeilen enthält `CALL 'CBLTDLI'` für IMS und keinen SQL-Block; im Index sind für `PAUDBUNL.CBL` 0 `sql_block`-Entities, für `COTRTLIC.cbl` 16. | 186,1 s / 155,9 s / 2 | 0/6; schwerer Quellenkonsistenzfehler O-346. |
| C4 (Copybook-Feldkette) | Chat-Bootstrap lieferte erneut nur `PAUDBUNL.CBL`; danach suchte das Modell irrtümlich `COPY COPAU00.cpy` und meldete die Kette unbelegt, `sources=[]`. Im Index existiert aber z. B. `CCPAUERY.cpy:24` (`ERR-LOCATION`) → aufgelöste `COPY`-Kante in `COPAUA0C.cbl:185` → aufgelöste `USES`-Kante aus `1100-OPEN-REQUEST-QUEUE` in `COPAUA0C.cbl:273`. | 172,4 s / 127,7 s / 2 | 0/6; O-317/O-319, O-346/O-347. |
| C5 (Grenzen und Indexvollständigkeit) | Wieder nur `get_repo_entities(limit=20)` mit `PAUDBUNL.CBL`-Treffern; danach pauschal „nicht belastbar belegt“, `sources=[]`. In Quelle 1005 sind 61 JCL-Dateien als `text_fallback` markiert und `COPAUA0C.cbl:262` enthält einen unaufgelösten `CALL MQOPEN`; beides blieb unerwähnt. | 138,1 s / 66,1 s / 1 | 0/6; genereller Recherche-Bootstrap O-347, C5-Fachabnahme offen. |
| C6 (COBOL-Recovery) | Der Agent öffnete korrekt beide Ziel-Dateien, aber jeweils nur Zeilen 1–150. Er behauptete danach einen erfundenen `EXEC SQL SELECT ... FROM ACCT_MASTER` in `COPAUA0C.cbl:484–488` (dort steht ein CICS-/Dateiaufruf) und einen erfundenen Cursor in `COTRTLIC.cbl:560ff` (dort steht `IF EIBCALEN ... PERFORM 1000-RECEIVE-MAP`). Außerdem erklärte er vorhandene `PROCEDURE`-/SQL-Strukturen fälschlich zu Textfallback. Als Quellen wurden nur beide Dateizeilen 1 genannt, nicht die behaupteten Belege. Der Index hat trotz `partial` 32 `COPAUA0C`-Paragraphen und 16 `COTRTLIC`-`sql_block`-Entities. | 258,0 s / 167,0 s / 2 | 2/6 (Dateifokus 1, Richtigkeit 0, Tool-Nachvollziehbarkeit 1); O-305 bleibt offen, Quellenkonsistenz O-346. |
| Process View C1 | `GET /process/focus` mit Entity 122000 und Projekt 1247: HTTP 200, 16 Knoten, 18 Übergänge, keine Kürzung bei 30/50-Grenze. `MAIN-PARA` → `1000-INITIALIZE` (Zeile 222) und → `2000-MAIN-PROCESS` (223) als `certain`, → `9000-TERMINATE` (224) als `unresolved`, jeweils mit Original-Locator. Bei 3/2-Grenze: 3 Knoten, 2 Übergänge, `truncated=true`, Grund `edge_limit`. | ohne LLM | Technische Teilabnahme O-292–O-295 für diesen COBOL-Fall; UI-/Java-Abnahme bleibt offen. |
| O-321 Call-Flow-Service | `trace_call_flow(project_id=1247, entity_id=122000, hops=2)` löste die Wurzel exakt als `COPAUA0C.MAIN-PARA` in `COPAUA0C.cbl:220` auf; 7 Knoten/8 Kanten, darunter `9000-TERMINATE` offen und beide Aufrufe von `1000-INITIALIZE` aufgelöst. | ohne LLM | Serverseitige Teilabnahme bestanden; der Chat nutzte den vorhandenen Beleg in C1 nicht. |
| O-288 `PERFORM THRU` | Die drei `MAIN-PARA`-Kanten in `COPAUA0C.cbl:222–224` tragen `meta_json.thru` (`1000-EXIT`, `2000-EXIT`, `9000-EXIT`) und Original-Locators; der nicht auflösbare dritte Einstieg bleibt `unresolved`. | ohne LLM | Technische Teilabnahme der `THRU`-Belege am Bestand; SQL-Include/FD-Beziehungen separat offen. |
| C6 Indexbasis | Quelle 1005 meldet `COPAUA0C.cbl` und `COTRTLIC.cbl` weiterhin als `partial` mit lokalen COBOL-Syntaxdiagnosen. Trotzdem bestehen für `COPAUA0C` 1 Programm, 32 Paragraphen, 116 Datenfelder und 20 `exec_block`-Entities; für `COTRTLIC` 1 Programm, 1 Paragraph, 251 Datenfelder und 16 `sql_block`-Entities. | ohne LLM | Struktur wird nicht vollständig verworfen; O-305-Fachabnahme bleibt offen, weil CardDemo vereinbarungsgemäß nicht neu indiziert wurde. |
| C5 Indexbasis | Quelle 1005 hat 61 JCL-Dateien mit `parse_status=text_fallback` und keine JCL-Code-Entities. `COPAUA0C.cbl:262` hat dagegen eine explizite, unaufgelöste `CALL`-Kante nach `MQOPEN`. | ohne LLM | Diese Unterscheidung muss die C5-Chatantwort treffen. |
| O-193 Suchfokus | `GET /search?q=COPAUA0C&project_id=1247` lieferte 198 Entity-Treffer und 1 Dokument; mit zusätzlichem `source_id=1005` verschwanden sämtliche Entity-Treffer, obwohl sie dieser Quelle angehören. | ohne LLM | Quellenfilter-Bug O-348. |
| O-347 Fokus-Fix | Nach Backend-Neubau und Neustart lieferte ein kurzer Live-Stream-Probe für die bloße Programm-ID `COPAUA0C` als ersten Tool-Aufruf `view_repo_file(COPAUA0C.cbl:1–150)`. Für `COPAUA0C.MAIN-PARA` lieferte er `get_repo_entities` mit `entity_names=['COPAUA0C','MAIN-PARA']` und dem exakten `COPAUA0C.cbl`-Pfad. Beide Probes wurden nach dem ersten Tool-Aufruf beendet, ohne einen weiteren Qwen-Antwortlauf auszulösen. | ohne vollständige LLM-Antwort | Bootstrap-Korrektur live bestätigt; fachliche Antwortabnahme ausstehend. |
| C2 Wiederholung nach Fokus-Fix | Der neue Bootstrap öffnete `COPAUA0C.cbl:1–300`. Qwen nannte sechs lokale Copybooks mit zutreffenden `COPY`-Zeilen (178–206) und sechs offene MQ-Copybooks (149–170), statt die Datei für unbelegt zu erklären. Die Antwort enthielt Quellenobjekte für `COPAUA0C.cbl:178` und README. Ein Graph-Tool für den tatsächlichen `resolved`-/`unresolved`-Status wurde nicht aufgerufen; zwei weitere lokale Beispiele fehlen. | 124,9 s / 64,5 s / 1 | 4/6 (Fundstellen 2, Richtigkeit 1, Nachvollziehbarkeit 1). O-347-Fokus live verbessert; Statusbeleg weiterhin offen. |
| O-320 Dateibaum | `GET /projects/1247/files` und `GET /knowledge-sources/1005/files` lieferten HTTP 200 und enthielten sowohl `COPAUA0C.cbl` als auch `COTRTLIC.cbl`; der Projektbaum enthielt 329 Dateipfade. | ohne LLM | Technische Teilabnahme für die beiden Zielpfade; rekursive Agentensuche bleibt offen. |

### Abnahmestand nach dem Lauf

Für die allgemeine LLM-Bestandsabnahme sind **11 Evaluierungsfälle noch offen**:
J1–J5 (Syncope Java) wurden in diesem RunPod-Lauf nicht erneut ausgeführt;
C1–C6 (CardDemo COBOL) wurden zwar ausgeführt, erreichten aber keine vollständige
Abnahme. C2 verbesserte sich nach dem Bootstrap-Fix von 0/6 auf 4/6, bleibt
wegen fehlender Kantenstatus-Belege und unvollständiger Beispiele offen. Die
übrigen C-Fälle sind ebenfalls offen; Einzelbefunde und Folgetodos stehen oben.

Die vier MCP-Punkte O-342–O-345 sind **zurückgestellt und weiterhin offen**;
sie waren in diesem Lauf ausdrücklich keine Priorität. Der separate vLLM-
Vergleich ist noch nicht ausgefüllt.

Der letzte bekannte Zwischenstand des Syncope-Imports vor der Lesesperre war
3.318/4.648 Dateien. Abschlussstatus und endgültige Chunk-Zahl sind hier nicht
verifiziert. CardDemo blieb unverändert auf Quelle 1005.

### Historische Einzelresultate vom 22.09.2026

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

### RunPod-Wiederholung 28.09.2026: aktives Doctus-Profil und Antwortbindung

Erneut live über die lokale Doctus-Chat-API angemeldet und das konfigurierte
Chatprofil **58 (RunPod Ollama – Qwen 32B, `qwen3:32b`)** sowie das aktive
Embeddingprofil **4 (RunPod BGE-M3, 1024 Dimensionen)** verwendet. Projekt 1246 /
Quelle 1004 ist Syncope; Projekt 1247 / Quelle 1005 ist CardDemo. Für jede Frage
wurde eine frische Chat-Unterhaltung verwendet. Antworten wurden als SSE,
Quellenobjekte, Tool-Aufrufe und Laufzeiten gesichert. Die Passagen unten sind
dieser Wiederholung zugeordnet und ersetzen nicht die älteren Messwerte.
RunPod-Ollama meldete Version `0.34.4`; `/api/tags` enthielt `qwen3:32b` und
`bge-m3`. `/api/ps` zeigte beide Modelle resident im GPU-VRAM (Qwen ca. 31,4 GB,
BGE-M3 ca. 664 MB); ein direkter BGE-M3-`/api/embed`-Aufruf mit
`dimensions: 1024` lieferte 1024 Werte.

| Fall | Live-Befund | Dauer / First Token / Tools | Bewertung (0–6) |
|---|---|---:|---:|
| J1 | Zwei passende Tools, Klassenzeilen 36–50 abgerufen. Typen und Felder korrekt erklärt; ausgegebene Quellenobjekte nennen aber nur Zeile 37 und decken `UserDAO`/`UserLogic` an Zeilen 40–43 nicht ab. | 129,5 s / 106,9 s / 2 | 4/6; Zitationsumfang unvollständig (O-346) |
| J2 | `trace_call_flow` lief für `UserServiceImpl.create` (Entity 142759, 5 Hops) und lieferte den passenden Graphkontext. Finale Antwort verwarf das Ergebnis pauschal als unbelegt und gab `sources=[]` zurück. | 241,6 s / 176,3 s / 2 | 2/6; Toolresultat nicht in Antwort übernommen (O-346) |
| J3 | Beide `logic`-Module in den richtigen POM-Dateien unterschieden und Pfad-Qualified-Names erklärt. Die Frage nach allen Core-Untereinträgen wurde nur mit `logic` beantwortet; kein POM-Dateitext wurde geöffnet. | 145,4 s / 134,1 s / 1 | 3/6; teilweise, Moduleliste nicht vollständig |
| J4 | Entity-Suche fand alle drei XSLT-Templates samt Definitionsbereichen. Tool lieferte keine Template-Aufrufkanten; interne Analyse behauptete konkrete Calls, finale Antwort erklärte dennoch alles für unbelegt und lieferte keine Quellen. | 76,3 s / 59,8 s / 1 | 2/6; widersprüchliche Analyse/Finalantwort, Quellen leer (O-346) |
| J5 | Kernklasse korrekt von FIT- und SCIMv2-Klassen abgegrenzt; alle drei Pfade und Quellzeilen als Quellenobjekte ausgegeben. | 70,6 s / 59,0 s / 1 | 6/6 |
| C1 | Programm und Paragraph wurden im exakten `COPAUA0C.cbl`-Pfad aufgelöst. Kein Call-Flow-Tool; interne Analyse erfand Kanten/Zeilen, Finale verwarf die Frage als unbelegt und lieferte `sources=[]`. | 66,0 s / 29,4 s / 1 | 1/6; O-346 reproduziert, Fokus-Fix allein reicht nicht |
| C2 | Korrekte Datei vollständig gelesen. Antwort trennte Repository- von MQ-Copybooks mit passenden Beispielen; einige vorhandene COPY-Einträge aus beiden Gruppen fehlten. Quellenobjekt deckte die Datei ab. | 195,9 s / 174,8 s / 3 | 4/6; Fokus verbessert, Vollständigkeit offen (O-347) |
| C3 | Allgemeiner Bootstrap fand wieder `PAUDBUNL.CBL`; der Agent las dort Zeilen 157–286 und erfand einen anderen Programm-/SQL-Block in `COTRTUPC.CBL`, dazu `sources=[]`. | 142,1 s / 124,8 s / 2 | 0/6; Quellenkonsistenz-Bug O-346 reproduziert |
| C4 | Programm-ID-Fokus öffnete `COPAUA0C.cbl`, danach nur eine generische Entity-Suche nach `COPY`/`USES`. Vorhandene Feld-/COPY-/USES-Kette wurde pauschal als unbelegt zurückgewiesen, Quellen leer. | 68,7 s / 43,3 s / 1 | 1/6; Retrieval-Tiefe und Belegausgabe offen |
| C5 | Allgemeiner Bootstrap lieferte keine zielgerichteten COBOL-/JCL-Belege; Antwort verweigerte pauschal und lieferte `sources=[]`. | 119,2 s / 88,5 s / 1 | 0/6; O-347-Retrieval-Bootstrap weiter lückenhaft |
| C6 | Beide genannten Dateien wurden als Fokus an die Entity-Suche übergeben, aber kein Dateiinhalt geöffnet. Die Antwort blieb pauschal unbelegt, ohne erwartete Parser-/Indexbefunde oder Quellen zu zeigen. | 102,3 s / 35,7 s / 1 | 2/6; O-305 fachlich nicht abgenommen |

**Ergebnis:** Java 17/30, COBOL 8/36 nach obiger 0–6-Rubrik. Fünf Java-Fälle
bestätigen, dass Profil, Anmeldung, Streaming und Basis-Retrieval grundsätzlich
funktionieren; J2/J4 zeigen dennoch, dass Toolresultate nicht zuverlässig in
Antworten und Quellen übergehen. C2 ist mit vollständigem Dateifokus teilweise
bestanden; C1 und C3–C6 bleiben fehlgeschlagen bzw. offen. Wiederkehrendes
Muster ist der Repository-Bootstrap auf `PAUDBUNL.CBL` statt dem in der Frage
genannten Ziel sowie das Verwerfen oder Erfinden von Belegen. Keine Codefixes
wurden in diesem Lauf vorgenommen.

Zusätzliche Live-Prüfungen: unauthentifizierter `POST /chat` lieferte HTTP 401.
Die Quellensuche `GET /search?q=COPAUA0C&project_id=1247&source_id=1005&types=entity`
lieferte HTTP 200 mit `counts={}` und null Treffern; das bestätigt O-348 erneut.
Ein erneuter direkter `GET /graph/neighborhood`-Aufruf für Entity 121997 und
`code_dependency` lieferte HTTP 200, einen Dateiknoten, null Kanten/`total_edges=0`
und zugleich `has_more=true`, Cursor `10` sowie `truncated={incoming:true,
outgoing:true}`. Das Ergebnis verweist auf `COPAUA0C.cbl`, enthält aber keine
Kanten, daher keine vollständige Graphabnahme.
MCP war in Chat-Läufen nicht konfiguriert (Preflight `not_configured`, 0 Tools)
und blieb gemäß Priorisierung außerhalb dieser Abnahme. Die Such-API und der
unauthentifizierte Berechtigungspfad sind geprüft; die Graph-Agentenansicht/UI
wurde in dieser Wiederholung nicht bedient.

### Direktlauf O-342–O-345 mit Qwen als MCP-Client (28.09.2026)

Für diesen getrennten MCP-Client-Lauf wurde ein persönlicher eintägiger Doctus-
Testtoken angelegt und nach den Toolaufrufen widerrufen (HTTP 204). Der Token
steht nicht in diesem Protokoll. Qwen `qwen3:32b` auf RunPod erhielt die echte
`tools/list`-Antwort von `doctus-inbound` und rief die Tools über Streamable HTTP
auf. Die geschützte MCP-Audit-API wurde anschließend gelesen; keine Datenbank-
Direktabfragen.

| Punkt | Qwen/MCP-Ablauf und Ergebnis | Dauer / Audit |
|---|---|---|
| MCP Preflight | `initialize` erfolgreich; `tools/list` enthielt 7 lesende Tools: `list_visible_projects`, `search_code`, `research_project`, `get_code_entity`, `get_call_flow`, `get_graph_neighbors`, `search_knowledge`. | — |
| O-342 COBOL | `research_project(1247, "COPAUA0C.MAIN-PARA", hops=2)` lieferte `unique_exact_match`, Root Entity 122000, 7 Knoten/8 Kanten. Die Root-Kanten an Zeilen 222/223 waren `resolved`, die `9000-TERMINATE`-Kante an 224 `unresolved`; Qwen gab die drei Stati und Zeilen korrekt wieder. | Qwen 65,0 s; Tool success 52 ms |
| O-342 Java | Query `UserServiceImpl.create` ergab `no_exact_match`. Die vollqualifizierte Klassenquery ergab `unique_exact_match` auf Entity 142751, aber `entry_point_selection_required`; Kandidaten enthielten `create` als ID 142759. Qwen nannte das fehlende Entry-Point explizit und erfand keine Kanten. Kein nachfolgender MCP-Aufruf auf ID 142759, daher Java-Call-Flow-Abnahme offen. | Qwen 43,2 s + 58,9 s; Tools success 177/258 ms |
| O-343 eindeutig | `get_call_flow(project=1247, entity=121997, hops=2)` meldete `unique_cobol_entry`, Root `COPAUA0C.MAIN-PARA` Zeile 220, 7 Knoten/8 Kanten, kein Kürzen. Qwen gab `entry_resolution` korrekt wieder. | Qwen 41,9 s; Tool success 6 ms |
| O-343 mehrdeutig/fehlend | In diesem kurzen Lauf nicht abgenommen; kein synthetischer Fixture-Fall angelegt. | Offen |
| O-344 Cursor | Qwen rief `get_graph_neighbors(entity=122000, limit=3)` auf: ein Dateiknoten, null Kanten, `has_more=true`, Cursor `3`; gültige Folgeseite mit Cursor `3` ergab erneut ein Dateiknoten, null Kanten, `has_more=true`, Cursor `6`. Qwen probierte dazwischen `abc123`; MCP gab `invalid cursor` zurück und das Audit markierte `error`. Qwen korrigierte danach den Cursor, ließ den Fehlversuch aber in der finalen Antwort unerwähnt. Der Paging-Vertrag funktioniert, aber die Graphantwort hat bei diesem Fokus trotz Fortsetzung keine Kanten. | Qwen 95,9 s; success 15/16 ms, error 1 ms, success 16 ms |
| O-345 Berechtigung / Telemetrie | MCP `POST /mcp` ohne Token: HTTP 401. Authentifizierte Tools wurden im Admin-Audit als `success`, ungültiger Cursor als `error` mit Toolname und Dauer protokolliert. Im normalen Doctus-Chat bleibt das MCP-Preflight `not_configured`; „Server verfügbar, aber nicht aufgerufen“ und dessen Chat-Telemetrie wurden nicht erzeugt. | Admin-Audit HTTP 200; Retention 90 Tage |

**MCP-Abnahmestand:** O-343 eindeutig bestanden, O-342 teilweise bestanden, O-344
teilweise bestanden mit fehlenden Kanten und einer von Qwen verschwiegenen
Toolfehlermeldung, O-345 teilweise bestanden. Der direkte MCP-Clientlauf belegt,
dass Qwen den Doctus-MCP-Endpunkt tatsächlich ansprechen kann. Er ist keine
Abnahme des Doctus-internen optionalen MCP-Preflights. Die Java-`create`-Kette,
mehrdeutige/fehlende COBOL-Einstiege und der Graph-Panel-UI-Pfad bleiben offen.

### MCP-Vorteil gegen normale Codeanalyse – C1-Kontrollvergleich

Normale Doctus-Chat-Baseline ohne MCP mit der festgelegten Frage zu
`COPAUA0C.MAIN-PARA`: 75,5 s, `mcp_preflight=not_configured`, 1 lokaler
`get_repo_entities`-Toolschritt, anschließend pauschal „nicht belegt“ und
`sources=[]`.

Ein semantisch gleicher Qwen-MCP-Lauf zu `COPAUA0C.MAIN-PARA` dauerte 65,0 s.
Qwen nutzte `research_project`; MCP gab Root, sieben Knoten, acht Kanten,
Quellzeilen und Status zurück. Qwen nannte die zwei aufgelösten Root-Aufrufe
und die offene `9000-TERMINATE`-Kante korrekt. Das zeigt für diesen Fall einen
Qualitätsvorteil des MCP-Kontexts; aus einem einzelnen, nicht exakt identischen
Prompt folgt kein allgemeiner Geschwindigkeitsvorteil.

Für ein striktes A/B wurde die C1-Frage wortgleich erneut im normalen Chat
abgeschickt und im MCP-Client vorbereitet. Der normale Chat reproduzierte das
Ergebnis in 75,5 s. Die erste wortgleiche MCP-Antwort endete am RunPod-Proxy mit
HTTP 524; ein Retry mit gekürzter Ausgabe dauerte 10,7 s, lieferte jedoch keine
Toolaufrufe und einen leeren Antworttext. Daher ist der wortgleiche A/B-Vergleich
nicht vollständig. Die erfolgreiche MCP-Kontrollfrage oben bleibt ein positiver
qualitativer Vergleich, nicht der vollständige O-342-Benchmark. Der temporäre
Vergleichstoken wurde nach diesen Versuchen widerrufen (HTTP 204).
