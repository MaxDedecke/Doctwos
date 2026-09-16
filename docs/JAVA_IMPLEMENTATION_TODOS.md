# Java-Unterstützung: Entwickler-Todos

Arbeitsliste zum Umsetzungsplan unter `/root/DOCTUS_JAVA_UNTERSTUETZUNGSPLAN.md`.
Die Paketgrenzen folgen der empfohlenen Lieferreihenfolge; jedes Paket hat ein
prüfbares Abnahmekriterium und soll bestehende COBOL-Ergebnisse erhalten.

## Paket 1 – Sprachneutraler Vertrag und Persistenz

- [x] **T1.1 Entity-Vertrag:** Entity- und Kanten-Typen als offene Strings
  modellieren; `parent_qualified_name` ergänzen und vom COBOL-Parser explizit
  befüllen. Golden-Ausgaben für COBOL unverändert halten und Parent-QNames
  separat testen.
- [x] **T1.2 Datei-Wurzel:** `/entities/resolve` über `meta.is_file_root`
  auflösen; für bereits persistierte COBOL-Dateien vorübergehend auf die
  bisherigen `program`-/`copybook`-Typen zurückfallen.
- [x] **T1.3 Registry:** `ParserEntry` und `STRUCTURE_PARSERS` nach
  `parser/core/registry.py` verschieben; `prepared_source`, explizite Root-Typen
  und parserabhängige Version/Fingerprint-Hooks einführen. COBOL-Aufrufer und
  Tests kontrolliert migrieren.
- [x] **T1.4 Eltern-Persistenz:** `_parent_id` anhand des expliziten Parent-QName
  bestimmen; alten Punkt-Split nur als Kompatibilitäts-Fallback für Ergebnisse
  ohne Parent-QName behalten. Parent-Scope- und Reparse-Tests ergänzen.
- [x] **T1.5 COBOL-Gate:** Parser-Golden-Files, Persistenz-/Connector-Tests und
  Backend-Entity-Tests ausführen; COBOL-Golden-Dateien dürfen sich nicht ändern.
  **Abgeschlossen 15.09.2026:** vollständige Parser-Suite 365/365 grün,
  Backend-Root-Tests 4/4 grün; COBOL-Golden-Files unverändert. Zwei veraltete
  Git-Connector-Testannahmen wurden aktualisiert: `force_reindex` analysiert
  alle Dateien erneut, übernimmt aber unveränderte Embeddings (O-122); die
  Skip-Meldung für UTF-8-Dateien mit zu vielen Steuerzeichen entspricht jetzt
  der aktuellen Diagnose. Kein Produktcode geändert.

## Paket 2 – Java-Deklarationen und Chunks

- [x] **T2.1 Grammatik-Freigabe:** **Abgeschlossen 15.09.2026.** Als Basis ist
  `antlr/grammars-v4/java/java` am Commit
  `20efa537586610f5aebd584429ac1b5993a30381` gepinnt. `JavaLexer.g4` und
  `JavaParser.g4` enthalten jeweils den BSD-3-Clause-Lizenztext; Herkunft,
  Sprachstand und Generierungsverfahren sind unter
  `parser/java/grammar/README.md` dokumentiert. Das Upstream-README nennt Java
  24 als getesteten Stand; Java-21-Feature-Abdeckung wird trotzdem im eigenen
  Golden-Korpus geprüft. Upstream liefert nur Java-/C#-Basisklassen. Die
  Python-Bridge und ihre beiden semantischen Prädikate werden Doctus-eigen
  implementiert, ohne die fremde Java-Basisklasse zu übernehmen.
- [x] **T2.2 Parser-Bridge:** **Abgeschlossen 15.09.2026.** ANTLR-4.13.2-
  Python-Lexer, Parser und Visitor sind generiert und eingecheckt; die eigene
  Basisklasse implementiert beide Grammatik-Prädikate. Die Bridge normalisiert
  CRLF/CR, mappt Diagnosen auf Originalzeilen, begrenzt sie und behält bei
  Syntaxfehlern den reparierten Teilbaum. Python 3.12.3 und die festgelegte
  ANTLR-Runtime 4.13.2 sind getestet. Regenerierung: `parser/java/generate_parser.sh`.
- [x] **T2.3 Declaration Visitor:** **Abgeschlossen 15.09.2026.** Das gemeinsame
  `ParseResult` enthält Datei-Wurzel, Package/Modul, Top-Level- und geschachtelte
  Typen (Klasse, Interface, Enum, Record, Annotation Type), Methoden,
  Konstruktoren, Felder/Enum-Konstanten und Initializer. QNames und Parent-QNames
  sind explizit; Signaturen, Modifier, Sichtbarkeit, Annotationen und Quellzeilen
  werden als Metadaten geliefert. `@Getter`, `@Setter` und `@Data` erzeugen
  belegte Accessor-Entities, sofern keine gleichnamige Methode existiert.
  Ausführbare Bodies werden nicht als lokale Deklarationsräume traversiert.
  Java-Bridge-Tests: 14/14.
- [x] **T2.4 Chunking und Git:** **Abgeschlossen 15.09.2026.** Methoden,
  Konstruktoren, Initializer und Feldgruppen erzeugen Symbol-Chunks; übriger
  Quelltext bleibt als Kontext, nicht parsebare Dateien bekommen markierte
  Fallback-Chunks. `.java` ist standardmäßig aus und kann pro Quelle über
  `language_extensions` oder workerweit `DOCTUS_LANGUAGE_EXTENSIONS` aktiviert
  werden. `target/`, `build/`, `.gradle/`, `bin/`, `out/`, `.idea/` und
  `.settings/` werden dann ausgeschlossen. Maven-/Gradle-Quellpfade liefern
  `meta.module`. Git-Integrationstest: 1/1.
- [x] **T2.5 Golden-Korpus:** **Abgeschlossen 15.09.2026.** Sieben Fixtures
  decken Java-8-Generics/Overloads, Java-21-Records/Pattern-Switch, Lombok,
  Modul-/Package-Deskriptoren, Modulpfade und beschädigte Syntax ab. JSON-
  Golden-Files und `parser/tests/update_java_goldens.py` sind vorhanden;
  Bridge-, Golden- und Registry-Tests zusammen: 19/19.

## Paket 3 – Beziehungen und Auflösung

- [x] **T3.1 Kantenextraktion:** **Abgeschlossen 16.09.2026.** Ein eigener
  ANTLR-Beziehungspass erfasst `IMPORTS`, `EXTENDS`, `IMPLEMENTS`,
  `USES_TYPE`, `CALLS`, `INSTANTIATES`, `READS` und `WRITES` mit physischen
  Quellzeilen, Besitzer-/Aufrufmetadaten und sichtbarer Originalschreibweise.
  Die Kanten bleiben bis zur lokalen bzw. globalen Auflösung bewusst
  `unresolved`; Tests decken Wildcard-/statische Imports, Generics,
  Konstruktoren, verschachtelte Aufrufe, Überladungen und Feldzugriffe ab.
- [x] **T3.2 Lokale Auflösung:** **Abgeschlossen 16.09.2026.** Eindeutige
  Typen, Felder, Methoden und Konstruktoren derselben Datei werden über
  Parent-/Owner-Kontext aufgelöst. Methoden- und Konstruktorüberladungen
  werden zuerst über Argumentanzahl und dann über sicher erkennbare
  normalisierte Literaltypen unterschieden; unklare oder mehrdeutige Ziele
  bleiben `unresolved` und erhalten einen Auflösungsgrund.
- [x] **T3.3 Globaler Resolver:** **Abgeschlossen 16.09.2026.** Der DB-freie
  Java-Resolver verarbeitet mehrere `ParseResult`s und berücksichtigt
  vollständige QNames, aktuelles Package, explizite und statische Imports,
  `java.lang`, Besitzer-Typen sowie normalisierte Argumenttypen. Wildcard-
  Imports werden nur bei genau einem Treffer verwendet; fehlende externe und
  mehrdeutige Ziele bleiben `unresolved` und erhalten einen Auflösungsgrund.
- [x] **T3.4 Persistenzintegration:** **Abgeschlossen 16.09.2026.** Die
  sprachneutrale Persistenz akzeptiert Java-QNames als Quellen und Ziele,
  behandelt geteilte Package-Entities über mehrere Dateien stabil und erhält
  eingehende Kanten beim Reparse. Der DB-Nachlauf adaptiert persistierte Java-
  Entities/Kanten wieder auf den bestehenden globalen Resolver, sodass auch
  unveränderte, per Resume übersprungene Zieldateien an Mehrdatei-Auflösung
  teilnehmen. Mehrdeutige Wildcard-Treffer bleiben mit
  `resolution_reason="ambiguous_type"` unresolved. Ende-zu-Ende-Tests decken
  Mehrdatei-Auflösung, Mehrdeutigkeit, Reparse/ID-Erhalt und Resume ohne neues
  Embedding ab.

## Paket 4 – API, Views und Chat

- [ ] **T4.1 API/Graph:** Beliebige Entity-/Kantentypen transportieren;
  Call-Graph-Filter für Aufrufe und optional Vererbung ergänzen.
- [ ] **T4.2 Gemeinsame Taxonomie:** Typnamen, Farben, Icons und Fallbacks für
  Entities und Kanten zentralisieren; keine separaten Java-Views bauen.
- [ ] **T4.3 Navigation:** Editor, Suche, Wissensgraph, Link-Manager,
  Referenzansicht und Nachbarschaften mit Java-Entities durchtesten.
- [ ] **T4.4 Chat/Retrieval:** Generischen Entity-Fokus und Breadcrumbs
  übertragen; relevante Java-Nachbarn im Tokenbudget ergänzen.

## Paket 5 – Härtung und Release

- [ ] **T5.1 Integrationssuite:** Mehrdatei-Java-Repo, gemischtes COBOL/Java,
  Löschungen, abgebrochener Sync und Resume Ende-zu-Ende prüfen.
- [ ] **T5.2 Performance:** Parse-Durchsatz, Peak-RAM, Graphgröße und Resolverzeit
  auf Referenzkorpus messen und Grenzfälle absichern.
- [ ] **T5.3 OSS/Betrieb:** Lizenz-Clearing, Offline-Regenerierung, Runtime-Image
  und Nutzergrenzen dokumentieren.
- [ ] **T5.4 Release-Gates:** Parser-Golden, Backend, Frontend, Lint, Lizenz,
  Docker-Build und Offline-Bundle gemeinsam grün nachweisen.

## Fortschritt

- **Abgeschlossen:** T1.1 bis T1.5, T2.1 bis T2.5 und T3.1 bis T3.4.
- **Aktiv:** Paket 4 beginnt mit T4.1 (API/Graph).
- **Nächstes konkretes TODO:** Generische Entity-/Kantentypen durch API und
  Graph transportieren und Call-Graph-Filter für Java ergänzen.
- **Noch nicht begonnen:** T4.2 bis T5.4.
