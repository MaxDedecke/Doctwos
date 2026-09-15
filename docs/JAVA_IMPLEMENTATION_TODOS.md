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
- [ ] **T1.3 Registry:** `ParserEntry` und `STRUCTURE_PARSERS` nach
  `parser/core/registry.py` verschieben; `prepared_source`, explizite Root-Typen
  und parserabhängige Version/Fingerprint-Hooks einführen. COBOL-Aufrufer und
  Tests kontrolliert migrieren.
- [x] **T1.4 Eltern-Persistenz:** `_parent_id` anhand des expliziten Parent-QName
  bestimmen; alten Punkt-Split nur als Kompatibilitäts-Fallback für Ergebnisse
  ohne Parent-QName behalten. Parent-Scope- und Reparse-Tests ergänzen.
- [ ] **T1.5 COBOL-Gate:** Parser-Golden-Files, Persistenz-/Connector-Tests und
  Backend-Entity-Tests ausführen; COBOL-Golden-Dateien dürfen sich nicht ändern.

## Paket 2 – Java-Deklarationen und Chunks

- [ ] **T2.1 Grammatik-Freigabe:** Java-21-Grammatik, Upstream-Commit,
  Sprachstand, Lizenztext und Regenerierungsweg verifizieren und dokumentieren.
- [ ] **T2.2 Parser-Bridge:** ANTLR-Lexer/Parser, begrenzte Diagnosen,
  Originalzeilen-Mapping und fehler-tolerantes Ergebnis implementieren.
- [ ] **T2.3 Declaration Visitor:** Compilation Units, Package/Module, alle
  vereinbarten Typen, Methoden, Konstruktoren, Felder und Initializer mit
  stabilen QNames, Parent-QNames, Metadaten und Zeilenbereichen erfassen.
- [ ] **T2.4 Chunking und Git:** Symbolorientierte Java-Chunks, Fallback,
  Java-Extension, Opt-in-Konfiguration, Build-Excludes und Modul-Metadaten
  integrieren.
- [ ] **T2.5 Golden-Korpus:** Java-Fixtures, Golden-Files und Regenerierungsskript
  aufbauen; Java-8- und Java-21-Syntax sowie beschädigte Dateien abdecken.

## Paket 3 – Beziehungen und Auflösung

- [ ] **T3.1 Kantenextraktion:** Imports, Vererbung, Implementierungen,
  Typnutzung, Aufrufe, Instanziierungen sowie Feldzugriffe mit Quellbeleg
  erfassen.
- [ ] **T3.2 Lokale Auflösung:** Eindeutige Ziele im selben Typ/Dateikontext
  auflösen; Überladungen anhand normalisierter Signaturen behandeln.
- [ ] **T3.3 Globaler Resolver:** Java-Regeln für Package, Imports, `java.lang`,
  Besitzer-Typ und Argumente ergänzen; mehrdeutige/externe Ziele unresolved
  lassen.
- [ ] **T3.4 Persistenzintegration:** Generische Kanten-Zieltypen und Resolver
  integrieren; Mehrdatei-, Mehrdeutigkeits-, Reparse- und Resume-Fälle testen.

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

- **Abgeschlossen:** T1.1, T1.2 und T1.4.
- **Als Nächstes:** T1.3 (sprachneutrale Registry); danach T1.5 als Paket-Gate.
- **Noch nicht begonnen:** T1.3 und T1.5 bis T5.4.
