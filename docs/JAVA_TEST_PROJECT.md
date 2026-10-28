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

## SOAP-Schnittstellen und generierte Quellen

- WSDL 1.1 wird in Services, Ports, Bindings, Port-Types, Operationen, Nachrichten
  und Parts zerlegt; SOAP-Actions und Endpoint-Adressen bleiben erhalten.
- XSDs liefern globale/lokale Elemente, Attribute und benannte/anonyme Typen.
  Typverwendung, Ableitung, Referenzen und lokale Schema-/WSDL-Imports werden
  über Namespace-QNames verbunden. Eingebaute XSD-Typen sind ausdrücklich extern.
- JAX-WS-Endpunkte werden mit WSDL-Operationen, Spring-WS-Endpunkte mit ihren
  Request-Elementen verbunden. JAXB-Annotationen verbinden Java-Typen und Felder
  mit XSDs; `package-info.java` liefert modulbezogene Namespace-Defaults.
- `DOCTUS_INCLUDE_GENERATED_JAVA=true` erlaubt vorhandene Java-Dateien unter
  `target/generated-sources`. Andere Build-Artefakte bleiben ausgeschlossen.
  Die Einstellung geht in den Analyse-Fingerprint ein. Doctus startet weder
  Maven-Plugins noch `wsimport`/`xjc`; fehlende generierte Quellen sind eine Lücke.
- Umbenannte/entfernte Zieltypen löschen die ursprüngliche Quellbeziehung nicht;
  sie wird neu aufgelöst oder bleibt mit Begründung unaufgelöst.
- Externe Schemas/URLs werden nicht heruntergeladen. Die Strukturanalyse ersetzt
  keine vollständige XSD-Validierung und keine JAX-WS-/JAXB-Laufzeit; komplexe
  Adapter und herstellerspezifische Bindings brauchen eigene Abnahmefälle.

Abnahme: `test_soap_schemas.py` prüft die Kette Java-Endpunkt → WSDL-Operation →
Nachricht → XSD einschließlich JAXB, Namespaces, Wiederholung und Zieländerung.

## AsciiDoc-Zusammensetzung

- Der Git-Parser verarbeitet Dokumentattribute, Attribute aus eingebundenen
  Dateien, `ifdef`/`ifndef`/`ifeval`, verschachtelte lokale Includes sowie
  `leveloffset`, `lines` und Tag-Auswahl. Includes in Quellcodeblöcken werden
  ebenfalls erkannt; deren Inhalt wird nicht als Kapitel interpretiert.
- `DOCTUS_ASCIIDOC_ATTRIBUTES='{"lang-de":"","product":"Doctus"}'` setzt
  explizite Buildattribute. Diese haben Vorrang vor Dokumentdefinitionen;
  Änderungen invalidieren den Analyse-Fingerprint.
- Das Dateiwurzelobjekt enthält unter `composition_outline` die logische
  Kapitelreihenfolge mit Quelldatei und physischer Zeile. Die Dateien werden
  weiterhin einzeln indexiert; eingebundene Dateien werden nicht unter falschen
  Zeilennummern in den Haupttext kopiert. Kapitel und Text der Hauptdatei erhalten
  die wirksamen Attribute und Bedingungen, inklusive Herkunftsangaben.
- Include-Beziehungen tragen Optionen und ausgewählte Originalzeilen. Das
  Retrieval verfolgt verschachtelte Includes begrenzt und liefert Ausschnitte
  aus ihren Originaldateien, ohne persistierte Chunks zu verändern.
- Zyklen, fehlende Dateien und nicht auswertbare Bedingungen erzeugen Diagnosen.
  Externe URLs werden nur als externe Referenzen geführt. Repository-Grenzen,
  maximal 32 Include-Ebenen, 4 MiB pro Include und 50000 verarbeitete Zeilen
  begrenzen die Verarbeitung.
- Dies ist eine Quellenanalyse mit logischer Buchgliederung, kein Asciidoctor-
  HTML-Renderer. Ein Fragment kann in mehreren Büchern unterschiedliche
  Attributkontexte haben; die jeweilige Gliederung steht am Buchwurzelobjekt.
  Die ausgeschlossenen Erweiterungen aus Paket 5 bleiben ausgeschlossen.

Abnahme: `test_asciidoc_composition.py` und der bestehende AsciiDoc-Korpus.

## Gemeinsame Abnahme

`parser/tests/fixtures/java25_enterprise` enthält einen versionierten Korpus mit
fünf Maven-Modulen, Java 25, zwei Implementierungen, Runtime-DI, Spring-Endpunkt,
JAX-WS/JAXB, WSDL/XSD, Properties/YAML und einem zusammengesetzten Handbuch.
`test_java_enterprise_acceptance.py` führt Git-Import, Parser, Datenbank und
Backend-Graph-Retrieval gemeinsam aus. Lediglich Embeddings werden ersetzt.

Geprüft werden ausgewählte statt beliebiger Implementierungen, eine durchgängige
SOAP-/XSD-Verbindung, Originalzeilen eingebundener Ausschnitte, Modulgrenzen,
UTF-8, unveränderter Folgeimport, geänderte Dokumentattribute und eine entfernte
Runtime-Abhängigkeit. Abhängigkeiten, die erst beim Import entdeckt werden,
fließen am Laufende in den stabilisierten Fingerprint ein; dadurch verursacht
der unveränderte zweite Import keine unnötige Neuverarbeitung.

Ausführen (getrennte Parser-/Backend-Umgebungen mit Test-DB und Test-Redis):

```bash
cd parser
python -m pytest tests/test_java_enterprise_acceptance.py -q
python -m pytest tests/ -q
cd ../backend
python -m pytest tests/ -q
```

Die Abnahme misst Parser- und Retrieval-Verhalten. Fachliche Antwortqualität
und kundenspezifische Framework-/Generatorvarianten müssen am echten Zielprojekt
mit eigenen erwarteten Ergebnissen gemessen werden.

## Ergänzungen aus der Lückenprüfung vom 28.10.2026

Java-Strukturversion 12 erhält die Verzweigungspfade moderner `switch`-Ausdrücke
und `switch`-Anweisungen mit Pfeilzweigen, ternärer Ausdrücke sowie der bedingten
Auswertung von `&&` und `||`. Selektoren und Bedingungen selbst werden nicht dem
ausgewählten Ergebniszweig zugerechnet. Verschachtelte Pfade behalten Originalzeilen
und das bestehende, sprachneutrale `control_path`-Format der Prozessansicht.
Abnahme: `parser/tests/test_java_control_paths.py` und vorhandene Java-Golden-Tests.

Strukturversion 13 ergänzt Pattern-Bindungen mit expliziten Sichtbarkeitsbereichen
für `if`, `switch`/`when`, boolesche Kurzschlussauswertung und negierte Rückkehr-Guards.
Eine Weitergabe des Testergebnisses an eine beliebige Funktion erweitert den
Bindungsbereich nicht. Die lokale Grammatikkorrektur verhindert, dass `Service s`
als ein Typ statt als Pattern gelesen wird. Für `var` aus Factory-Aufrufen wird
der Rückgabetyp des an der Initialisierungsstelle tatsächlich aufgelösten Aufrufs
im Importkontext der Factory verwendet. Mehrdeutige Initialisierer bleiben offen.
Abnahme: `parser/tests/test_java_pattern_inference.py`; Java-Golden-Dateien aktualisiert.

Strukturversion 14 modelliert implizite Record-Accessor als ausdrücklich synthetische
Methoden an der Zeile ihrer Komponente; explizite Accessor haben Vorrang. Receiver
aus vollständig indizierten Arrays erhalten ihren Elementtyp. Direkte generische
Receiver wie `Box<Service>` spezialisieren den Rückgabetyp `T` von `get()`; generische
Methodenparameter werden nicht mit Klassenparametern verwechselt. Nicht belegbare
Dimensionen und Wildcards bleiben offen. Abnahme: `test_java_receiver_types.py`.

Strukturversion 15 verbindet Aufrufe eindeutig initialisierter lokaler Lambdas über
`DISPATCHES_TO` mit ihrem Körper; die ursprüngliche Interface-Aufrufkante bleibt
erhalten. Wiederzuweisungen, unvollständige Datenflusstabellen und unvollständig
aufgelöste geerbte SAM-Verträge erzeugen keine behauptete Bindung. Die Ableitung
wird beim globalen Auflösen neu berechnet, sodass Wiederholung und Reparse keine
doppelten oder veralteten Verbindungen hinterlassen.

Das Datenflusslimit bleibt bei 80 Anweisungen. Überschreitungen tragen jetzt
`data_flow_truncated`, `data_flow_omitted` und eine explizite Warnungsdiagnose.
MCP-Methodenmetadaten und Herkunftsbeweise geben die Einschränkung weiter, auch
wenn die gesuchte Zuweisung hinter dem Limit liegt. Abnahme: Java-Lambda-Tests,
`test_lambda_dispatch_persistence.py` und `backend/tests/test_data_flow_limit.py`.

Die bestehende Codeansicht bietet einen aufklappbaren Bereich „Objektdetails“ mit
Objektwahl innerhalb der Datei. Erst beim Öffnen werden die Metadaten des Objekts
und der Dateiwurzel mit dem aktuellen Projektkontext geladen. Verspätete Antworten
eines vorherigen Fokus werden verworfen. Rückgabetypen/-ausdrücke, Annotationen,
deklarierte Ausnahmen, Exception-Bereiche und Zuweisungsherkunft sind an ihren
Originalzeilen navigierbar. Die Ansicht zeigt die Datenflusskürzung ausdrücklich.

Die Dateiwurzel ergänzt aktive Maven-Profile, Compile-/Laufzeitsichtbarkeit und
konkrete Auflösungshindernisse. Endpunkte zeigen HTTP-/SOAP- und Parameterdetails;
Beans zeigen Namen, bereitgestellte Typen, Profile und ihren statisch ermittelten
Aktivierungszustand. Unbekannte Aktivierung wird nicht als aktiv dargestellt.
Belegte `INJECTS`-/`DISPATCHES_TO`-/`EXPOSES`-Verbindungen öffnen die Zielquelle;
weitere Seiten bleiben über das vorhandene Referenzen-Menü erreichbar.
Abnahme: `frontend/components/EntityAnalysisDetails.test.tsx`.

Gesamtprüfung dieses Stands: 751 Parser-, 749 Backend- und 966 Frontend-Tests
bestanden (5 Parser- und 2 Backend-Tests umgebungsbedingt übersprungen), außerdem
TypeScript, Lint/Format, Modellabgleich und Design-Token-Prüfung. Neue Struktur-
und Ableitungsdaten werden über den regulären Quellen-Sync im Worker erneuert;
die angehobene Java-Parserversion invalidiert dabei die bisherigen Analyse-Fingerprints.
