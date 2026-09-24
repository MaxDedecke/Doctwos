# Sicherheitsprüfung der eingehenden MCP-Schnittstelle

Stand: 24.09.2026. Geprüfter Ausgangs-Checkout: `aaf524d` einschließlich der
vorhandenen lokalen IDE-Änderungen. Das Review fand zwei Befunde, darunter eine
bestätigte Verletzung der Projektisolation. Beide Befunde wurden im aktuellen
Arbeitsstand behoben und durch Regressionen erneut geprüft.

## Umfang und Nachweis

Quelltextprüfung von MCP-Transport, sechs Tools, Tokenverwaltung, Projekt- und
Quellenberechtigungen sowie der verwendeten Retrieval-/Call-Flow-Funktionen.
Zusätzlich 27 begrenzte Prüfungen: 27 erwartete Schutz-/Funktionsresultate nach
der Behebung. Die ursprüngliche Reproduktion der beiden Befunde lief per
HTTPX-ASGI-Transport durch
den echten `/mcp`-Handler und das installierte MCP-SDK, mit echten PostgreSQL-
Abfragen auf temporären Tabellen.

Alle Nutzer, Tokens, Projekte, Quellen und Inhalte waren künstlich. Die Tabellen
überschatteten die produktiven Tabellen ausschließlich auf der Testverbindung;
die äußere Transaktion wurde vollständig zurückgerollt. IDs waren explizit
gesetzt, sodass keine produktiven Sequenzen verwendet wurden. Der externe
Embedding-Aufruf wurde durch einen festen Testvektor ersetzt; Profilauflösung
und Auditpersistenz wurden für die isolierte Prüfung ersetzt. Keine realen
fremden Dokumentinhalte wurden abgefragt und kein Lastangriff durchgeführt.

Reproduktion aus dem Repository-Root:

```sh
.venv/bin/python scripts/reproduce_mcp_security_review.py
```

Das Skript benötigt die lokale PostgreSQL-Instanz und die vorhandene `.env`.
Es prüft, dass die zuvor beobachteten Datenlecks und die unbegrenzte
Call-Flow-Abfrage nicht mehr auftreten.

## SEC-MCP-01 — Hoch: fremde Projektinhalte in der Wissenssuche (behoben)

**Fundstellen:** `backend/services/ollama_client.py:166–188`,
`backend/mcp_server.py:78–80` und `backend/mcp_server.py:383–402`.

`search_project_chunks` sammelt Projekt-/Quellenfilter sowie Modell- und
Dimensionsbedingungen in einer Liste und verbindet anschließend alles mit
`OR`. Damit genügte etwa die passende Embedding-Dimension, um einen Ausschnitt
aus einem anderen Projekt in die Kandidatenmenge aufzunehmen.

Der MCP-Wrapper prüft danach die Quellenberechtigung, aber nicht die tatsächliche
Projektzugehörigkeit jedes Chunks. Für `source_id=None` gilt die Quellenprüfung
pauschal als bestanden. Solche Datensätze sind im Datenmodell vorgesehen. Zudem
schreibt die Antwort die angefragte Projekt-ID statt der tatsächlichen
Chunk-Projekt-ID in das Ergebnis und verschleiert damit die falsche Zuordnung.

**Ursprünglich reproduziert:** Ein regulärer Nutzer war ausschließlich Mitglied von Projekt
`-8401` und Team `-8201`. Ein künstlicher Ausschnitt gehört zu Projekt `-8402`
in einem anderen Team, hat keine Quellen-ID und enthält
`SYNTHETIC_FOREIGN_SOURCELESS`. Ein authentifizierter Aufruf von
`search_knowledge(project_id=-8401, query="synthetic", limit=8)` liefert diesen
Text, dessen Dateipfad und Chunk-ID; die Antwort behauptet `project_id=-8401`.
Ein fremder Chunk mit einer nicht sichtbaren Quelle wird dagegen ausgefiltert.
Der direkte Aufruf mit der fremden Projekt-ID wird korrekt verweigert.

**Ursprüngliche Voraussetzungen:** gültiges Token eines normalen Nutzers mit mindestens einem
sichtbaren Projekt, funktionierender Embedding-Aufruf und passende fremde
Kandidaten ohne Quellen-ID. Kein fremdes Token und keine Kenntnis der fremden
Projekt-ID nötig. Der zuletzt beobachtete Embedding-HTTP-Fehler ist keine
Sicherheitsmaßnahme; nach Wiederherstellung des Providers bleibt der Fehler
in der Autorisierung bestehen.

**Behebung:** Die Abfrage gruppiert die Projektbedingung und verbindet sie mit
Modell und Vektordimension per `AND`. Projektgebundene Quellen-Chunks ohne
`project_id` bleiben als Altbestand unterstützt. Vor der MCP-Antwort wird
außerdem Projekt-ID und Quellenbesitz für jeden Treffer erneut geprüft;
quellenlose Chunks benötigen eine direkte Zuordnung zum angefragten Projekt.
Regression `test_search_knowledge_retrieval_is_scoped_before_ranking` prüft
gleichzeitig, dass so ein zulässiger Altbestand weiter geliefert wird und ein
ähnlicher quellenloser Chunk aus einem anderen Projekt ausgeschlossen bleibt.
`test_search_knowledge_rechecks_scope_on_retriever_results` prüft die zusätzliche
Ausgabekontrolle mit einem absichtlich fehlerhaften Retriever-Ergebnis.

## SEC-MCP-02 — Mittel: Call-Flow-Abfragearbeit (behoben)

**Fundstellen:** `backend/services/call_flow.py:168–176`,
`backend/mcp_server.py:get_call_flow`. Das installierte SDK führt synchrone
Tool-Funktionen unmittelbar aus (`mcp/server/fastmcp/utilities/func_metadata.py`).

Die Traversierung lädt pro Schritt sämtliche passenden Kanten mit `.all()`
ohne SQL-Limit. Das Knotenlimit begrenzt diese Kantenmenge nicht; anschließend
werden sämtliche geladenen Kanten verarbeitet und ein Mermaid-Text aufgebaut.
Erst im MCP-Wrapper wird auf 120 Ausgabekanten gekürzt. Die synchronen DB- und
Verarbeitungsschritte können dabei den Event-Loop des Backend-Workers blockieren.

**Ursprünglich reproduziert:** 180 künstliche Aufrufkanten an einer erlaubten Entity, ein
MCP-Aufruf mit nur einem Hop. Die aufgezeichnete Kantenabfrage enthält kein
`LIMIT`; die Antwort enthält dennoch nur 120 Kanten. Die unbeschränkte
Materialisierung ist nachgewiesen. Ein tatsächlicher Dienstausfall wurde nicht
provoziert oder gemessen.

**Voraussetzungen:** gültiges Token und Zugriff auf einen Bestand mit hoher
Kantenzahl. Im geprüften MCP-Pfad ist kein Rate-Limit erkennbar; vorgeschaltete
Infrastruktur wurde nicht auf solche Limits geprüft.

**Behebung:** `CALL_FLOW_MAX_EDGES=500` begrenzt die Abfrage über alle Hops.
Die Datenbank lädt höchstens das verbleibende Budget plus einen zusätzlichen
Datensatz, um Kürzung zuverlässig zu markieren. Bereits geladene Kanten werden
bei folgenden Hops ausgeschlossen. Regression
`test_call_flow_bounds_edges_before_returning_them` prüft Budget und
Kürzungsstatus. Der Call-Flow liefert weiterhin Mermaid für bestehende Nutzer;
hohe Fan-outs haben nun eine harte Obergrenze. Ein separates Rate-Limit und die
Auslagerung synchroner DB-Arbeit sind mögliche weitere Härtungen, waren aber
nicht Teil der reproduzierten Lücke.

## Erfolgreich geprüfte Schutzmechanismen

- Fehlendes, unbekanntes, widerrufenes oder abgelaufenes Token: HTTP 401.
- Token eines deaktivierten Nutzers und doppelte Authorization-Header: HTTP 401.
- Widerruf eines zuvor gültigen Tokens: nächster Request erhält HTTP 401.
- Fremden Host abgewiesen (421), fremden Origin abgewiesen (403).
- Request größer als 256 KiB abgewiesen (413); fehlerhaftes JSON abgewiesen (400).
- Projektliste zeigt nur das zugängliche Projekt.
- Direkte fremde Projekt-/Entity-Zugriffe bei allen fünf projektspezifischen
  Tools verweigert; abgewiesene Wissenssuche ruft den Embedder nicht auf.
- Eigenes Codeobjekt lesbar; überlange Suchanfrage verworfen; eine SQL-
  Injektions-Testzeichenfolge erzeugt keine Treffer.
- Fremde quellengebundene Chunks werden im MCP-Ergebnis unterdrückt.
- Widerruf eines Tokens eines anderen Nutzers verweigert (404).
- Tool-Liste enthält die sechs vorgesehenen lesenden Tools.

Statische Prüfung: Tokens bestehen aus kryptographischem Zufall und werden
als SHA-256-Hash gespeichert; Listen zeigen keinen vollständigen Tokenwert.
MCP-Tool-Auditargumente enthalten keine Suchtexte oder Antwortinhalte.

## SDK-Abgleich und Grenzen

Installiert: `mcp==1.29.0`, `fastapi==0.139.2`, `starlette==1.3.1`.
Die auf der offiziellen SDK-Seite aufgeführten sechs Advisories betreffen
ältere MCP-Versionen; die dort jeweils angegebenen Fixversionen liegen unter
1.29.0. Geprüfte Primärquellen:

- [HTTP-Session-Zuordnung: Fix 1.27.2](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-jpw9-pfvf-9f58)
- [Experimentelle Tasks: Fix 1.27.2](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-hvrp-rf83-w775)
- [WebSocket-Host/Origin: Fix 1.28.1](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-vj7q-gjh5-988w)
- [DNS-Rebinding: Fix 1.23.0](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-9h52-p55h-vw2f)
- [Validierungsfehler: Fix 1.9.4](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-3qhf-m339-9g5v)
- [Streamable-HTTP-Fehler: Fix 1.10.0](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-j975-95f5-7wqh)

Dies ist kein vollständiger Scan sämtlicher transitiver Abhängigkeiten. Die
Prüfung betrifft den Checkout und dessen ASGI-Handler, nicht die gesamte
ausgelieferte Netzwerkstrecke einschließlich TLS, Proxy und Firewall. Ebenso
keine End-to-End-Prüfung von Prompt-Injection im angebundenen Agenten. Inhalte
aus Tools bleiben für diesen Agenten unvertrauenswürdige Quelldaten.

Gezielte Regressionen nach der Behebung: `tests/test_mcp_server.py` — 9 passed.
Der isolierte ASGI-/PostgreSQL-Reproduktionslauf meldete alle 27 Prüfungen als
PASS. Der laufende Dienst wurde bei der Fehlerbehebung nicht ausgerollt.
