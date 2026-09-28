# Java-Analyseprüfung vom 28.09.2026

Geprüft: `parser/java/parse.py`, DeclarationVisitor, RelationshipVisitor,
lokale/globale Resolver, Chunking, MCP-Quelle und lesend der Syncope-Index
(Projekt 1246). Kleine Java-Beispiele wurden nur im Speicher mit
`parse_java_file` ausgewertet. Kein Import, kein Reindex, keine Produktcodeänderung.
Die Prüfung erfasst wesentliche statische Lücken, ist keine vollständige
Java-Sprachkonformitätsprüfung.

| Bereich | Ergebnis | TODO |
|---|---|---|
| Lambda-Body | `() -> helper()` erzeugt Lambda-Entity, aber CALLS-Kante von `outer()` auf helper statt vom Lambda-Body. | O-365 |
| Anonyme Klasse | Aufruf in `run()` wird `outer()` zugeschrieben. `this.helper()` bindet im Negativfall an `demo.A#helper()` statt an die gleichnamige Methode der anonymen Klasse. | O-365 |
| Lokale Variablen | Zwei zulässige Variablen `first` in verschiedenen Blöcken, zwei `first.work()`-Verwendungen: beide unresolved, obwohl je eine sichtbare Deklaration eindeutig ist. | O-366 |
| Methodenreferenz | `this::helper` ergibt Entity, keine Zielkante. | O-367 |
| Fremdes Feld | `b.value=1; int x=b.value;` plus `B.value` ergibt unresolved READS/WRITES auf `b.value`. | O-368 |
| Ausnahmen | `throws`, `catch`, `finally` sind syntaktisch erkannt, aber Method-Entity und CALLS-Kanten tragen keinen Ausnahme-/Abschlusskontext. | O-369 |
| Annotationen | `@Flag("critical")` erzeugt nur den Namen `Flag`; Werte fehlen. | O-357 |
| Ketten | `getB().work()` wird im einfachen Fall korrekt aufgelöst; mehrstufiger Syncope-Fall bleibt offen. | O-352 |

Die In-Memory-Proben waren syntaktisch gültig und lieferten keine
Parserdiagnosen. Einfache lokale Feldlese-/Schreibkanten funktionieren. Die
lokale einfache Rückgabetypkette funktioniert ebenfalls. Das trennt fehlende
Features von bereits implementierten Fällen.

Codeursachen: `JavaRelationshipVisitor` hat keine Scope-Wechsel für Lambda und
anonyme Klasse, aber DeclarationVisitor erzeugt ihre Entities;
`_receiver_declaration` kennt Methodennamen und Variablennamen, keine
lexikalischen Blöcke/Verwendungspositionen; `visitMethodReferenceExpression`
erzeugt nur eine Entity; `resolve_global_edges` überspringt READS/WRITES;
Methodenmetadaten erfassen keinen Throws- oder Annotationswert. Weitere
Quelldetails stehen in `parser/java/relationships.py`,
`parser/java/declarations.py` und `parser/java/resolution.py`.

Bestandsabgleich: Projekt 1246 enthält 1.999 Lambda-, 1.050
Anonymous-Class- und 409 Method-Reference-Entities; keine dieser Entitytypen
hat eine ausgehende CodeEdge. Das belegt die fehlende Graphprojektion im
bestehenden Index, aber nicht die Häufigkeit konkreter falscher Antworten.
Die gespeicherten Java-Kanten sind auch von Indexrevision und Buildvarianten
abhängig; Änderungen erfordern kontrollierten Reindex und neue Negativfälle.

Reproduktion: `PYTHONPATH=parser .venv/bin/python`
`docs/evidence/java_analysis_2026-09-28/probe.py`. Das Skript nutzt nur
`parse_java_file` und `resolve_global_edges`; seine Ausgabe ist unter
`docs/evidence/java_analysis_2026-09-28/results.txt` archiviert.
