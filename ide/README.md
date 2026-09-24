# Doctus in der IDE (O-325)

Die Integration zeigt indizierte COBOL-`CALL`-/`COPY`-Referenzen und Java-
`CALLS`-/`EXTENDS`-/`IMPLEMENTS`-/`INSTANTIATES`-Beziehungen mit Ziel und
Auflösungsstatus an. In VS Code öffnet ein aufgelöstes Ziel aus derselben Git-
Quelle die lokale Definition; andere Referenzen öffnen den Doctus-Graph.
Die URL enthält nur Projekt, Quelle, Repo-Pfad, Zeile und optional die Buildvariante;
der Browser prüft die normale Doctus-Anmeldung und Projektberechtigung.

## Voraussetzungen

1. Im Doctus-Browser unter **Einstellungen → IDE / MCP** ein persönliches Token
   erstellen. Dasselbe Token authentifiziert die lesende IDE-API. Ein Widerruf
   sperrt IDE-Abfragen sofort.
2. Die numerischen IDs des Projekts und der Git-Quelle ermitteln. Der Repo-Pfad
   der lokalen Datei muss dem indizierten Pfad entsprechen. Bei Monorepos kann
   `repositoryRoot` auf ein Unterverzeichnis zeigen.
3. Die installierte Doctus-Instanz als API- und Web-URL eintragen. Für entfernte
   Instanzen HTTPS verwenden.

## VS Code

Den Ordner `ide/vscode` als lokale Extension in das VS-Code-Extensionsverzeichnis
unter dem Namen `doctus-ide-0.1.2` kopieren und VS Code neu laden. Bei Remote-SSH
gehört er in das Extensionsverzeichnis des Remote-Hosts. Alternativ kann der
Ordner als VSIX paketiert werden.
Beispiel für `.vscode/settings.json` im Repository:

```json
{
  "doctus.apiUrl": "https://doctus.example",
  "doctus.webUrl": "https://doctus.example",
  "doctus.projectId": 42,
  "doctus.sourceId": 17,
  "doctus.repositoryRoot": "."
}
```

Das Token über **Doctus: Set personal token** eingeben; VS Code speichert es in
Secret Storage. Danach erscheinen CodeLens über indizierten COBOL- und Java-
Beziehungen und Hover-Informationen am referenzierten Namen. Für Java nutzt der
Hover die exakte Symbolposition aus neu indizierten Dateien; bei älteren Indizes
wird nur eine eindeutige Textfundstelle hervorgehoben. **Doctus: Open source line in
graph** öffnet die aktuelle Editorzeile auch ohne eine solche Referenz.

### Copilot-Agent und MCP

Die Editor-Extension und der MCP-Server haben unterschiedliche Aufgaben: CodeLens
und Hover helfen im Editor; Copilot kann über MCP indizierte Beziehungen prüfen.
Für die Remote-SSH-Session muss der MCP-Server `doctus` im Agenten aktiviert sein.
Die projektweite Datei [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
gibt Copilot konkrete Anlässe für Doctus-Abfragen vor. Für andere indizierte
Repositories kann dieselbe Anweisung als persönliche Copilot-Anweisung unter
`~/.copilot/copilot-instructions.md` auf dem Agent-Host liegen. Die Projekt-ID
liest der Agent aus der jeweiligen `.vscode/settings.json`; bei fehlender ID
fragt er die sichtbaren Projekte über MCP ab.

In VS Code **Chat: Open Customizations** öffnen und für den aktiven Copilot-
Harness prüfen, ob die Anweisung geladen und die `doctus`-Tools aktiviert sind.
In einem neuen Agent-Chat beispielsweise nach der Aufrufkette eines indizierten
Symbols fragen. In **References** und den Tool-Aufrufen kontrollieren, ob Copilot
die Anweisung und mindestens ein passendes Doctus-Tool verwendet hat. Ein
MCP-Fehler oder ein fehlender Index muss im Ergebnis als Lücke benannt werden;
der Index ersetzt nicht den aktuellen Quellcode im Workspace.

## JetBrains

`ide/doctus_lsp.py` ist ein stdio Language Server ohne
Python-Pakete. Im LSP-Client der IDE als Serverkommando registrieren:

```text
python3 /pfad/zu/Doctwos/ide/doctus_lsp.py
```

Die Umgebung des Serverprozesses setzen:

| Variable | Bedeutung |
|---|---|
| `DOCTUS_API_URL` | Backend-URL, z. B. `https://doctus.example` |
| `DOCTUS_WEB_URL` | Browser-URL, z. B. `https://doctus.example` |
| `DOCTUS_TOKEN` | Persönliches MCP-Token |
| `DOCTUS_PROJECT_ID` | Numerische Projekt-ID |
| `DOCTUS_SOURCE_ID` | Numerische Git-Quellen-ID |
| `DOCTUS_REPOSITORY_ROOT` | Absoluter Pfad zum lokalen Repo-Root |
| `DOCTUS_VARIANT_KEY` | Optionale Buildvariante |

Den Server für die benötigten Dateitypen aktivieren. Er bietet die LSP-Methoden
`textDocument/codeLens`, `textDocument/hover` und `workspace/executeCommand` an.
Ein Client mit CodeLens-Unterstützung zeigt die Links direkt über den Zeilen;
der Hover enthält zusätzlich einen normalen HTTPS-Link für Clients, die den
CodeLens-Befehl nicht ausführen. Für jede andere lokale Kopie eines Repos sind
eigene Projekt-/Quellen-IDs beziehungsweise eine eigene Serverinstanz nötig.

## Eclipse

Eclipse kann den stdio-Server über LSP4E anbinden. Für einen ersten Versuch
installiere LSP4E, aktiviere den **Generic Editor** für die betroffenen Dateien
und definiere in den LSP4E-Einstellungen einen benutzerdefinierten Language
Server mit dem Kommando `python3 /pfad/zu/Doctwos/ide/doctus_lsp.py`. Weise ihm
die Content Types oder Dateiendungen des Bestands zu und setze dieselben
`DOCTUS_*`-Umgebungsvariablen wie oben. LSP4E dokumentiert die dynamische
Konfiguration ohne Eclipse-Plugin ausdrücklich als geeigneten Weg zum Testen;
für eine dauerhaft verteilte Integration empfiehlt Eclipse den Extension Point
`org.eclipse.lsp4e.languageServers`.

Hover ist die sinnvollste erste Abnahme: LSP4E stellt Language-Server-Hover im
Editor dar, und Doctus liefert darin einen normalen HTTPS-Graph-Link. Die
aktuelle LSP4E-Funktionsübersicht nennt CodeLens nicht ausdrücklich. Deshalb
müssen CodeLens-Darstellung, Ausführung von `doctus.openGraph` über
`workspace/executeCommand` und der vom Server angeforderte externe Browseraufruf
(`window/showDocument`) in der konkreten Eclipse-Version praktisch geprüft
werden. Diese generische Konfiguration ist noch keine bestätigte Eclipse-
Abnahme.

Falls CodeLens oder das Öffnen des Links nicht funktionieren, die nützlichen
Eclipse-Funktionen sind weiterhin erreichbar: Hover mit Graph-Link und ein
expliziter **Doctus: Open current source line in graph**-Befehl. Dafür wäre ein
kleines Eclipse-Plugin nötig, das Einstellungen samt Token in Eclipses Secure
Storage hält, den Language Server pro Projekt startet und den Befehl mit
Eclipses Browser-API ausführt. Damit hängt die Navigation nicht von
`window/showDocument` ab. CodeLens kann das Plugin über LSP4E-CodeMining
darstellen, sofern die eingesetzte LSP4E-Version das anbietet; andernfalls kann
der Befehl über Editor-Kontextmenü/Toolbar angeboten werden.

## API-Vertrag

`GET /ide/file?project_id=…&source_id=…&path=…[&variant_key=…]` erwartet
`Authorization: Bearer <persönliches MCP-Token>` und liefert bis zu 2000
persistierte COBOL- oder Java-Referenzen einer exakt indizierten Datei. Bei größeren
Dateien meldet der Server `413`, sodass keine unvollständigen Hinweise als
vollständig erscheinen. Die Antwort trägt `Cache-Control: no-store`.
