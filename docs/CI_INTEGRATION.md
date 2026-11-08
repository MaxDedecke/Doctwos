# Maven- und Testergebnisse aus der CI

Im Änderungspaket „CI-Anbindung verwalten“ öffnen. Ein Projekt-Admin wählt die
Git-Quelle, gibt dem Zugang einen Namen und erstellt ein CI-Token.
Das Token einmalig als Secret `DOCTUS_CI_TOKEN` in der Pipeline speichern.
`DOCTUS_SOURCE_ID` und `DOCTUS_URL` als Pipelinevariablen setzen. Die URL zeigt
auf die erreichbare Backend-Basis einschließlich etwaigem API-Präfix.
Token sind an Quelle, Repository, konfigurierten Branch und die Berechtigungen
ihres Erstellers gebunden. Die Oberfläche stellt standardmäßig 90 Tage
Gültigkeit aus. Projekt-Admins können Tokens widerrufen.

Der CI-Runner benötigt Python 3.11+, Git und das Projekt-JDK. Er verwendet den
vorhandenen Maven-Wrapper, andernfalls `mvn` aus dem PATH. Das Git-Checkout
muss dem gemeldeten Commit entsprechen und für versionierte Dateien sauber sein.
Die Doctus-Instanz muss vom Runner aus erreichbar sein. Für Unternehmens-CAs
kann `DOCTUS_CA_FILE` auf ein PEM-Bundle zeigen.

## GitHub Actions

`docs/examples/maven-ci.github.yml` zeigt einen vollständigen Job.
Die Composite Action führt `clean verify` aus, erzeugt anschließend das
effektive POM und JSON-Abhängigkeitsbäume und veröffentlicht die Ergebnisse.
Ein fehlgeschlagener Maven-Build liefert nach dem Upload weiterhin seinen
ursprünglichen Fehlercode. Für mehrere JDKs/Profile erhält jede Kombination
einen eigenen stabilen `variant`-Wert. Ein freigegebener Doctus-Commit kann
anstelle von `@develop` als Action-Referenz verwendet werden.

Die Beispielpipeline läuft für den konfigurierten Main-Branch. Weitere Branches
verwenden die entsprechende Doctus-Git-Quelle und deren Token.
Zugriff auf die private Action muss für das aufrufende Repository eingerichtet
sein. Selbst gehostete Doctus-Instanzen benötigen gegebenenfalls einen
selbst gehosteten GitHub-Runner im selben Netz.

## GitLab und andere CI-Systeme

Der Offline-Bundle enthält `ci-runner/`. Diesen Ordner auf dem CI-Runner
bereitstellen und `DOCTUS_CI_RUNNER` auf
`ci-runner/scripts/publish_maven_ci.py` setzen. Alternativ dieselbe Datei
aus einem vollständigen Doctus-Checkout verwenden. Die beiden zugehörigen
Python-Helfer werden relativ zum Tool-Verzeichnis geladen. Eine zusätzliche
Python-Paketinstallation ist dafür nicht nötig.

`docs/examples/maven-ci.gitlab.yml` verwendet dieses Werkzeug. GitLab-Pipeline-ID,
Jobname, Job-ID als Wiederholungsnummer und Commit werden automatisch übernommen.
Jenkins verwendet Buildnummer und Jobname. Andere Systeme übergeben
`--provider generic --run-id <stabile-id> --job-name <job> --branch <branch>`.
`--profiles integration,soap` gilt sowohl für den Build als auch für die
Metadatenziele. Zusätzliche Maven-Argumente können wiederholt mit
`--maven-arg=-Dname=value` übergeben werden.

Für bestehende Buildjobs ist `--publish-only --status success|failed|cancelled`
verfügbar. Dann müssen deren Artefakte bereits für genau dieses Checkout
vorliegen. Der normale Runner entfernt alte bekannte Reportdateien vor dem
Build, damit ein früh abbrechender neuer Lauf keine alten Testergebnisse meldet.

## Datenfluss und Anzeige

Die CI veröffentlicht einen abgeschlossenen Job an `POST /ci/builds` mit
`Authorization: Bearer <CI-Token>`. Der Browserzugang und persönliche
MCP-Tokens sind getrennt davon. Der Upload darf vor dem Git-Sync eintreffen.
Er wird dauerhaft gespeichert und erscheint automatisch im Änderungspaket,
sobald dessen vollständig indizierter Quellstand denselben Commit,
dieselbe Quelle und den passenden Branch/Repository-Kontext hat.

Pro Maven-Modul werden das effektive POM, der JSON-Abhängigkeitsbaum und
Surefire-/Failsafe-Ergebnisse gesammelt. Das effektive POM wird vor dem Upload
auf Modulkoordinaten und Abhängigkeiten reduziert. Properties, Plugin-Konfiguration,
Testausgaben und Stacktraces werden verworfen. Artefakt-Hashes halten den Bezug
zu den Originalberichten der Pipeline. Testergebnisse umfassen Zähler und eine
begrenzte Liste fehlgeschlagener Tests. Pipeline-Links öffnen die vollständigen
CI-Logs. Buildstatus und Teststatus sind getrennt sichtbar.

Identisch wiederholte Uploads desselben Jobs/Versuchs liefern denselben
Datensatz. Abweichende Inhalte derselben Identität liefern HTTP 409.
Ein neuer Versuch verwendet eine größere `attempt`-Nummer. Für dieselbe
Pipeline, Job und Variante wird im Paket der höchste vorhandene Versuch gezeigt.
Verspätet eintreffende frühere Versuche ersetzen ihn nicht. Unterschiedliche
Pipelines und Varianten bleiben einzeln sichtbar.

Fehlende oder beschädigte Testberichte bedeuten „unbekannt“ beziehungsweise
„unvollständig“. Eine grüne Pipeline allein bestätigt keine bestandenen Tests.
Es gibt keine automatische Aussage über Testabdeckung. Ein erfolgreicher Teil
eines begrenzten Berichtssatzes bestätigt keinen vollständigen Testlauf.

## Grenzen und Betrieb

Ein Upload umfasst maximal 8 MB, 200 Modulberichte und 1.000 Testreports je Modul.
Der Runner begrenzt die Gesamtzahl der eingesammelten Testreports auf 1.000.
Große Maven-Artefakte werden mit explizitem Hinweis ausgelassen, wenn sonst der
gesamte Upload zu groß würde. Das Paket zeigt bis zu 20 passende CI-Jobs und
meldet eine Kürzung. Die gespeicherten Berichte bleiben unveränderlich.
Aufbewahrung und Bereinigung sind Teil der Projekt-/Quellenverwaltung.

Die Herkunft wird durch den quellengebundenen CI-Zugang belegt. Die Angaben
stammen aus dessen Pipeline. Doctus führt beim Import keine Maven-Plugins aus
und übernimmt die Artefakte nicht automatisch in den Java-Resolver-Klassenpfad.

Maven dokumentiert das aggregierte effektive POM und das JSON-Format des
Dependency-Plugins in den offiziellen Pluginbeschreibungen.
[Effective POM](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html),
[Dependency Tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

## Lokale Abnahme am 07.11.2026

911 Backend-Tests (1 Skip), 854 Parser-Tests (7 Skips) und 1.108 Frontend-Tests
bestanden. Zusätzlich bestanden 15 Installer-/Offline-Tests, TypeScript,
ESLint, Design-Token-Prüfung, Ruff, Formatprüfung und Shell-Syntaxprüfung.
Migration 0047 wurde auf einer isolierten Datenbank vorwärts und rückwärts
geprüft. Der Runner-End-to-End-Test verwendet simuliertes Maven und einen
echten HTTP-Upload durch die API bis zur Datenbank. Eine externe
Unternehmenspipeline wird mit deren URL, Quell-ID, Runner und CI-Secret
in ihrer Zielumgebung aktiviert.

## Nutzung über Chat und MCP

CI-Läufe sind auch in `answer_context`, `search_knowledge` und
`inspect_change_package` verfügbar. Die kompakte Darstellung zeigt denselben
Build-/Teststatus und dieselbe Commit-Zuordnung wie das Web-Änderungspaket,
begrenzt aber die Detailmenge und weist Kürzungen aus. Das reine Lesen benötigt
den bestehenden persönlichen MCP-Zugang; CI-Upload-Tokens bleiben getrennt.

Der Chat zitiert einen gelieferten Lauf mit `[CI:id]` und speichert dessen
Snapshot an der Antwort. Die Quellenanzeige öffnet die Build-/Testdetails und
den Pipeline-Link. Ein späterer CI-Lauf verändert keine alte Chat-Antwort.
