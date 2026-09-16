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
  Fallback-Chunks. Programmiersprachen werden standardmäßig anhand ihrer
  Dateiendung erkannt; `.java` benötigt kein Opt-in mehr. Die vorhandenen
  `language_extensions` bzw. `DOCTUS_LANGUAGE_EXTENSIONS` bleiben für
  kundenspezifische Endungen oder bewusste Overrides verfügbar. `target/`,
  `build/`, `.gradle/`, `bin/`, `out/`, `.idea/` und
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

- [x] **T4.1 API/Graph:** **Abgeschlossen 16.09.2026.** Entity- und Kanten-
  Typen bleiben in API und Frontend offene Strings. Der Wissensgraph liefert
  jetzt persistierte `CodeEdge`s inklusive Typ, Auflösung, Metadaten und
  Quellzeilen; das gilt für Übersicht, Fokus und Exporte. Der Call-Graph
  unterstützt COBOL-Aufrufkanten sowie Java-`CALLS`/`INSTANTIATES`, explizite
  freie Typfilter (wiederholt oder kommasepariert) und eine optionale
  `EXTENDS`/`IMPLEMENTS`-Erweiterung. Die View übernimmt Typen dynamisch,
  färbt unbekannte Typen deterministisch und bietet den Vererbungs-Schalter.
  Regressionen decken Java-Typen, Filter, Vererbung und Graph-Transport ab.
- [x] **T4.2 Gemeinsame Taxonomie:** **Abgeschlossen 16.09.2026.** Die
  gemeinsame Frontend-Taxonomie unter `frontend/lib/graphTaxonomy.ts` bündelt
  Node-Kategorien, Entity-Typnamen, Kantenfarben, lokalisierte Kantenlabels,
  Icon-Klassen und deterministische Fallbacks für unbekannte Parser-Typen.
  Knowledge-Graph, Call-Graph, Suche/Referenzen und Node-Icon verwenden damit
  dieselbe Darstellungslogik; eine separate Java-Ansicht wurde nicht gebaut.
  Regressionstests prüfen Java-Typen, Web-/Code-/Dokument-Klassifikation und
  stabile unbekannte Typen.
- [x] **T4.3 Navigation:** **Abgeschlossen 16.09.2026.** Java-Navigation ist
  über Editor/Dateiansicht, globale Suche, Wissensgraph, Call-Graph,
  Link-Manager, Referenz-Drilldown und Entity-Nachbarschaften als
  Regressionstest abgedeckt. Geprüft werden insbesondere `.java`-Erkennung,
  Projekt-/Quellenwechsel sowie stabile Datei-, Zeilen- und Entity-IDs für
  `class`-/`method`-Entities und freie Beziehungstypen wie `CALLS`. Die
  betroffenen Frontend-Tests laufen mit **118/118** grünen Tests; bestehende
  COBOL-Navigationsfälle bleiben unverändert.
- [x] **T4.4 Chat/Retrieval:** **Abgeschlossen 16.09.2026.** Chat-Pins tragen
  jetzt optional die sprachneutrale `CodeEntity`-ID, Typ, Qualified Name und
  Breadcrumbs; alte Datei-/Zeilen-Pins bleiben kompatibel. Der Backend-Kontext
  validiert den Entity-Fokus innerhalb des bestehenden Projekt-/Quellkontexts
  und verwendet dessen autoritative Zeilengrenzen. Das Chat-Retrieval ergänzt
  aufgelöste Java-Kanten (`CALLS`, `INSTANTIATES`, `EXTENDS`, `IMPLEMENTS`,
  `USES_TYPE`, `READS`, `WRITES`) als 1-Hop-Nachbarn im bestehenden harten
  Tokenbudget. Frontend-/Backend-Regressionen decken Fokus-Persistenz,
  Breadcrumb-Anzeige, Java-Nachbarn und Budgetgrenze ab; bestehende COBOL-Pins
  und `CALL`/`COPY`-Erweiterungen bleiben erhalten.

## Paket 5 – Härtung und Release

- [x] **T5.1 Integrationssuite:** Mehrdatei-Java-Repo, gemischtes COBOL/Java,
  Löschungen, abgebrochener Sync und Resume Ende-zu-Ende prüfen. **Abgeschlossen
  16.09.2026:** `parser/tests/test_t51_integration.py` führt Git,
  Java-/COBOL-Parser, Persistenz, Löschung, synthetischen Abbruch und Resume in
  einem Lebenszyklus zusammen. Der Lauf im Compose-Testdienst mit aktuellem
  Workspace-Code ist **1/1 grün**; der Dienst verwendet das interne `db`-/Redis-
  Netzwerk und verändert das produktive DB-Volume nicht.
- [ ] **T5.2 Performance:** Parse-Durchsatz, Peak-RAM, Graphgröße und Resolverzeit
  auf Referenzkorpus messen und Grenzfälle absichern.
- [x] **T5.3 OSS/Betrieb:** **Abgeschlossen 16.09.2026.** Java-Grammatik,
  Lizenzkopie, Upstream-Pin und Offline-Regenerierung sind in
  `docs/OSS-CLEARING.md` und `parser/java/grammar/README.md` dokumentiert.
  `docs/DEPLOYMENT.md` beschreibt die Trennung von finalem Runtime-Image und
  `docker-compose.dev.yml`-Testdienst. Die wirksamen technischen Grenzen und
  die derzeit ausdrücklich nicht vorhandenen Nutzer-/Speicherquoten stehen in
  `docs/OPERATIONS_LIMITS.md`.
- [x] **T5.4 Release-Gates:** **Abgeschlossen 16.09.2026.** Parser-Suite
  `391 passed, 4 skipped`, Backend `373 passed, 1 skipped`, Frontend `655
  passed` in 54 Testdateien, Installer `11 OK`, Ruff und Model-Sync grün.
  Die isolierten Lizenzscans akzeptieren Backend (142), Parser (55) und
  Frontend (327) Pakete ausschließlich über Allowlist bzw. dokumentierte
  Ausnahmen. Die drei produktiven Docker-Images bauen; der Offline-Bundle
  `dist/doctus-offline-bundle-t54-20260916` ist 4,9 GB groß, seine
  SHA256SUMS und Offline-Compose-Konfiguration sind validiert.
- [ ] **T5.5 OSS-Referenzkorpus:** Nach den groben Release-Gates ein großes,
  externes Open-Source-Java-Projekt (bevorzugt JUnit) auf einen festen Commit
  ziehen und als separates Testkorpus prüfen. Lizenz/Version/Transitiv-
  abhängigkeiten werden vor der Nutzung erfasst; das Korpus bleibt außerhalb
  des Doctus-Release-Bundles. Daraus entsteht ein reproduzierbarer Test für
  Parser, Chunks, Beziehungen, Persistenz, Suche und Navigation sowie ein
  messbarer Realbestand für T5.2.

## Fortschritt

- **Abgeschlossen:** T1.1 bis T1.5, T2.1 bis T2.5, T3.1 bis T3.4 sowie T4.1
  bis T4.4.
- **Aktiv:** Paket 5; T5.2 (Performance) und T5.5 (OSS-Referenzkorpus) sind
  offen. T5.4 ist abgeschlossen.
- **Nächstes konkretes TODO:** T5.5 — ein großes, fest gepinntes OSS-Java-
  Projekt (bevorzugt JUnit) außerhalb des Produkt-Bundles importieren und als
  reproduzierbaren Integrations-/Regressionstest nutzen.
- **Noch nicht begonnen:** T5.2 und T5.5.
