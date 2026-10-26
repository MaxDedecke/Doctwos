# Java-25-Parser-Abnahmekorpus

Der Korpus prüft Maven-Strukturen mit fünf Modulen, ein Interface mit zwei
Implementierungen, eine über Qualifier gewählte Runtime-Abhängigkeit, einen
Spring-Endpunkt, JAX-WS/JAXB, WSDL/XSD, Konfiguration und ein AsciiDoc-Handbuch.
Er enthält außerdem eine kompakte Java-25-Quelldatei mit Modulimport.

`test_java_enterprise_acceptance.py` kopiert die Dateien in ein temporäres Git-Repo
und verwendet die echte Import-, Parser-, Persistenz- und Retrieval-Pipeline.
Externe Jakarta-/Spring-APIs bleiben externe Symbole; der Test startet keinen
Maven-Build und keine Webanwendung. Nur die Embedding-Antworten werden ersetzt.

Die erwarteten Namen, Namespace-QNames, Zeilen und Beziehungen stehen ausdrücklich
im Test. Der Lauf prüft den unveränderten zweiten Import, eine geänderte
Dokumentattributdatei und den Wegfall der Runtime-Implementierung im POM.

Die Parser-Abnahme trifft keine Aussage über die Antwortqualität eines LLMs.
