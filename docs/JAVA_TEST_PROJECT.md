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

## Frameworks, Endpunkte und Konfiguration

- Annotationen an Parametern bleiben der konkreten Parameterdeklaration zugeordnet.
- Spring-MVC- und JAX-RS-Endpunkte besitzen Pfad/HTTP-Methode; Spring-WS-Payloads
  und JAX-WS-Webmethoden besitzen SOAP-Operationsmetadaten. `EXPOSES` verbindet
  diese Objekte mit der Java-Methode, inklusive Originalzeilen.
- CDI/EJB/Spring-Injection wird über `INJECTS` modelliert. Namen, Qualifier,
  Primary, Factory-/Producer-Methoden und einzelne Spring-Konstruktoren werden
  berücksichtigt. Eindeutig zugewiesene Konstruktor-/Setterparameter können
  über den vorhandenen Datenfluss ein Feld binden.
- `DISPATCHES_TO` beschreibt einen statisch belegten Kandidaten einer ausgewählten
  Bean. Die ursprüngliche `CALLS`-Kante auf die deklarierte Methode bleibt erhalten.
  Fehlende/mehrdeutige Beans werden nicht durch eine beliebige Implementierung ersetzt.
- `DOCTUS_SPRING_PROFILES=prod,soap` bestimmt die expliziten Spring-Profile.
  Unausgewählte CDI-Alternatives und unbekannte Boot-Conditions werden nicht als
  aktive Beans behauptet. Laufzeit-Beanregistrierung und komplexe Profil-/SpEL-Ausdrücke
  erfordern zusätzliche Belege und sind nicht als vollständig aufgelöst zugesagt.
- Bean-Auswahl verwendet den Maven-Laufzeitkontext; reine Runtime-Abhängigkeiten
  werden dadurch für DI sichtbar, ohne die Java-Compile-Sichtbarkeit zu erweitern.
- Spring-XML-Beans und direkte Referenzen werden als `spring_bean`, `CONFIGURES`
  und `INJECTS` erfasst und bei eindeutiger Zuordnung mit Java verbunden.
- YAML/JSON/INI-Konfiguration liefert Schlüssel-Entities und physische Zeilen;
  YAML-Dokumente können explizite Profilangaben tragen. Property-Verweise werden
  im Modulkontext aufgelöst. Geheimniswerte erscheinen nicht in den zusätzlichen
  Vorschau-Metadaten; der vorhandene verschlüsselte Quelltext bleibt erhalten.
- Ableitungen werden bei jedem globalen Auflösungslauf neu berechnet, nach
  Quelle und Variante getrennt. Endpunkte, DI und Dispatch sind in Graph-Retrieval
  und Callgraph verfügbar; diese Erweiterung fügt keine UI-Ansicht hinzu.

Abnahme: `test_java_frameworks.py`, `test_enterprise_configuration.py` und
`test_framework_persistence.py` einschließlich wiederholter Auflösung.
