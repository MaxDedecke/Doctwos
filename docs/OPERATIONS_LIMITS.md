# Betriebs- und Nutzergrenzen

Stand: 16.09.2026. Dieses Dokument trennt technische Schutzgrenzen von
Produkt-/Abrechnungsquoten. Doctus ist single-tenant und selbst gehostet;
Docker, PostgreSQL, Valkey und der verfügbare Speicherplatz bleiben deshalb
zusätzliche Grenzen der jeweiligen Kundenumgebung.

## Wirksame technische Grenzen

| Bereich | Grenze / Default | Quelle und Bedeutung |
|---|---:|---|
| Kontextnotiz einer Wissensquelle | 2.000 Zeichen | `backend/api/knowledge_sources.py::SOURCE_CONTEXT_NOTE_MAX_CHARS`; die Notiz wird bei jeder Chat-Anfrage in den Kontext übernommen. |
| Einzelner Git-Dateiread | 2 MiB | `parser/git_utils.py::MAX_READ_BYTES`; größere Dateien werden nicht als unbeschränkter Einzelread verarbeitet. |
| Confluence-Anhang | 20 MiB | `parser/connectors/confluence.py::ATTACHMENT_MAX_BYTES`. |
| Java-/Text-Chunk | 1.000 Zeichen | `parser/core/config.py::CHUNK_SIZE`; per Env anpassbar. Java-Struktur-Chunks werden zusätzlich symbolorientiert erzeugt. |
| Embedding-Nebenläufigkeit | 20, CPU-only 2 | `EMBED_CONCURRENCY` und `EMBED_CONCURRENCY_CPU_ONLY`; per Env anpassbar, um Ollama nicht zu überlasten. |
| Gemeinsame Inferenzkapazität | 4 Slots pro Endpoint, davon mindestens 1 für Chat und 1 für Batch-Arbeit | `INFERENCE_MAX_CONCURRENCY`, `INFERENCE_CHAT_RESERVE`, `INFERENCE_BATCH_RESERVE`; backend und Parser koordinieren Slots über Valkey/Redis. Die Batch-Queue wartet bis zu 900 s, Chat bis zu 30 s. Logs zeigen Queue-Eintritt, Wartezeit und belegte Slots; der Redis-Metrik-Hash enthält Requests, Drosselungen, Wartezeit und Slot-Auslastung. Slot-Auslastung ist ein Belegungsproxy des Endpunkts, keine GPU-Telemetrie. |
| Embedding-Batch | 20 Chunks | `EMBED_BATCH_MAX_CHUNKS` im Git-Konnektor; große Läufe werden in kleinere Ollama-Anfragen geteilt. |
| Knowledge-Graph-Übersicht | 2.000 Nodes | `KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES`; per Env anpassbar. Die API meldet eine abgeschnittene Übersicht. |
| Call-Graph-Fokus | 500 Nodes | `backend/api/callgraph.py::MAX_NODES`; verhindert unbounded BFS und übergroße Browser-Graphen. |
| Agenten-Ablauftrace | 150 Nodes, maximal 5 Hops | `backend/services/call_flow.py`; begrenzt Tool-Kontext und Mermaid-Diagramme bei hoher Aufruffächerung. |
| Graph-Retrieval im Chat | 1.800 Tokens | `backend/services/graph_retrieval.py::DEFAULT_GRAPH_TOKEN_BUDGET`; bleibt innerhalb des bestehenden Chat-Kontextbudgets. |
| MCP-Tool-Ergebnis im Agenten | 8.000 Zeichen | `backend/agent.py::MAX_MCP_TOOL_RESULT_CHARS`; lange Tool-Ergebnisse werden begrenzt. |
| MCP-Auditwerte | String 500 / Fehler 1.000 Zeichen, 50 Collection-Elemente, Tiefe 6 | `backend/services/mcp_audit.py`; sensible Werte werden vor der Speicherung redigiert. |
| Audit-Abfrage | 1–500 Einträge, Default 100 | `backend/api/audit.py`; Aufbewahrung standardmäßig 90 Tage über `MCP_AUDIT_RETENTION_DAYS`. |
| Diagnose-Laufhistorie | 50 Einträge | `backend/api/diagnostics.py`; dies begrenzt die Anzeige, nicht automatisch die Größe aller Diagnoseartefakte. |
| Fehlgeschlagene Logins | 5 freie Versuche, danach Backoff bis maximal 1 Stunde | `backend/core/login_throttle.py`; Redis- und dauerhafte DB-Sperre ergänzen sich. |
| Anwendungssession | 14 Tage | `backend/core/auth_dependency.py::SESSION_MAX_AGE_SECONDS`. |
| OIDC-State | 10 Minuten | `backend/core/oidc.py::OIDC_STATE_MAX_AGE_SECONDS`; schützt den Login-Callback gegen veraltete Zustände. |

Die O-258-Metriken liegen als Redis-Hashes `doctus:inference:v1:{endpoint-hash}:metrics` vor. Der Hash enthält aktuelle belegte Slots und Auslastung sowie Request-, Drosselungs-, Timeout- und Wartezeit-Zähler je Klasse (`chat`/`batch`). Den Hash findet man über den im Anwendungslog ausgegebenen Endpoint-Hash:

```bash
docker compose exec -T redis redis-cli --scan --pattern 'doctus:inference:v1:*:metrics'
docker compose exec -T redis redis-cli HGETALL 'doctus:inference:v1:{ENDPOINT_HASH}:metrics'
docker compose logs --since=30m backend-api parser-worker | rg inference_admission
```

`utilization_percent` beschreibt die belegten Doctus-Slots relativ zum konfigurierten Limit. Für GPU-/CPU-Auslastung des eigentlichen Modellservers gelten weiterhin dessen eigene Telemetriedaten.

Einige Grenzwerte sind bewusst konfigurierbar. Eine Erhöhung muss immer gegen
RAM/VRAM, Ollama-Durchsatz, PostgreSQL und Browserlast geprüft werden; sie ist
keine automatische Skalierung.

## Keine Nutzer- oder Speicherquote

Aktuell gibt es keine harte, per Nutzer durchgesetzte Quote für:

- Anzahl der Benutzer, Projekte oder Wissensquellen insgesamt,
- Gesamtgröße eines Repositorys oder der Uploads,
- Anzahl indexierter Dateien, Chunks, Entities oder Kanten,
- Embedding-/LLM-Verbrauch pro Nutzer oder Team.

Die oben genannten Werte sind Endpunkt-, Kontext- oder Laufzeit-Schutzgrenzen,
keine Kundenquoten. Für ein produktives Deployment müssen daher insbesondere
Docker-Volumes, PostgreSQL, `/repos` und die Ollama-Modellablage überwacht und
mit der Kundengröße dimensioniert werden. T5.2 ergänzt die noch offene Messung
für Referenzkorpus, Durchsatz, Peak-RAM, Graphgröße und Resolverzeit.

Die Konstante `MAX_KNOWLEDGE_SOURCES_PER_REPO = 2` existiert in
`backend/api/knowledge_sources.py`, die aktuell aufgerufene Funktion
`_check_knowledge_source_cap()` setzt diese Grenze jedoch noch nicht durch.
Sie darf deshalb bis zu einer separaten Implementierung nicht als zugesicherte
Nutzergrenze kommuniziert werden.

## Verantwortlichkeit im Betrieb

Vor produktiver Nutzung:

1. Speicher- und Backup-Überwachung für `data/postgres`, `repos` und
   `data/ollama` einrichten.
2. `OLLAMA_NUM_CTX`, Embedding-Nebenläufigkeit und Graph-Deckel nur nach einem
   Messlauf auf dem Zielhost ändern.
3. Bei kundenspezifischen Quoten einen vorgeschalteten Reverse Proxy,
   Container-/Volume-Limits oder eine separate Produktanforderung verwenden;
   solche Quoten sind derzeit nicht Bestandteil der Anwendung.
