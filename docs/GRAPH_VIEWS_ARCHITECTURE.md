# Graph View und Call Graph: fachlicher Schnitt und Skalierung

Stand: 23.09.2026

## Verantwortlichkeiten

| Ansicht | Nutzerfrage | Knoten | Beziehungen |
|---|---|---|---|
| Process View / Call Graph | „Wie hängt der Code technisch zusammen und was läuft als Nächstes?“ | Code-Entities | `CodeEdge` und synthetische Strukturkanten wie `CONTAINS` |
| Wissensgraph | „Welche Dateien, Systeme und Wissensquellen hängen zusammen – und warum?“ | Code-Dateien und quellenspezifische Wissensressourcen wie Confluence-Seiten, Jira-Issues oder Dokumente | Datei-zu-Datei-Projektionen aus `CodeEdge`, `EntityDocLink` und `KnowledgeLink` |

Der Wissensgraph zeigt keine Code-Entities als Knoten. Er fasst Parserobjekte
pro Quelldatei zusammen und projiziert gerichtete Beziehungen zwischen
verschiedenen Dateien. Kanten innerhalb derselben Datei und unaufgelöste Ziele
bleiben in der Process View bzw. im Call Graph, wo der konkrete Codepfad
sichtbar ist. Datei-Kanten nennen die Parserbeziehungen und repräsentative
Codeobjekte als Beleg.

Bei `EntityDocLink` zeigt die Richtung von der Wissensressource zur Code-Datei:
Die Seite oder das Dokument dokumentiert die Datei. Die Kante hält zusätzlich
fest, welches Codeobjekt die Beziehung begründet und wo die Dokumentpassage
liegt. Ressourcen werden je Quelle identifiziert; Confluence- und Notion-Seiten
nutzen ihre native Seiten-ID, andere Quellen ihre URL oder Quelldatei. Chunks
derselben Ressource erzeugen keine zusätzlichen Graphknoten.

## Richtungstaxonomie

Jede Kante verwendet genau eine der drei Richtungen:

| Richtung | Bedeutung | Darstellung |
|---|---|---|
| `directed` | Fluss von `source` nach `target` | Pfeil am Ziel |
| `undirected` | Verbindung ohne fachlichen Fluss | keine Pfeilspitze |
| `bidirectional` | Fluss in beide Richtungen | Pfeilspitzen an beiden Enden |

Dateiabhängigkeiten sind gerichtet. Ein `EntityDocLink` läuft von der
Dokumentationsressource zur Code-Datei. `KnowledgeLink`s speichern die Richtung explizit;
manuell angelegte Links starten ungerichtet, können im Dialog aber gerichtet
oder beidseitig gerichtet angelegt werden. Der Richtungsfilter blendet die drei
Kantengruppen unabhängig von Beziehungstyp und Knotentyp ein oder aus.

Die Auswahl „Upstream“, „Downstream“ oder „Beide Richtungen“ beim Laden einer
Fokusnachbarschaft ist davon getrennt: Sie begrenzt, welche gerichteten
Codeabhängigkeiten der API-Aufruf traversiert. Der Toolbar-Filter blendet
dagegen bereits geladene Kanten nach ihrer Beziehungsausrichtung aus.

## Gemessener Ausgangszustand

Am 21.09.2026 enthielt der lokale Bestand unter anderem:

| Projekt | Code-Entities | Code-Kanten | bestätigte Code-Doku-Links |
|---|---:|---:|---:|
| Apache Syncope 2.1.14 | 31.036 | 246.468 | 0 |
| JUnit Framework Import Test | 23.594 | 141.340 | 20 |
| AWS CardDemo | 10.400 | 6.987 | 0 |
| Apache Shiro | 9.412 | 46.766 | 0 |

Die frühere Graph API lud alle Entities, alle Code-Kanten und alle Dokumente und
kappte erst danach auf 2.000 Knoten. Für Syncope wurden dadurch mehr als 277.000
Codeobjekte und Kanten verarbeitet. Der Deckel schützte nur die Antwort und den
Browser, nicht Datenbank, Backend oder Serialisierung.

Auch der Call Graph braucht einen serverseitigen Kantenhaushalt: Der größte
gemessene Einzelknoten (`<clinit>` in Syncope) hat 2.510 ein- und ausgehende
Kanten. Die heutige BFS lädt die Treffermenge eines Hops vollständig und wendet
den 500-Knoten-Deckel erst beim Aufbau der Antwort an. Eine Folgeversion muss
deshalb bereits in SQL pro Richtung und Beziehungstyp begrenzen und die
Abschneidung in der Antwort ausweisen.

## Unmittelbare Entlastung

- `GET /graph` liest nur eine begrenzte Codekantenmenge und fasst Beziehungen
  pro Dateipaar als beschreibende `code_dependency`-Kante zusammen.
- `GET /graph/focus` und `/graph/neighborhood` fokussieren Code-Dateien und
  liefern Dateiabhängigkeiten, Dokumentationsbelege und Wissenslinks.
- Alle isolierten Entities und Dokumente werden nur noch beim expliziten
  Inventarmodus `include_isolated=true` geladen.
- Die interaktive Graph View bietet den Inventarmodus nicht mehr an. Der API-
  Parameter bleibt für Exporte und administrative Auswertungen erhalten.
- Dokumentationskanten liefern die konkrete Code- und Dokumentfundstelle mit.
- Die Graph View beendet das Neuzeichnen nach dem Layout. Der begrenzte Call
  Graph animiert die ausgehenden Kanten der ausgewählten Node und behält beim
  Öffnen einer Quelldatei seine Wurzel und sein bestehendes Layout.

## Zielbild für große Bestände

Eine Vollübersicht mit tausenden Einzelknoten ist kein brauchbarer Einstieg,
selbst wenn sie schnell übertragen wird. Die API soll deshalb eine serverseitig
begrenzte Exploration anbieten:

1. **Startansicht:** aggregierte Gruppen nach Dokumentquelle, Dokument und
   Codebereich mit Anzahl der enthaltenen Links. Pro Gruppe kommen nur wenige
   repräsentative Knoten zurück.
2. **Suchen und fokussieren:** Suche und Filter laufen im Backend. Ein Fokusaufruf
   liefert eine begrenzte Nachbarschaft mit `node_limit`, `edge_limit`, erlaubten
   Beziehungstypen und einem stabilen Cursor.
3. **Schrittweise erweitern:** Ein Klick lädt die nächste begrenzte Scheibe. Die
   Antwort enthält `has_more` und `next_cursor`; der Client führt nur IDs und
   Canvaszustand zusammen.
4. **Serverseitige Projektion:** Grad, Gruppierung, Filter, Priorisierung und
   Berechtigungen werden in SQL bzw. einem Backend-Service berechnet. Häufige
   Projektionen werden an eine Graphrevision gebunden und gecacht.
5. **Layout:** Für Übersichten liefert das Backend normalisierte, gecachte
   Koordinaten. Kleine Fokusgraphen dürfen weiterhin lokal nachjustiert werden.

Ein NDJSON- oder SSE-Strom kann Ladefortschritt und mehrere bereits begrenzte
Antwortseiten früh sichtbar machen. Er ersetzt die Begrenzung nicht: Das
fortlaufende Einspeisen eines Vollgraphen würde die Kräftesimulation bei jedem
Batch neu starten und die UI erneut überlasten.

## Empfohlene API-Form

```text
GET /graph/overview?project_id=…&group_by=source&limit=100
GET /graph/neighborhood?node_id=…&relationships=code_dependency,documented,manual&limit=150&cursor=…
GET /callgraph/focus?entity_id=…&direction=both&types=CALLS,PERFORM&hops=2&node_limit=300
```

Jede Graphantwort sollte `graph_revision`, `nodes`, `edges`, `has_more`,
`next_cursor` und die tatsächlich angewandten Filter enthalten. Ein Client darf
keinen impliziten Vollbestand anfordern.

## Reihenfolge

1. Fachlichen Schnitt und dauerhaftes Redraw ausrollen.
2. Dokumentfundstellen in der Graph View fachlich abnehmen.
3. Für den API-Inventarmodus eine eigene paginierte Liste anbieten.
4. Cursorbasierte Nachbarschaft und aggregierte Startansicht implementieren.
5. Mit festen großen Projekten Antwortzeit, Payload, Backend-RAM, UI-FPS und Zeit
   bis zur ersten nutzbaren Ansicht messen.
