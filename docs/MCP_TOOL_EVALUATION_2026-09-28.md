# Kapitel 4 – MCP-Tool-Test mit Codex CLI und GPT-6 Luna

## Versuchsaufbau

Am 28.09.2026 wurde ein einzelner read-only Lauf mit Codex CLI 0.158.0,
Modell `gpt-6-luna` und Reasoning `high` gegen das lokale CardDemo-Projekt
1247 ausgeführt. Der Codex-Lauf dauerte 58,3 Sekunden. Der MCP-Server war
verpflichtend konfiguriert; jede Sitzung war frisch und ephemeral. Ein
kurzlebiger Testtoken wurde nach dem Lauf widerrufen. Keine Quelldateien wurden
geändert. Der Lauf ist ein Tool-Smoke-Test mit n=1, kein Modellvergleich.

## Ergebnisse

| Tool | Aufruf und Ergebnis | Bewertung |
|---|---|---|
| `list_visible_projects` | CardDemo als Projekt 1247 gefunden. Anfrage mit Limit 100 wurde serverseitig auf 50 begrenzt. | Erfolgreich; das Limit-Clamping war in der Antwort sichtbar. |
| `search_code` | `COPAUA0C` als Programm-Entity 121997 und `MAIN-PARA` als Entity 122000 gefunden. Ergebnis war gekürzt. | Erfolgreich; lieferte brauchbare Entity-IDs und Pfad. |
| `research_project` | Exakter Treffer; Call-Flow-Einstieg `MAIN-PARA` eindeutig. Kanten zu `1000-INITIALIZE` und `2000-MAIN-PROCESS` aufgelöst; `9000-TERMINATE` blieb unresolved. | Erfolgreich und inhaltlich mit dem Quelltext vereinbar. |
| `get_code_entity` | Entity 121997 lieferte COPAUA0C und einen Quelltextauszug mit den `PERFORM`-Aufrufen. | Erfolgreich. |
| `get_call_flow` | Zwei Hops ergaben sieben Knoten und acht Kanten; darunter Initialisierung, Nachrichtenextraktion und Autorisierung. `9000-TERMINATE` blieb unresolved. | Erfolgreich; zentrale Kanten stimmen mit dem Checkout überein. |
| `get_graph_neighbors` | Erstaufruf mit `relationship="PERFORM"` scheiterte mit `invalid relationship`. Retry mit Standardfilter `code_dependency` gelang formal, lieferte aber nur einen Dateiknoten, keine Kanten und `analysis_status=partial` mit Parserfehlern. | Filterfehler war vermeidbar; die Graphdaten für diesen COBOL-Fokus blieben unvollständig. |
| `search_knowledge` | Embedding-Endpunkt antwortete HTTP 404; kein Retry. | Nicht nutzbar, bis die Embedding-URL/-Route korrigiert ist. |

Damit wurden alle sieben verschiedenen Tools aufgerufen. Sechs lieferten
mindestens eine erfolgreiche MCP-Antwort; die Wissenssuche nicht. Insgesamt
gab es acht Toolaufrufe: sechs erfolgreich und zwei mit Toolfehler (ungültiger
Graphfilter und Embedding-404). Der lokale Quelltext bestätigte die berichteten
`PERFORM`-Aufrufe in `COPAUA0C.cbl`; die ungelöste Kante zu `9000-TERMINATE`
bleibt ein Indexbefund und widerspricht der vorhandenen Quelltextreferenz.

## MCP-Fix

Der Erstaufruf zeigte, dass `get_graph_neighbors` den Filter als beliebigen
String veröffentlichte und zulässige Werte nicht im Toolschema einschränkte.
Der Parameter ist jetzt als Literal-Enum `code_dependency`, `documented` oder
`manual` typisiert; die Toolbeschreibung stellt klar, dass Call-Graph-Typen
wie `PERFORM` keine Filterwerte sind. Das registrierte Schema wurde lokal
ausgelesen und enthält das Enum. Der Live-Lauf fand vor diesem Quellfix statt;
der laufende Dienst wurde für diese Prüfung nicht neu gebaut oder gestartet.

Die MCP-Server-Pytestdatei ließ sich nicht ausführen: nach Setzen der
Konfiguration scheiterte die Verbindung zur lokalen PostgreSQL-Datenbank an
der Authentifizierung. Der Schema-Check benötigt keine Datenbank und
bestätigte die Enum-Ausgabe. Der Embedding-404 und die partielle COBOL-Analyse
sind separate Daten-/Konfigurationsbefunde und wurden durch den Schema-Fix
nicht verändert.
