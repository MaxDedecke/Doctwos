# Java-Testprojekt: Parser-Erweiterungen

Auftrag vom 26.10.2026: Java 25, Maven-Multimodulauflösung, DI/Endpunkte,
SOAP/JAX-WS/JAXB mit WSDL/XSD und AsciiDoc-Zusammensetzung erweitern.
Das ursprünglich vorgeschlagene Paket 5 (Vereinheitlichung von Tabellen,
Bildern, Quellcodeverweisen, Markdown und Javadoc) ist ausdrücklich ausgeschlossen.

## Java 25 und Maven

- Modulimporte und kompakte Quelldateien werden durch die eingecheckte ANTLR-Grammatik
  verarbeitet; implizite Klassen besitzen quellzeilengenaue Methoden und Aufrufe.
- Exporte eingecheckter JPMS-Modulbeschreibungen unterstützen Modulimporte.
  Nicht vorhandene externe Modulbeschreibungen werden nicht geraten.
- Der globale Java-Auflöser verwendet ein statisches Maven-Reaktormodell:
  eingecheckte Parents und BOMs, Properties, Dependency-Management, direkte und
  transitive interne Dependencies, Scopes und Exclusions.
- `DOCTUS_MAVEN_PROFILES=soap,integration` aktiviert benannte Profile.
  Ohne explizite Auswahl werden `activeByDefault`-Profile verwendet.
- POM-Änderungen werden auch gegen unveränderte Java-Entities neu ausgewertet;
  Produktionsquellen dürfen keine Testklassen verwenden, Abhängigkeiten dürfen
  nicht auf Testquellen eines anderen Moduls zeigen.
- Maven und seine Plugins werden nicht ausgeführt. Externe Parents/BOMs,
  umgebungsabhängige Profilaktivierung und unbekannte Koordinaten bleiben
  als `maven_issues` am Java-Dateiwurzelobjekt sichtbar. Das statische Modell
  ist kein Ersatz für die vollständige Modellberechnung eines Maven-Builds.
- Java-Preview-Features sind ohne eigenen Abnahmefall nicht als unterstützt zugesagt.

Regressionen: `parser/tests/test_java25_maven_workspace.py`, vorhandener
Java-Golden-Korpus und Maven-Persistenztests. Parserstände werden für die
inkrementelle Neuverarbeitung erhöht.
