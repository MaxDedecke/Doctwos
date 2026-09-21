# Graph View und Call Graph: fachlicher Schnitt und Skalierung

Stand: 21.09.2026

## Verantwortlichkeiten

| Ansicht | Nutzerfrage | Knoten | Beziehungen |
|---|---|---|---|
| Call Graph | „Wie hängt der Code technisch zusammen?“ | ausschließlich Code-Entities | `CodeEdge` und synthetische Strukturkanten wie `CONTAINS` |
| Graph View | „Welche Elemente hängen zusammen und wo sind sie dokumentiert?“ | Code-Entities und Dokumente | typneutral zusammengefasste `CodeEdge`s, `EntityDocLink` und `KnowledgeLink` |

Codeabhängigkeiten bleiben in der Graph View sichtbar, werden dort aber bewusst
zu einer ungerichteten Beziehung `code_dependency` zusammengefasst. Mehrere
Aufrufe, Vererbungs- oder Datenzugriffskanten zwischen demselben Elementpaar
erscheinen als eine Kante. Die exakten Typen, Richtungen und Aufrufpfade bleiben
Aufgabe des Call Graph.

Bei `EntityDocLink` ist der Dokumentknoten das Dokument und die Kante trägt die
konkrete Belegstelle: Chunk, Datei, Quelle, Zeilenbereich, Seite, Abschnitt und
URL-Anker, soweit die Quelle diese Daten liefert. So bleibt sichtbar, an welcher
Stelle ein Codeelement dokumentiert wird, ohne das Dokument für jeden Chunk als
eigenen Knoten zu vervielfachen.

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

- `GET /graph` liest nur eine begrenzte Codekantenmenge und fasst technische
  Kantentypen pro Elementpaar als `code_dependency` zusammen.
- `GET /graph/focus` liefert bis zu 500 direkte, ebenfalls typneutral
  zusammengefasste Codeabhängigkeiten sowie die Wissenslinks der Entity.
- Alle isolierten Entities und Dokumente werden nur noch beim expliziten
  Inventarmodus `include_isolated=true` geladen.
- Die interaktive Graph View bietet den Inventarmodus nicht mehr an. Der API-
  Parameter bleibt für Exporte und administrative Auswertungen erhalten.
- Dokumentationskanten liefern die konkrete Fundstelle mit.
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
