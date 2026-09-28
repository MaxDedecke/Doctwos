# MCP: Parser- und Indexabdeckung am 28.09.2026

Geprüft: Benchmark-Projekte Apache Syncope (1246) und CardDemo (1247), laufender
PostgreSQL-Index, Originalchunks über das ORM und aktueller Parser-/MCP-Code.
Keine vollständige Abnahme aller Sprachen oder Dateien. Keine Änderungen an
Index, Containern oder Produktcode. Nur ein neuer COBOL-In-Memory-Parse zur
Unterscheidung zwischen aktuellem Parserfehler und veraltetem Index.

## Ergebnis

Die Informationen reichen noch nicht vollständig aus. Es gibt sowohl echte
Parser-/Indexlücken als auch Informationen, die bereits im Originaltext oder in
Metadaten vorhanden sind, aber nicht passend gesucht oder ausgegeben werden.

| Bedarf | Beobachteter Stand | Ticket |
|---|---|---|
| COBOL-Detailbefüllung und IMS-Schreiben | Originaldatei 1026 Zeilen, 67 Indexchunks nur bis 825. Neuer Parse bestätigt dieselbe Grenze und fehlende Folgeparagraphen. | O-305, O-359 |
| Lesen/Schreiben von PA-TRANSACTION-AMT | Entity 119377 vorhanden, Verwendung bei 821 nur USES; keine von trace_data_access erfasste READS/WRITES-Kante für diese Verwendung. Zuweisung bei 885 außerhalb der Chunkabdeckung. | O-353, O-359 |
| Laufzeitbedingungen und Datenfluss | Feld-XREF sowie Aufrufkanten vorhanden; keine damit nachgewiesene pfadsensitive Zuweisungs-/Verwendungskette. Vorverarbeitungsbedingungen sind keine Laufzeitbedingungen. | O-353 |
| Java-Methoden finden | PullJobDelegate-Methode existiert als Entity 141032 mit # im Qualified Name; Punktnotation liefert im Benchmark leere Suche. | O-355 |
| Java-Transaktionsdeklaration | Manager-Entity 137090 speichert annotations=[Transactional, Override]. Originalchunk 88–108 enthält REQUIRES_NEW, strukturierte Annotationswerte fehlen. | O-357 |
| Java-Aufrufargumente/Nachbearbeitung | doCreate-Entity 111199 hat Kanten zu provisioningManager.create, binder.getUserTO und afterCreate. Argumentanzahl/teilweise Typen vorhanden, konkrete Ausdrücke nicht in CALLS-Metadaten. Originaltext der Nachbearbeitung liegt im Chunk 193–196. | O-351, O-357 |
| Vollständige Methodenbelege | _definition nimmt nur ersten überlappenden Chunk: Pull 213–239 statt vollständigem Bereich 213–395. Weitere Kürzung im MCP auf 1600 Zeichen. | O-351 |
| Verkettete Java-Receiver | getResource aufgelöst, getResource().getPullPolicy weiterhin unresolved im Live-Index. Ursache Resolver vs. alter Index noch offen. | O-352 |
| Lokale EXEC-Verknüpfung | REPL-Entity 122174 und exakter Zielname existieren; EXECUTES-Kante dennoch unresolved ohne Ziel-ID. | O-306 |

## Reproduktion des wichtigsten Parserbefunds

Datei: `repos/wt/ks_4917/app/app-authorization-ims-db2-mq/cbl/COPAUA0C.cbl`.
Aufruf: `cobol.parse.parse_program(text, path)` mit aktuellem lokalem Parser,
ohne Copybook-Index, ohne Persistenz. Der live gespeicherte Index einschließlich
Copybook-Auflösung zeigt dieselbe Paragraphen-/Chunkgrenze.

- Physische Quellzeilen: 1026; Programm-Entity im Index: 22–1025.
- Letzter Paragraph: `8400-UPDATE-SUMMARY`, 798–825.
- Chunks: 67; maximaler Endwert: 825.
- Parserdiagnosen: Fehler bei 307, 334, 344 und 829; letzter Fehler:
  `mismatched input 'ELSE' expecting <EOF>`.
- `MOVE PA-RQ-TRANSACTION-AMT TO PA-TRANSACTION-AMT` steht bei 885.
- Das Detail-ISRT steht bei 913–919; als separate EXEC-Struktur sind spätere
  Operationen teilweise erfasst, als Originalchunk und Paragraphenstruktur fehlen sie.

Die Diagnose lokalisiert den Verlust, belegt aber noch nicht den exakten
Grammatik-/Recovery-Fix. Fehlende Chunks sind kein Beweis, dass der Quellcode
nicht existiert oder die Laufzeit keinen entsprechenden Zugriff ausführt.

## Relevante Implementierungen

- `parser/cobol/divisions.py`: Paragraphen aus dem ANTLR-Tree.
- `parser/cobol/chunking.py`: Chunkbildung anhand dieser Paragraphenbereiche.
- `parser/cobol/xref.py`: allgemeine USES-Referenzen ohne Verb-/Operandenrichtung.
- `parser/cobol/parse.py`: Herkunfts-/Vorverarbeitungsbedingungen an Kanten.
- `parser/java/declarations.py`: Annotationsnamen, Signaturen und Rückgabetypen.
- `parser/java/relationships.py`: CALLS mit argument_count und argument_types.
- `backend/api/entities.py::_definition`: erster überlappender Chunk.
- `backend/mcp_server.py`: Suche, Zeichenkürzung und READS/WRITES-Filter.

Empfohlene Reihenfolge: verlorene COBOL-Quellabdeckung wiederherstellen,
vorhandene Java-/Quellinformationen vollständig erreichbar machen, anschließend
gezielt die fehlende strukturierte Datenfluss- und Annotationsinformation ergänzen.
