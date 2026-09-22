# Doctus: Checkliste für den ersten On-Prem-Test

Stand: 18.09.2026. Prüfgrundlage: Commit `e8e07f5`.

Dieses Dokument dient als gemeinsame Arbeitsliste für Betreiber und Agenten.
Die Prüfung ist abgeschlossen; die unten aufgeführten technischen Maßnahmen
wurden im Rahmen dieser Prüfung noch nicht umgesetzt. Vor Änderungen den aktuellen
Code prüfen, da sich Befunde seit dem Prüfstand geändert haben können.

## Ziel und verbindliche Vorgaben

- Zielplattform ist eine Linux-VM oder Linux-Maschine. Distribution, Architektur
  und konkrete Ressourcen sind noch offen.
- Ollama wird immer mitgeliefert. Im vorgesehenen Erstbetrieb nutzt Doctus jedoch
  einen Modellserver auf einer anderen On-Prem-Maschine im Intranet.
- Die Remote-Schnittstellen sind laut Betreiber OpenAI-kompatibel.
- Chat: vorgeschriebenes Qwen-32B-Modell; genaue Modellkennung und URL noch offen.
- Embeddings: vorgeschriebenes Qwen-4B-Modell, 8100 Tokens Kontext und 1024
  Dimensionen; eigener Endpunkt mit `/embeddings`, genaue URL und Port noch offen.
- Chat- und Embedding-Konfiguration müssen unabhängig und ohne Image-Neubau
  änderbar sein: URL, Port, Pfad, Modellkennung, gegebenenfalls API-Schlüssel und
  Kontextparameter.
- `bge-m3` war ein bisheriger Standardwert und ist keine Lieferanforderung.
- Automatische Modell-Downloads sollen im Zielbetrieb ausgeschaltet sein.
- Transportweg: Build-Maschine → Google Drive → Handy → Firmen-SharePoint →
  Arbeitsclient → interne Zielmaschine. Bevorzugtes Lieferformat: versioniertes ZIP.
- Eine erfolgreiche Offline-Generalprobe mit exakt dem Lieferpaket ist
  Voraussetzung für die Versandfreigabe.
- Zu analysierender Bestand laut Nutzer: 94 % Java, 3,7 % XSLT, 1,6 % Shell,
  0,5 % HTML und 0,1 % JavaServer Pages (JSP). Die Summe von 99,9 % wird als
  Rundungsrest behandelt; Messbasis, Größe und tatsächliche Dateien sind unbekannt.
  Aus dem Sprachmix werden keine konkreten Frameworks oder Java-Versionen abgeleitet.

**Embedding-Modellwechsel:** Indexierung und Suchanfragen müssen dasselbe
Embedding-Modell verwenden. Gleiche Dimensionen machen unterschiedliche Modelle
nicht kompatibel. Ein Modellwechsel bei vorhandenen Daten erfordert eine
vollständige Neueinbettung. Die aktuelle Datenbank setzt 1024 Dimensionen voraus.

**Lokales Ollama:** Mitlieferung bedeutet nicht automatisch betriebsbereiten
Ersatzbetrieb. Dafür müssen passende Modellgewichte, Ressourcen und eine geprüfte
Umschaltung für Chat und Embeddings vorhanden sein. Ein lokales `bge-m3` ist kein
unmittelbarer Ersatz für einen bereits mit Qwen eingebetteten Datenbestand.

## Arbeitsweise und Nachweise

- Aufgaben erst abhaken, wenn das jeweilige Abnahmekriterium erfüllt ist.
- Bei jeder erledigten Aufgabe Verantwortlichen, Datum, Commit und Testnachweis
  im Nachweisprotokoll unten eintragen.
- Konkrete Zugangsschlüssel, Passwörter und echte `.env`-Dateien nicht einchecken.
- Unbekannte Zielparameter nicht stillschweigend als erfüllt annehmen.
- Tests auf einer isolierten Installation durchführen; bestehende Daten und
  laufende Deployments erhalten.

## ID-Zuordnung und Prioritäten

Alle Aufgaben dieses Chats werden hier im O-XXX-Format geführt und im zentralen
[Entwicklungsbacklog](TODO.md) registriert. Bestehende
O-190–O-199 bleiben unverändert. Die früheren lokalen IDs wurden überführt:

| Bereich | Alte IDs | Verbindliche IDs |
|---|---|---|
| Umgebungsfragen | U01–U16 | O-200–O-215, in gleicher Reihenfolge |
| Deployment-Technik | T01–T12 | O-216–O-227, in gleicher Reihenfolge |
| Generalprobe und Versand | A01–A12 | O-228–O-239, in gleicher Reihenfolge |
| Chat-Ansichten | O-190–O-199 | Unverändert |
| Java-/XSLT-/Shell-/HTML-/JSP-Bestand | Neu | O-240–O-254 |

Checkboxen innerhalb eines Tickets sind Teilaufgaben derselben O-ID. Fragen sind
Klärungsaufgaben; sie gelten erst mit dokumentierter Antwort als erledigt. P1
bedeutet für den vereinbarten Analyseumfang vor der fachlichen Abnahme erforderlich,
P2 eine gezielte Erweiterung nach Bestandsaufnahme, P3 nachrangig. Bedingte Aufgaben
können mit dokumentierter Begründung als nicht anwendbar abgeschlossen werden.
Die Sprachanteile allein machen nicht jede Parser-Erweiterung zum Versandblocker.

## 1. Offene Fragen zur Zielumgebung

Die folgenden Punkte mit IT beziehungsweise Modellserver-Betreiber klären.

- [ ] **O-200 – Linux:** Distribution, Version und Architektur (`x86_64` oder
  `aarch64`) festhalten.
- [ ] **O-201 – Ressourcen:** CPU-Kerne, RAM und freien Speicher bestätigen;
  Speicherorte für Docker, Doctus-Daten, Installationsarchive und Backups festlegen.
  Der Platzbedarf umfasst ZIP, entpacktes Paket, importierte Images, Modelle und
  wachsende Betriebsdaten.
- [ ] **O-202 – Docker:** Installierte Docker-Engine-/Compose-Versionen festhalten;
  Rechte zum Image-Import, Containerstart und Einbinden von Host-Verzeichnissen
  bestätigen. Falls nicht vorhanden: Offline-Bereitstellung durch IT klären.
- [ ] **O-203 – Internet und Werkzeuge:** Klären, ob der Host vollständig ohne
  Internet arbeitet und wer fehlende Systempakete beziehungsweise Werkzeuge
  bereitstellt.
- [ ] **O-204 – Doctus-Adresse:** Feste IP beziehungsweise DNS-Namen für Browserzugriff
  und API festlegen.
- [ ] **O-205 – HTTPS und Ports:** Erlaubte Ports, vorhandenen Reverse-Proxy und
  Zertifikate klären. Festhalten, welche Komponenten gegebenenfalls zusätzlich
  mitgeliefert werden müssen.
- [ ] **O-206 – Chat:** Vollständige Basis-URL, Port, Chat-Pfad und exakte Qwen-32B-
  Modellkennung beschaffen. Streaming und Tool-Aufrufe für den vorgesehenen
  Agentenmodus bestätigen.
- [ ] **O-207 – Embeddings:** Vollständige Basis-URL, Port, Pfad und exakte Qwen-4B-
  Modellkennung beschaffen. Klären, ob 1024 Dimensionen standardmäßig geliefert
  werden oder ein expliziter Anfrageparameter nötig ist.
- [ ] **O-208 – Modellgrenzen:** Bedeutung der 8100 Tokens bestätigen, insbesondere
  maximale Eingabelänge; Batch-, Parallelitäts- und Zeitlimits sowie Chat-
  Kontextgrenze erfragen.
- [ ] **O-209 – Authentifizierung:** API-Key-Verfahren und gegebenenfalls
  Unternehmens-CA für beide Endpunkte klären. Geheimnisse separat übergeben.
- [ ] **O-210 – Netzwerk:** DNS, Routing, Firewall und gegebenenfalls Proxy klären.
  Erreichbarkeit muss auch aus den Doctus-Containern gegeben sein, nicht nur vom
  Linux-Host.
- [ ] **O-211 – Beispielanfragen:** Je eine funktionierende `curl`-Anfrage und
  Beispielantwort für Chat und Embeddings ohne echte Zugangsdaten beschaffen.
  Daraus die genaue OpenAI-kompatible Anfrageform bestätigen.
- [ ] **O-212 – Testumfang:** Festlegen, welche Quellen getestet werden: Upload,
  Git, Ordnerfreigabe, Confluence, Jira oder weitere. Adressen, Rechte,
  Authentifizierung und Zertifikate dafür bereitstellen.
- [ ] **O-213 – Transport:** Größenlimits und Archiv-/Skriptfilter auf Drive, Handy,
  SharePoint und Arbeitsclient prüfen. Verfügbaren Speicher und Möglichkeit zum
  Entpacken sowie zur Prüfsummenprüfung bestätigen.
- [ ] **O-214 – Betrieb:** Installationsverantwortlichen, Backup-Ziel und sichere
  Verwahrung von Verschlüsselungs- und Sitzungsschlüsseln festlegen.
- [ ] **O-215 – Lokale Option:** Festlegen, welche Modellgewichte neben dem Ollama-
  Image mitgeliefert werden und ob lokaler Ersatzbetrieb Teil der Abnahme ist.
  Eine GPU auf dem Doctus-Host ist für den geplanten Remote-Betrieb nicht nötig;
  lokale Inferenz muss separat dimensioniert werden.

### Zielparameter zum Ausfüllen

| Parameter | Vereinbarter Wert |
|---|---|
| Linux / Version / Architektur | Offen |
| CPU / RAM / freier Speicher | Offen |
| Docker / Compose | Offen |
| Datenverzeichnis / Backup-Ziel | Offen |
| Frontend-URL / API-URL | Offen |
| Reverse-Proxy / TLS / Unternehmens-CA | Offen |
| Chat-Basis-URL / Pfad / Modellkennung | Offen – Qwen 32B vorgeschrieben |
| Chat-Kontext / Streaming / Tool-Aufrufe | Offen |
| Embedding-Basis-URL / Pfad / Modellkennung | Offen – Qwen 4B, `/embeddings` |
| Embedding-Kontext / Dimensionen | 8100 / 1024 – API-Verhalten bestätigen |
| API-Authentifizierung | Offen – keine Schlüssel hier eintragen |
| Batch-/Parallelitäts-/Zeitlimits | Offen |
| Testquellen und Testdatensatz | Offen |
| Mitgelieferte lokale Modelle | Offen |
| Installations- und Betriebsverantwortlicher | Offen |

## 2. Technische Aufgaben

### O-216 – Blocker: Remote-Compose reparieren

- [ ] Abhängigkeit des `link-worker` vom deaktivierten lokalen Ollama entfernen.

Befund: Die Konfigurationsprüfung für Offline-Compose plus Remote-Overlay lieferte
`service "link-worker" depends on undefined service "ollama"`.

Quellen: [Remote-Overlay](../docker-compose.remote-inference.yml),
[Offline-Compose](../docker-compose.offline.yml).

Abnahme: Konfigurationsprüfung und Start des kompletten Remote-Stacks funktionieren
ohne gestarteten lokalen Ollama. Auch den normalen Stack mit Remote-Overlay prüfen.

### O-217 – Blocker: Remote-Erststart der KI-Konfiguration korrigieren

- [ ] Bootstrap an die unabhängigen, OpenAI-kompatiblen Remote-Profile anpassen.

Befund: `ensure_profiles()` erzeugt und aktiviert beim Erststart ein lokales
Chat-Profil mit `http://ollama:11434`. Die Anwendung überschreibt dadurch die
konfigurierte Remote-Chat-Adresse. Dies wurde isoliert mit den aktuellen Funktionen
reproduziert. Der Backend-Healthcheck kann anschließend scheitern; das Frontend
wartet auf ein gesundes Backend. Eine spätere UI-Umstellung ist daher kein
verlässlicher Erststartpfad.

Quellen: [KI-Einstellungen](../backend/services/ai_settings.py),
[Healthcheck](../backend/api/system.py), [Start](../backend/main.py).

Abnahme: Eine leere Datenbank startet direkt mit den vereinbarten Remote-Profilen.
Protokoll, URL, Pfad und Authentifizierung stimmen; Backend und Frontend werden
gesund. Bestehende Profile bleiben bei einem Neustart erhalten.

### O-218 – Pflicht: Konfiguration ohne Image-Neubau

- [ ] Chat und Embeddings unabhängig bei Installation und im Betrieb konfigurieren.

Bestehende Profile unterstützen bereits getrennte Einstellungen. Lieferkonfiguration,
Bootstrap und Dokumentation müssen diese konsistent abbilden. Ein bloßer Wechsel
von `OLLAMA_BASE_URL` reicht für OpenAI-kompatible Endpunkte nicht als Nachweis.

Abnahme: URL, Port, Pfad, Modellkennung, Schlüssel und relevante Modellparameter
lassen sich ohne Image-Neubau ändern. Indexierung und Retrieval verwenden dasselbe
aktive Embedding-Profil. Ein Embedding-Modellwechsel mit vorhandenen Daten wird
mit einem klaren Verfahren zur Neueinbettung dokumentiert.

### O-219 – Pflicht: Installer vollständig offline machen

- [ ] Schlüsselerzeugung ohne zusätzliche Downloads ermöglichen.
- [ ] Host-Werkzeuge dokumentieren und vor Installation prüfen.

Befund: Fehlt Python mit `cryptography` auf dem Host, versucht der Bootstrap
`python:3.11-slim` zu starten und `cryptography` per `pip` nachzuinstallieren.
Stattdessen kann beispielsweise das bereits gelieferte Backend-Image die
Schlüsselerzeugung übernehmen.

Quelle: [Environment-Bootstrap](../scripts/lib/env-bootstrap.sh).

Abnahme: Installation funktioniert ohne Internet und ohne Python-Paketinstallation
auf dem Host. Schlüssel werden individuell erzeugt und nicht versehentlich ersetzt.

### O-220 – Pflicht: Offline-Stack vervollständigen

- [ ] `parser-beat` für regelmäßige Quellensynchronisation ergänzen.
- [ ] Benötigte Ordner-Mounts und Feature-Konfiguration mitliefern und einbinden.
- [ ] Unterschiede der normalen und Offline-Konfiguration systematisch prüfen.

Befund: Der Offline-Stack enthält den Scheduler sowie die Ordnerfreigabe- und
Feature-Konfigurations-Mounts des normalen Stacks nicht.

Quellen: [Normaler Stack](../docker-compose.yml),
[Offline-Stack](../docker-compose.offline.yml).

Abnahme: Alle Dienste und Mounts für den vereinbarten Testumfang sind vorhanden.
Automatische Synchronisation funktioniert. Cloud-Provider sind für den vorgesehenen
On-Prem-Betrieb deaktiviert; Entwicklungsflags nicht ungeprüft übernehmen.

### O-221 – Pflicht: Modellannahmen und Downloads korrigieren

- [ ] Feste `bge-m3`-Annahmen aus Liefer- und Prüfablauf entfernen.
- [ ] Automatische Modell-Downloads in der Lieferkonfiguration ausschalten.
- [ ] Lokalen Modellumfang festlegen und mit Manifest dokumentieren.

Befund: `.env.example` setzt `EMBEDDING_AUTO_PULL=true`, obwohl die Offline-
Dokumentation einen anderen Eindruck vermittelt. Der Builder zieht immer `bge-m3`;
Chat ist standardmäßig mit `LLM_MODEL=disabled` deaktiviert. Image und Modellgewichte
sind unterschiedliche Lieferbestandteile.

Quellen: [Environment-Vorlage](../.env.example),
[Bundle-Builder](../scripts/build-offline-bundle.sh).

Abnahme: Remote-Qwen funktioniert ohne `bge-m3`; keinerlei automatische Modell-Pulls
im Zielbetrieb. Der lokale Lieferumfang und seine tatsächlich möglichen Funktionen
sind eindeutig dokumentiert.

### O-222 – Pflicht: Verbindliche Vorab- und Abschlussprüfung

- [ ] Architektur, Docker/Compose, Speicher, Werkzeuge, Konfiguration und benötigte
  Ports vor dem Start prüfen.
- [ ] Sichere Passwörter, Schlüssel und vom Arbeitsclient erreichbare URLs prüfen.
- [ ] Erfolg erst nach bestandenen Bereitschaftsprüfungen melden.

Befund: Der Installer warnt teilweise erst nach dem Start und bestätigt nicht
verbindlich die Einsatzbereitschaft des gesamten Stacks.

Quelle: [Offline-Installer](../scripts/install-offline.sh).

Abnahme: Ungültige Voraussetzungen führen zu verständlichen Fehlern und einem
Fehler-Exitcode. Eine Erfolgsmeldung bedeutet, dass alle erforderlichen Dienste
einsatzbereit sind. Zeitlimits berücksichtigen kalte Modellstarts.

### O-223 – Pflicht: Remote-Funktionstest für Qwen

- [ ] Vorhandenen Test auf konfigurierbare OpenAI-kompatible Endpunkte umstellen.
- [ ] Test aus den betroffenen Doctus-Containern ermöglichen.
- [ ] Chat, Embeddings, Dimensionen und gegebenenfalls Streaming/Tool-Aufrufe prüfen.

Befund: Das vorhandene Skript erwartet `bge-m3`, `/api/tags` und `/api/embed`,
benötigt Host-Python und testet weder Chat noch die Container-Netzverbindung.

Quelle: [Remote-Test](../scripts/test-remote-inference.sh).

Abnahme: Echte Anfragen mit den vereinbarten Modellkennungen funktionieren aus
Backend und Worker. Embeddings enthalten genau 1024 Dimensionen. Modellname,
Authentifizierung, Pfad, Batch-Verhalten und Zeitlimits werden sinnvoll geprüft.

### O-224 – Pflicht: Image-Export und Import absichern

- [ ] Fehler im Image-Export zuverlässig erkennen.
- [ ] Vollständigkeit und Nutzbarkeit der importierten Image-Referenzen prüfen.

Befund: `docker save | gzip` ist im aktuellen Shell-Skript nicht gegen einen
Fehler des ersten Pipeline-Befehls abgesichert. Prüfsummen können auch ein bereits
fehlerhaft erzeugtes Archiv unverändert bestätigen.

Quelle: [Bundle-Builder](../scripts/build-offline-bundle.sh).

Abnahme: Fehlerhafte Exporte brechen den Build ab. Auf einer leeren Docker-
Installation werden alle referenzierten Images korrekt geladen und ohne Registry-
Zugriff gestartet. Die Konfiguration verhindert unbeabsichtigte Pulls beim Start.

### O-225 – Pflicht: Lieferpaket und Transport

- [ ] Versioniertes ZIP64-Paket automatisch erzeugen.
- [ ] Äußere ZIP-Prüfsumme und innere Dateiprüfsummen bereitstellen.
- [ ] Image-/Modellmanifest, Konfigurationsvorlage, Installer, Prüfskripte und kurze
  deutsche Installationsanleitung mitliefern.
- [ ] Enthaltene Dateien auf Vollständigkeit und fehlende Geheimnisse prüfen.

Abnahme: Das Paket ist ohne Quellrepository installierbar. Version, Architektur,
Image-Referenzen und Modellumfang sind nachvollziehbar. Die Anleitung beschreibt
Entpacken, Konfigurieren, Installation, Prüfung, Diagnose und Wiederanlauf.
Keine Entwicklungsdatenbank, echten Zugangsdaten oder echte `.env` mitliefern.

Größenreferenz, keine aktuelle Freigabe: Das vorhandene Bundle
`dist/doctus-offline-bundle-t54-20260916` umfasst ungefähr 4,9 GiB (3,9 GiB Images,
1 GiB Modelle). Es enthält nicht alle aktuellen Remote-Dateien. Ein zusätzliches
Chat-Modell erhöht die Größe. ZIP ist hier primär Transportverpackung, da die
enthaltenen Archive bereits komprimiert sind.

### O-226 – Bedingt: Unternehmensnetz und Zertifikate

- [ ] Falls erforderlich, Unternehmens-CA in alle betroffenen Container einbinden.
- [ ] Proxy-Ausnahmen, interne DNS-Auflösung und Connector-Zugriffe prüfen.
- [ ] Tatsächlich wirksame Firewall-Regeln für veröffentlichte Docker-Ports prüfen.

Abnahme: Die vorgesehenen internen HTTPS-Dienste funktionieren mit aktiver
Zertifikatsprüfung. Nur die vereinbarten Verbindungen sind freigegeben.
Eine UFW-Regel allein ist kein Nachweis, dass veröffentlichte Docker-Ports passend
geschützt sind: [Docker: Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

### O-227 – Vor Nachlieferungen: Updates und Datenhaltung

- [ ] Versionswechsel bei vorhandener `.env` explizit behandeln.
- [ ] Stabile Datenpfade, Backup und Wiederherstellung dokumentieren und testen.

Befund: Der Installer erhält eine bestehende `.env` einschließlich `DOCTUS_VERSION`.
Dadurch können trotz neu geladener Images weiterhin die alten Tags gestartet werden.

Abnahme: Ein Update startet nachweislich die vorgesehene Version, erhält Daten und
Schlüssel und hat ein geprüftes Wiederherstellungsverfahren. Ein Wechsel des
Bundle-Verzeichnisses darf nicht versehentlich eine neue leere Datenablage erzeugen.

## 3. Generalprobe und Versandfreigabe

Die technischen Aufgaben allein sind kein Ersatz für diese Abnahme.

- [ ] **O-228:** Frische Linux-Testmaschine mit Zielarchitektur und vergleichbarer
  Docker-/Compose-Version vorbereiten. Keine vorhandenen Anwendungsimages,
  Datenbanken oder Modell-Caches voraussetzen.
- [ ] **O-229:** Externen Internetzugriff sperren; nur erforderliche interne
  Verbindungen erlauben. Installation ausschließlich aus dem fertigen ZIP.
- [ ] **O-230:** Separaten OpenAI-kompatiblen Modellserver verwenden, möglichst mit
  den vorgeschriebenen Qwen-Modellen und denselben Einstellungen. Falls nicht
  verfügbar, verbleibende Modell-/Infrastrukturrisiken ausdrücklich dokumentieren.
- [ ] **O-231:** Erststart, Migrationen, gesunde Dienste und Login von einem zweiten
  Rechner prüfen.
- [ ] **O-232:** Vereinbarte Testdaten importieren; Parsing, Embeddings, Suche und Chat
  einschließlich Quellenbezug prüfen. Graph-/Agentenfunktionen gemäß Testumfang
  prüfen, insbesondere benötigte Tool-Aufrufe.
- [ ] **O-233:** Automatische Quellensynchronisation und gegebenenfalls Ordnerquellen
  prüfen.
- [ ] **O-234:** Host-Neustart und kurzzeitigen Ausfall des Modellservers testen;
  Wiederanlauf und verständliche Fehlermeldungen nachweisen.
- [ ] **O-235:** Backup/Restore von Datenbank, Dateien und Schlüsseln erproben.
- [ ] **O-236:** Falls vereinbart, lokalen Ollama-Betrieb mit dem gelieferten
  Modellumfang prüfen. Chat- und Embedding-Umschaltung getrennt berücksichtigen;
  bei Modellwechsel keine unterschiedlichen Vektorräume vermischen.
- [ ] **O-237:** Den tatsächlichen Transportweg mit ähnlich großem Testarchiv
  durchlaufen, vollständig herunterladen, entpacken und Prüfsummen vergleichen.
- [ ] **O-238:** Exakt das abgenommene ZIP unverändert für den Versand festlegen;
  Hash, Version und Testprotokoll dokumentieren. Jede nachträgliche Paketänderung
  benötigt eine erneute angemessene Prüfung.
- [ ] **O-239:** Am Ziel äußere und innere Prüfsummen vergleichen und denselben
  grundlegenden Funktionstest wiederholen.

## 4. Bisheriger Prüfstand und Grenzen

- Laufender Entwicklungsstack: acht Dienste bei der Prüfung gesund.
- Elf vorhandene Installer-Tests bestanden; Shell-Syntax geprüft.
- Offline-Compose ohne Remote-Overlay bestand die Konfigurationsprüfung.
- Offline-Compose mit Remote-Overlay scheiterte reproduzierbar wie unter O-216.
- Remote-Chat-Adresse wurde bei isoliert ausgeführter Profilinitialisierung durch
  die lokale Adresse ersetzt, siehe O-217. Dies war kein vollständiger Erststarttest.
- Kein Nachweis einer frischen, internetlosen Installation des aktuellen Pakets.
- Kein Zugriff auf den tatsächlichen internen Qwen-Server und keine dortige
  Ende-zu-Ende-Abnahme.
- Keine Softwarekorrekturen oder Auslieferungen während der ursprünglichen Prüfung.

Referenzen: [Deployment](DEPLOYMENT.md), [Remote-Inferenz](REMOTE_INFERENCE.md),
[Betriebsgrenzen](OPERATIONS_LIMITS.md). Aussagen dieser Dokumente zum Offline-
Verhalten mit den Befunden dieser Liste abgleichen und bei Umsetzung aktualisieren.

## 5. Chat-Agent: Ansichten während der Arbeit öffnen

Ergänzung vom 18.09.2026 auf Nutzerwunsch. Die folgenden O-XXX-Aufgaben sind
Produktverbesserungen und keine zusätzlichen pauschalen Blocker für den ersten
On-Prem-Test. Die IDs sind im zentralen
[Entwicklungsbacklog](TODO.md#chat-agent-ansichten-während-der-arbeit)
registriert; die Detailplanung und Abnahme stehen hier. O-190 bis O-192 sind
inzwischen als geführte, explizit gestartete Tour umgesetzt.

### Ausgangslage und Reihenfolge

Der Agent bietet bereits `list_repo_files`, `view_repo_file`, `search_repo_code`,
`get_repo_entities` und `trace_call_flow` sowie angebundene MCP-Tools an.
`trace_call_flow` liefert einen indizierten Aufrufgraphen; O-195 bindet seine
validierten Kanten als einzelne Schritte in die geführte Tour ein. Der Nutzer
startet die Tour und die vorhandene Call-Graph-Ansicht hebt bei jedem Schritt die
erklärte Aufrufkante hervor.

Relevante Einstiegspunkte: [Agent](../backend/agent.py),
[Chat-Stream](../frontend/lib/chatStream.ts),
[Chat-Ansicht](../frontend/components/ChatView.tsx),
[Workspace](../frontend/app/page.tsx),
[Panel-Navigation](../frontend/lib/panelNavigation.ts),
[Panel-Synchronisation](PANEL_SYNCHRONISATION.md).

Empfohlene Reihenfolge: O-190/O-191 bilden die umgesetzte Grundlage. O-192 und
O-195 ergänzen Dokument- und Graphschritte. O-196 liefert die begrenzte,
lesende Änderungsfolgenanalyse; O-273 erweitert sie um Fachregeln, Fehlerhistorie,
Tests und Verantwortlichkeiten. O-193/O-194 ergänzen die Recherche; O-197/O-198 sind
nachrangig. O-199 begleitet die Umsetzung und schließt die Abnahme ab.
Toolnamen unten sind Vorschläge; bestehende Tools erweitern statt redundante
Lese- und Navigationswerkzeuge einzuführen.

### O-190 – P1: Gemeinsame Ansicht-Aktionen im laufenden Chat

- [x] Einen typisierten Mechanismus für agentengesteuerte Ansicht-Aktionen und
  dessen Einbindung in den Chat-Stream implementieren.

**Zweck:** Der Agent kann während seiner Recherche eine passende Ansicht öffnen
oder aktualisieren, bevor die abschließende Antwort vorliegt. Bestehende
Recherche-Tools dürfen dazu eine validierte Ansicht-Aktion liefern; ein eng
begrenztes `open_workspace_view` kann bereits aufgelöste Ziele erneut anzeigen.

**Umfang:** Erlaubte Ansichtstypen und strukturierte Zielparameter definieren
(Projekt, Quelle, Entity, Dokument/Chunk, Zeilen, Filter). Aktions-ID, Chat-/Turn-
Zuordnung und Status wie geöffnet, aktualisiert, abgelehnt oder kein Platz führen.
Aktionen aus erfolgreich validierten Tool-Ergebnissen ableiten, nicht aus freiem
Modelltext oder beliebigen HTML-/JavaScript-/URL-Anweisungen. Ziele serverseitig
gegen Nutzer-, Team- und Projektberechtigungen prüfen. Clientstatus darf dem Modell
nicht fälschlich als erfolgreiche Öffnung dargestellt werden.

**Abnahme:** Recherchewerkzeuge öffnen keine Ansichten und erzeugen keine
Einzelkarten im Chat. Nach einer Erklärung kann der Agent genau eine geführte
Code-Tour mit zwei bis sechs didaktisch geordneten Schritten anbieten. Erst der
Klick auf „Veranschaulichen“ öffnet den Editor und markiert die erste Stelle.
„Zurück“ und „Weiter“ wechseln kontrolliert zwischen den Stellen; nach Abschluss
kann dieselbe Tour aus der ursprünglichen Chatnachricht wiederholt werden.
Passende unfixierte Code-Panels werden aktualisiert, fixierte Panels bleiben
erhalten. Hintergrundchats und alte Events übernehmen nicht den aktuellen
Workspace.

**Umsetzungsstand:** `offer_code_walkthrough` prüft jede vorgeschlagene Datei
und Zeilenspanne serverseitig gegen das Repository und erzeugt anschließend eine
typisierte SSE-Aktion mit stabiler ID sowie Turn- und Projektbezug. Der Client
dedupliziert sie, schützt Sitzungswechsel und hält den aktuellen Schritt lokal in
der Chatkarte. Frühere Einzelaktionen aus `trace_call_flow` und
`view_repo_file` bleiben als gespeicherte Metadaten lesbar, werden aber nicht
mehr als Öffnungskarten dargestellt. Geöffnet, aktualisiert, kein Platz,
abgelehnt und alter Kontext werden weiterhin an der Assistentenantwort
persistiert.

### O-191 – P1: Codefundstelle im Editor zeigen

- [x] `view_repo_file` und Entity-Ergebnisse um gezielte Code-Navigation erweitern
  beziehungsweise `show_code_location` ergänzen.

**Nutzen:** Während der Agent eine Routine erklärt, sieht der Nutzer die konkrete
Funktion, COBOL-Section oder betroffene Zeile im vorhandenen Code-Panel.

**Parameter:** Projekt-/Quellen-ID, Entity-ID oder validierter relativer Dateipfad,
Start-/Endzeile, optional kurze Begründung. Vorhandene Datei- und Entity-Auflösung
wiederverwenden; keine frei gewählten Hostpfade akzeptieren.

**Abnahme:** Die richtige Datei öffnet sich, der relevante Bereich wird markiert
und gescrollt. Pfad-/Projektverwechslungen und Traversal werden abgefangen.
Fehlende oder veraltete Fundstellen führen zu verständlichen Ergebnissen. Die
Navigation bearbeitet keine Datei und verwendet bestehende Panel-Historie.

### O-192 – P1: Dokument und Belegstelle öffnen

- [x] Dokumentbelege als validierte Schritte der vorhandenen geführten Tour
  ergänzen.

**Nutzen:** Der Agent macht eine fachliche Aussage anhand der passenden PDF-Seite,
Dokumentpassage oder indexierten Confluence-/Jira-Fundstelle nachvollziehbar.

**Parameter:** Quellen-/Dokument-ID, Chunk- oder Beleg-ID; Seite beziehungsweise
Abschnitt nur soweit tatsächlich im Index vorhanden. Bestehende Citation-Auflösung
verwenden. Standardmäßig die interne Ansicht öffnen; externe Originalseiten als
bewussten Nutzerlink anbieten, nicht automatisch einen Browser-Tab öffnen.

**Abnahme:** Die angezeigte Passage stimmt mit dem zitierten Inhalt überein.
Fehlende Seitenkoordinaten werden als Textauszug behandelt, nicht erfunden. Auch
ohne Zugriff auf das externe Ursprungssystem bleiben vorhandene indexierte Belege
darstellbar. Nicht berechtigte Quellen werden weder angezeigt noch offengelegt.

**Umsetzungsstand:** `offer_source_walkthrough` akzeptiert ausschließlich
Dokument-Chunks, die für den aktuellen Turn bereits berechtigt abgerufen wurden.
Chunk-ID, Quellen-ID, Dateipfad, Seite, Abschnitt und Auszug werden serverseitig
aus dem Index übernommen. Der Tour-Schritt zeigt den Originalauszug im Chat,
öffnet die interne Dokumentansicht und springt bei PDF-Belegen auf die indexierte
Seite. Für Confluence/Jira bleibt der indexierte Auszug auch ohne erreichbares
Ursprungssystem intern darstellbar.

### O-193 – P2: Suchergebnisse als Ansicht öffnen

- [ ] `search_knowledge` mit Öffnung einer gefilterten Suchansicht anbinden;
  vorhandene Code-Suche bei Bedarf in denselben Mechanismus integrieren.

**Nutzen:** Bei Fragen wie „Wo wird Kundenstatus verarbeitet?“ können Nutzer die
Treffermenge sehen, während der Agent einzelne Treffer weiter untersucht.

**Parameter:** Suchtext, erlaubter Projekt-/Quellenbereich, vorhandene Suchart und
unterstützte Filter, begrenzte Trefferzahl. Bestehende Suchservices wiederverwenden.

**Abnahme:** Die Ansicht zeigt dieselbe Suche und denselben Berechtigungsbereich
wie das Werkzeug. Treffer navigieren zu Code oder Dokument. Kein Treffer, gekürzte
Treffermengen und Ladefehler sind sichtbar. Eine globale Suche erweitert nicht
ungefragt den für den Turn vereinbarten Projektkontext.

### O-194 – P2: Wissensgraph auf eine Frage fokussieren

- [ ] `show_graph_neighborhood` für die vorhandene Wissensgraph-Ansicht ergänzen.

**Nutzen:** Der Agent zeigt etwa die Beziehungen eines Programms zu Dokumenten,
Themen oder anderen Code-Entities als begrenzten Graph-Ausschnitt.

**Parameter:** Validierte Fokus-ID mit Knotentyp, erlaubte Beziehungstypen,
Richtung und begrenzte Tiefe/Knotenanzahl. Vorhandene Graph-API und deren Limits
verwenden. Gewählte Filter für den Nutzer sichtbar machen.

**Abnahme:** Der Fokus und die erklärten Beziehungen sind sichtbar. Große Bestände
werden nicht vollständig geladen. Bei expliziter Auswahl eines Beziehungstyps
blenden bestehende Standardfilter die angeforderte Beziehung nicht unbemerkt aus.
Beziehungsart, Herkunft und gegebenenfalls Konfidenz bleiben unterscheidbar;
semantische Ähnlichkeit wird nicht als gesicherter Funktionsaufruf dargestellt.

### O-195 – P1: Call-Graph als Schritt einer geführten Tour

- [x] Erledigt 20.09.2026: `trace_call_flow` als belegten Schritt in die
  wiederholbare O-190/O-191-Tour integrieren.

**Nutzen:** Bei einer Erklärung einer Aufrufkette kann der Agent anbieten, den
Nutzer Schritt für Schritt durch die konkreten Aufrufstellen mitzunehmen. Der
Nutzer startet und wiederholt die Tour selbst; Graphschritte aktualisieren die
vorhandene Call-Graph-Ansicht und heben die erläuterte Kante samt Zielknoten
hervor.

**Umfang:** Ein Graphschritt muss auf eine aufgelöste Kante aus einem erfolgreichen
`trace_call_flow` desselben Turns verweisen. Backend und Client prüfen die
Werkzeug-ID, Kante und Endpunkte; unaufgelöste oder erfundene Kanten werden nicht
als Tour angeboten. Code- und Graphschritte dürfen in einer Tour gemischt werden.
Die bestehende Hop- und Knotengrenze sowie die Kennzeichnung als indizierter,
statischer Aufrufgraph bleiben erhalten.

**Abnahme:** Kein zweites Call-Graph-System. Start, Weiter, Zurück und Wiederholen
führen jeweils die zugehörige Ansicht mit; Knotenklicks bleiben mit der
Codefundstelle verbunden. Zyklen und gekürzte Graphen bleiben erkennbar. Der
Graph suggeriert keinen tatsächlich ausgeführten Laufzeit-Trace.

### O-196 – P1 / Erledigt 20.09.2026: Änderungsfolgen untersuchen und anzeigen

- [x] `inspect_change_impact` zur lesenden Analyse einer Entity oder Datei ergänzen.

**Nutzen:** Bei „Was könnte eine Änderung an dieser Routine betreffen?“ werden
Aufrufer und belegte Abhängigkeiten in Graph-/Code-Ansichten sichtbar.

**Umfang:** Bestehende eingehende Aufrufbeziehungen und belegte Querverweise nutzen;
keine zusätzliche Analyseplattform voraussetzen. Richtung, Suchtiefe und Umfang
begrenzen. Sicher indizierte Beziehungen, heuristische Links und unbekannte
dynamische Aufrufe getrennt ausweisen.

**Abnahme:** Betroffene Fundstellen lassen sich öffnen. Unvollständige Indexierung
und dynamische Aufrufe werden als Grenzen angezeigt; keine Behauptung vollständiger
Auswirkungsanalyse. Das Tool führt weder Codeänderungen noch Reindexierung aus.
O-273 bleibt offen und ergänzt diese Basis um Dokumentation, Fehlerhistorie,
Tests und Verantwortlichkeiten sowie eine gemeinsame API.

### O-197 – P2: Verknüpfungen samt Belegen im Link-Manager prüfen

- [ ] `inspect_knowledge_link` für gefilterten Link-Manager und Belegnavigation
  ergänzen.

**Nutzen:** Auf „Warum ist dieses Dokument mit dem Programm verknüpft?“ sieht der
Nutzer den konkreten Link, Herkunft, Konfidenz, Prüfstatus und verfügbare Belege.

**Parameter:** Link-ID mit Linktyp oder validierte Quell-/Ziel-ID. Existierende
Entity-/Dokument-Navigation und Review-Darstellung wiederverwenden.

**Abnahme:** Agent und Nutzer sehen dieselbe Verknüpfung; Belege öffnen die
passenden Fundstellen. Fehlende Begründungen werden nicht erfunden. Das Werkzeug
bestätigt, verwirft oder erzeugt keine Links; solche Änderungen bleiben gesonderte
explizite Nutzeraktionen im bestehenden Review-Verfahren.

### O-198 – P3: Import- und Jobstatus im passenden Kontext öffnen

- [ ] `show_processing_status` zum lesenden Öffnen des Job Centers beziehungsweise
  der Quellenstatusansicht ergänzen.

**Nutzen:** Der Agent kann erklären, warum eine Quelle noch nicht in der Suche
erscheint, und parallel den aktuellen Verarbeitungsstand zeigen.

**Parameter:** Berechtigte Quellen-/Job-ID, optional Projektfilter. Aktuellen
Status, Fortschritt und bereits freigegebene Fehlermeldungen verwenden.

**Abnahme:** Laufende, fehlgeschlagene und abgeschlossene Jobs werden korrekt
angezeigt und aktualisiert. Keine Rohlogs oder Geheimnisse an das Modell geben.
Kein impliziter Neustart, Abbruch oder Neuimport durch dieses Lesewerkzeug.

### O-199 – P1: Gemeinsame Abnahme mit dem vorgeschriebenen Qwen-Modell

- [ ] Agentenwerkzeuge, Live-Ansichten und Panel-Regeln über den tatsächlichen
  OpenAI-kompatiblen Qwen-32B-Endpunkt abnehmen.

**Umfang:** Kleine eindeutige Tool-Schemas, nur im aktuellen Kontext verfügbare
Tools anbieten. Ungültige Argumente verständlich zurückmelden. Parallel eintreffende
Tool-Ergebnisse, Abbruch, Wiederverbindung, erneutes Öffnen eines gespeicherten
Chats und manuelle Panel-Navigation berücksichtigen. Gespeicherte Aktionen dürfen
beim Laden eines Chats nicht automatisch erneut ausgeführt werden.

**Abnahme:** Repräsentative Fragen zu Code, Dokumentbeleg, Suche und Aufrufgraph
öffnen während des Turns passende Ansichten. Die vorhandenen Antwort-/Tool-
Streamingpfade bleiben funktionsfähig, der Ziel-Endpunkt ist explizit getestet.
Berechtigungsfehler und nicht vorhandene Ziele offenbaren keine fremden Daten.
Fixierte Panels, Vier-Panel-Grenze, Hintergrundchat, mobile Bedienung und deaktivierte
Automatik sind durch gezielte Tests abgesichert. Ein Ansichtfehler lässt die
Chat-Antwort weiterlaufen; Werkzeugstatus und Nutzeranzeige behaupten keinen Erfolg.

## 6. Analyse des Java-/XSLT-/Shell-/HTML-/JSP-Bestands

### Codebefund vom 18.09.2026

| Bereich | Vorhanden | Grenze / offene Prüfung |
|---|---|---|
| Java | ANTLR-Strukturparser; Deklarationen, Methoden-/Feld-Chunks, Beziehungen, lokale und dateiübergreifende Auflösung, Diagnosen, partielle Lombok-Accessor-Synthese | Quelltextanalyse, kein vollständiger Compiler-/Laufzeit-Classpath; reale Java-Version, Module und Frameworks noch unbekannt |
| XSLT | Im Git-Pfad grundsätzlich als Text indexierbar | `.xsl`/`.xslt` fehlen in der Standard-Spracherkennung; kein XSLT-Strukturparser registriert |
| Shell | `.sh`, `.bash`, `.zsh`, `.fish` werden erkannt | Generisches Text-Chunking; kein Shell-Strukturparser in der Registry; Dateien ohne Endung werden so nicht als Shell erkannt |
| HTML / JSP | Im Git-Pfad grundsätzlich Text-Chunking | Keine eigenen Standard-Sprachlabels für HTML/JSP und keine Strukturparser; JSP ist eine Mischsprache |
| Quellcode-Anlieferung | Git-Connector führt die Strukturparser aus | Ordnerquelle erlaubt aktuell nur `.pdf/.docx/.doc/.txt/.md`; normaler Upload ebenfalls nur Dokumentformate, kein Java-Projekt-/ZIP-Import |
| Build-Kontext | Java-Modul- und Source-Set-Hinweis aus `src/<set>/java`-Pfad; statische Maven-POM-Entities für Projekte, Module, Dependencies und Plugins | Kein Maven-/Gradle-/Ant-Build und keine Auflösung externer Artefakte; alternative Layouts und Klassenpfadgrenzen prüfen |
| Java-Chunking | Symbolorientiert, standardmäßig ca. 1000 Zeichen | `_split_range` teilt nur an Zeilengrenzen; eine einzelne sehr lange Zeile kann die gewünschte Chunkgröße überschreiten |

Quellen: [Spracherkennung](../parser/core/language_detection.py),
[Parser-Registry](../parser/core/registry.py), [Java-Parser](../parser/java/parse.py),
[Java-Auflösung](../parser/java/resolution.py), [Module](../parser/java/modules.py),
[Java-Chunking](../parser/java/chunking.py), [Git-Import](../parser/connectors/git.py),
[Ordnerquelle](../parser/connectors/folder.py),
[Upload](../backend/api/knowledge_sources.py),
[Editor-Spracherkennung](../frontend/components/SplitPaneWorkspace.tsx).

Gezielte Prüfung: `tests/test_java_antlr_bridge.py`, `tests/test_java_relationships.py`
und `tests/test_java_golden.py` mit `.venv-parser/bin/python -m pytest` ausgeführt:
**22 Tests bestanden**, eine SQLAlchemy-Deprecation-Warnung. Das belegt vorhandene
Java-Bausteine, nicht die Vollständigkeit der Analyse des noch unbekannten Zielcodes.
Die bestehenden DB-/Ingestion-Integrationstests wurden bei dieser Ergänzung nicht
erneut ausgeführt. Parser-, Resolver- und UI-Erweiterungen unten sind noch offen.

### O-240 – P1 / Klärung: Repräsentativen Bestand und Analyseziele festlegen

- [ ] LOC, Datei-/Modulanzahl, größte Dateien, Encodings und Verzeichnisstruktur
  erfassen; Grundlage der Prozentangaben dokumentieren.
- [ ] Java-Versionen, Buildsysteme, vorhandene Frameworks/Server, Annotation-
  Prozessoren, generierte Quellen und benötigte externe Bibliotheken erfragen.
- [ ] XSLT-Version/Prozessor, Shell-Dialekte, JSP-/Taglib-Verwendung und relevante
  Konfigurationsformate anhand realer Dateien feststellen.
- [ ] Repräsentative, intern nutzbare Probe und konkrete Analysefragen mit
  erwarteten Fundstellen zusammenstellen. Kein interner Quellcode in das externe
  Lieferpaket oder öffentliche Testfixtures übernehmen.

**Abnahme:** Versionierter Bestandssteckbrief, erlaubter Testdatensatz und fachliche
Fragen liegen vor. Neben „Wo ist Methode X?“ mindestens einen tatsächlich vorhandenen
Java-zu-Ressourcen-/Transformations-/Web-Ablauf aufnehmen. Kleine Sprachanteile werden
nicht automatisch als fachlich unwichtig behandelt.

### O-241 – P1 / Import: Quellcode vollständig in die Offline-Analyse bringen

- [ ] Internes Git oder bereitgestellten Repository-Snapshot als verbindlichen
  Importweg festlegen und mit dem echten Berechtigungskonzept erproben.
- [ ] Falls kein Git-Zugriff möglich ist, einen Snapshot-/Repository-Import an
  dieselbe Strukturparser-Pipeline anbinden; normales Dokument-Upload-Verhalten
  nicht als gleichwertigen Codeimport ausgeben.
- [ ] Gegebenenfalls Submodule, LFS-Inhalte und außerhalb des Repositorys liegende
  Ressourcen berücksichtigen; Platzhalter oder fehlende Quellen melden.

**Abnahme:** Java und alle vier Begleitsprachen kommen aus dem vereinbarten Liefer-
format mit stabilen relativen Pfaden in die Analyse. Importmenge ist nachvollziehbar.
Bei Archivimport Pfadtraversal, Symlinks, Dateianzahl und Entpackgröße begrenzen.
Kein Maven-/Gradle-/Shell-Build und kein Start der fremden Anwendung zur Indexierung.
Snapshot-Inhalt und Revision eindeutig zuordnen; Änderungen/Löschungen sind erneut
importierbar. Bei funktionierendem internem Git keinen unnötigen zweiten Importweg bauen.

### O-242 – P1 / Abdeckung: Spracherkennung und Importbericht für den Mischbestand

- [x] XSLT, HTML und JSP einschließlich tatsächlich vorhandener Varianten
  (`.xsl`, `.xslt`, `.html`, `.htm`, `.jsp`, gegebenenfalls `.jspx/.jspf/.tag/.tagx`)
  eindeutig erkennen; die Labels bleiben bewusst unabhängig von einem
  Strukturparser. Die Inhaltsprüfung ergänzt die Endungserkennung bei
  endungslosen Dateien.
- [x] Shell ohne Endung anhand begrenzter Shebang-Prüfung erkennen, ohne Inhalt
  auszuführen. Konfigurierbare Endungszuordnungen erhalten.
- [x] Pro Sprache und Quelle melden: erkannt, strukturell geparst, nur als Text
  indexiert, fehlerhaft oder übersprungen, jeweils mit nachvollziehbarem Grund.
- [x] Encoding-, Größen- und Ausschlussregeln mit dem Bestand prüfen; Build-/Vendor-
  Kopien begrenzen, fachlich nötige Ressourcen und generierte Quellen nicht unbemerkt
  verlieren. JAR/WAR/Class-Dateien nicht als analysierten Java-Quellcode zählen.

**Umsetzung:** `SourceScanFile.language` und `SourceScanFile.encoding` bilden die
Klassifikation und das verwendete Codec ab. `parse_status` unterscheidet
`complete`, `text_fallback`, `partial`, `error` und `skipped`; `parse_error` enthält
die Begründung. Der Datei-Endpunkt liefert zusätzlich `scan_summary.by_language`,
`by_status` und `by_encoding`. Build-/IDE-Ausschlüsse werden nach dem Entfernen
alter Chunks als sichtbare `skipped`-Einträge protokolliert.

**Abnahme:** Inventar und importierte Dateien lassen sich abgleichen. Ein Sprachlabel
behauptet keine Strukturunterstützung. XML/Properties/Builddateien bleiben auffindbar,
auch wenn sie in den Prozentangaben nicht separat erscheinen. Fehlerhaft dekodierte
oder ausgeschlossene Inhalte sind sichtbar statt still verloren.

### O-243 – P1 / Java: Syntax- und Strukturabdeckung am Zielbestand absichern

**Technische Referenzabdeckung umgesetzt, Bestandsabnahme offen.** Der versionierte
Offline-Referenzsatz prüft Java-8-Überladungen und innere Klassen, Java-21-Records/
Pattern-Matching, Maven-Modul-/Source-Set-Metadaten, Annotationen und Lombok-
Accessor-Synthese samt abgeleiteter Kennzeichnung/Quellposition. Fehlerhafte Syntax
behält Originaldiagnose und Textfallback. Die Golden-Snapshots sichern das gesamte
Parserergebnis; `test_java_reference_corpus.py` hält die fachlich relevanten
Abnahmeinvarianten lesbar fest.

- [ ] Den Referenzsatz mit den tatsächlich benötigten Konstrukten und
  anonymisierten Regressionen aus O-240 erweitern.
- [ ] Bei auftretenden Fehlern Parser/Visitor gezielt korrigieren; Diagnosen,
  Textfallback und Originalzeilen erhalten. Java-8-/Java-21-Fixtures bleiben
  bewusst keine pauschale Freigabe aller Zwischenversionen.
- [x] Annotationen, innere/anonyme Klassen, Lambdas/Methodenreferenzen sowie
  die unterstützten Lombok-Accessor-Konstrukte sind durch Parser- und
  Referenztests abgedeckt.

**Abnahme:** Deklarationen, Signaturen und Quellenpositionen des vereinbarten
Referenzsatzes stimmen. Synthetische Methoden sind als abgeleitet markiert.
Nicht unterstützte Konstrukte sind dokumentiert. Strukturparser und benötigte
generierte ANTLR-Dateien funktionieren im endgültigen Offline-Runtime-Image.

### O-244 – P1 / Java: Module, Source-Sets und Build-Metadaten unterscheiden

- [x] **Erledigt 18.09.2026:** Maven-POMs statisch als Projekte, Module, Dependencies, Plugins und
  Properties erfassen; keine vollständige Buildausführung voraussetzen.
- [x] **Erledigt 18.09.2026:** Java-Entities um `module`, `source_set` und `source_kind` aus konventionellen Maven-
  Pfaden (`src/main/java`, `src/test/java`, `src/it/java` usw.) ergänzen.
- [ ] Gradle-/Ant-Metadaten nach demselben Vertrag ergänzen, sobald der
  Referenzbestand sie tatsächlich benötigt.
- [x] **Erledigt 18.09.2026:** Produktions-, Test- und generierte Quellen sowie Ressourcensets getrennt
  kennzeichnen. Doppelte vollqualifizierte Klassennamen zwischen Modulen prüfen.
- [x] **Erledigt 18.09.2026:** Abhängigkeiten nur soweit aus vorhandenen Dateien belegbar übernehmen;
  dynamische Buildskripte und fehlende externe Artefakte als unbekannt behandeln.

**Abnahme:** Gleichnamige Klassen aus getrennten Modulen werden nicht fälschlich
zusammengeführt. Suche und Graph können Module/Source-Sets unterscheiden.
Nichtstandard-Layouts sind konfigurierbar oder ausdrücklich als unaufgelöst markiert.
Analyse benötigt weder Build-Downloads noch Ausführung von Gradle-/Ant-Skripten.

### O-245 – P1 / Java: Aufrufauflösung und Unsicherheit fachlich prüfen

**Stand 18.09.2026:** JUnit-Referenzbestand `a468b7a42ec2cb3cd12af8b70e713011adbc7124`
mit `parser/audit_java_calls.py` geprüft: 1.739 Java-Dateien, 66 Syntaxdiagnosen,
70.727 Aufrufe; 16.595 statisch aufgelöst, 54.132 offen mit Begründung.
Korrigiert: falsche Selbstzuordnung von `super`, Besitzer statischer Wildcard-Imports
und fehlende Argumentanzahlprüfung bei globalen Aufrufen. Regression am echten
`JupiterTestEngine.java:86` und synthetische Referenztests ergänzt.
Vererbungsauflösung und Empfängertypen über Felder/lokale Variablen bleiben begrenzt;
O-245 ist damit noch keine vollständige fachliche Freigabe. Graph und Chat erhalten
Auflösungsgründe; aufgelöste Java-Aufrufe bezeichnen statische Deklarationen.

**Nachzug 18.09.2026:** Ein belegbarer Sonderfall ist nun zusätzlich abgedeckt:
`super.methode()` folgt ausschließlich expliziten `EXTENDS`-Kanten zur nächsten
passenden, nicht privaten Oberklassen-Deklaration (auch über eine kurze
Oberklassenkette). Paketprivate Methoden über Paketgrenzen sowie Default-Interface-
Dispatch werden weiterhin nicht geraten und bleiben mit einem Auflösungsgrund offen.
Die Regressionen stehen in `parser/tests/test_java_call_safety.py`.

- [ ] Gegen Referenzfälle prüfen: Überladung, Vererbung, Interfaces, statische
  Imports, Empfänger über Felder/lokale Variablen und dateiübergreifende Aufrufe.
- [ ] Nur nachgewiesene Resolver-Lücken gezielt schließen; Methodennamen allein
  nicht als hinreichenden Beleg für einen Aufruf verwenden.
- [ ] Gründe für externe, mehrdeutige oder dynamisch nicht auflösbare Ziele bis
  in Graph und Chat durchreichen.

**Abnahme:** Bekannte Aufrufe werden korrekt aufgelöst; uneindeutige Fälle bleiben
sichtbar uneindeutig. Interface-Aufrufe und mögliche Implementierungen werden nicht
als gesicherte konkrete Laufzeitroute ausgegeben. Reflexion/Proxies und fehlender
Classpath begrenzen die Aussage ausdrücklich. O-195/O-196 verwenden diese Grenzen.

### O-246 – P2 / Bedingt: Framework-Einstiegspunkte und Konfiguration verbinden

- [ ] Nach O-240 die wirklich vorkommenden Frameworks auswählen, etwa Servlet-
  Mappings, Spring-Konfiguration oder andere Container-/DI-Mechanismen.
- [ ] Vorhandene Annotationen und XML-/Properties-Konfiguration zu belegten
  Einstiegspunkten, Bean-/Service-Zuordnungen und Ressourcenreferenzen verbinden.

**Abnahme:** Ein repräsentativer konfigurierter Einstiegspunkt lässt sich bis zur
Java-Fundstelle verfolgen. Profilabhängige, dynamische und mehrdeutige Zuordnungen
werden getrennt dargestellt. Keine unbegründete Spring-Annahme aus dem Sprachmix,
keine Laufzeitvollständigkeit behaupten. Ohne entsprechende Frameworks begründet
als nicht anwendbar abschließen.

### O-247 – P2 / XSLT: Templates und Transformationsabhängigkeiten analysieren

- [x] **Erledigt 18.09.2026:** XSLT über die bestehende Parser-Registry anbinden: Stylesheet, Templates mit
  `name`/`match`/`mode`, Parameter/Variablen und Abschnitte sinnvoll erfassen.
- [x] **Erledigt 18.09.2026:** `xsl:include`, `xsl:import`, `xsl:call-template` und belegbare
  `xsl:apply-templates`-Beziehungen aufnehmen. Namespaces, relative Pfade und
  Import-Prioritäten im vereinbarten Versionsumfang berücksichtigen.
- [x] **Erledigt 18.09.2026:** XPath-Ausdrücke als Quellbelege erhalten; dynamische Dokument- und Template-
  Auswahl nicht zu vermeintlich eindeutigen Aufrufen vereinfachen.

**Abnahme:** Referenz-Stylesheets liefern suchbare Template-Chunks und navigierbare
Quellenpositionen. Includes, Modi, Zyklen und mehrdeutige Matches sind getestet.
Statische XML-Verarbeitung lädt keine externen Entities/DTDs oder URLs und führt
keine Transformation aus. Versionsgrenzen aus O-240 dokumentieren; unbekannte
Konstrukte fallen nachvollziehbar auf Textanalyse zurück.

### O-248 – P2 / Shell: Start- und Verarbeitungsskripte statisch erfassen

- [x] **Erledigt 18.09.2026:** Im vereinbarten POSIX-/Bash-nahen Dialekt Funktionen, `source`/`.`-Includes und nachvollziehbare
  Aufrufe von Skripten, Java-Entrypoints und Transformationswerkzeugen erfassen.
- [x] **Erledigt 18.09.2026:** Quoting, Zeilenfortsetzungen, Here-Documents und variable Pfade berücksichtigen;
  dynamische Expansionen als unbekannt erhalten.

**Abnahme:** Relevante Start-/Batchskripte sind suchbar und zeigen belegte Beziehungen
zu Java oder XSLT. Keine Shell-Ausführung, kein `eval`, kein Start eines referenzierten
Programms. Endungslose Skripte und Dateien mit Leerzeichen im Pfad sind geprüft.
Bei nicht unterstütztem Dialekt expliziter Textfallback statt falscher Aufrufgraph.

### O-249 – P2 / JSP und HTML: Ansichten, Includes und Serverbezüge sichtbar machen

- [x] **Erledigt 18.09.2026:** JSP-Mischinhalte unterscheiden: Direktiven, Includes, Taglibs, EL und Java-
  Scriptlets. HTML-Formularziele und statische Ressourcenbezüge erfassen, soweit
  sie im Bestand für Analysefragen gebraucht werden.
- [x] **Erledigt 18.09.2026:** Java-Fragmente mit Originalpositionen verbinden; JSP nicht als vollständige
  Java-Quelldatei behandeln. Eigene Tag-Dateien und Konfiguration bedingt einbeziehen.

**Abnahme:** Eine relevante JSP-/HTML-Seite ist als Quelltext navigierbar; belegte
Include-/Formular-/Controllerbezüge sind sichtbar, dynamische Ziele bleiben offen.
Keine Ausführung eingebetteter Skripte, keine ungeschützte Darstellung fremden HTML
und kein automatischer Abruf referenzierter Ressourcen im Browser. Kompilierte
Servlet-Details nicht ohne vorhandene Belege erfinden.

### O-250 – P2 / Sprachübergreifend: Java–XSLT–Shell–JSP-Ketten erklären

**Implementierungsstand 18.09.2026:** Gemeinsame Ressourcenauflösung verbindet
Shell-Java-Starts (bei belegter Signatur bis `main`), Class-Literal-Ressourcenaufrufe
aus Java, XSLT-Abhängigkeiten und JSP/HTML-Dateiverweise. Classpath-Ressourcen
werden im konventionellen Ressourcenverzeichnis desselben Moduls gesucht;
mehrdeutige, dynamische und verschwundene Ziele bleiben explizit offen.
Kanten tragen Herkunft und Originalzeile, sind im Graph standardmäßig sichtbar
und öffnen per Klick die Belegzeile. Chat-Abläufe erhalten Typ und Metadaten.
Servlet-Mappings, beliebige Classloader und nichtstandardisierte Ressourcenlayouts
werden weiterhin nicht erraten; fachliche Abnahme eines O-240-Ablaufs bleibt offen.

**Nachbesserung und Abnahme 18.09.2026:** Der neue parser-level Akzeptanztest
`parser/tests/test_o250_cross_language_acceptance.py` führt einen vollständigen
source-backed Beispielbestand durch den tatsächlichen Parser- und Resolverpfad:
Shell→Java-`main`, Java→XSLT/JSP, XSLT→XML und JSP→JSP. Er prüft zusätzlich
Belegdatei/-zeile, Beziehungstyp und dynamische Nichtauflösung; die bestehenden
Resolver-Regressionen decken zusätzlich verschwundene und mehrdeutige Ziele ab.
Die Persistenzabnahme über den GitConnector ist mit PostgreSQL ebenfalls grün:
`parser/tests/test_java_persistence.py` importiert den Mehrsprachen-Bestand,
persistiert Entities und Kanten, prüft Cross-Language-Auflösung, Belegmetadaten,
Mehrdeutigkeit sowie Reparse/Resume. Rollout und Reindex des Zielbestands bleiben
noch offen.

Validierung: 44 Parser-/Java-Tests, 30 Graph-UI-Tests, 8 Backend-Graph-/Chat-Tests
auf isolierter Datenbank sowie TypeScript-Prüfung erfolgreich. Eine bereits
veraltete Java-Golden-Datei an die vorhandenen Source-Set-Metadaten angepasst.
Die Schemaabweichung zwischen ORM und Testdatenbank ist mit Migration 0024
behoben; zusätzlich wurden fehlende Parser-ORM-Felder und ein Fehler in der
Java-Container-Persistenz korrigiert. Änderungen noch nicht deployed/reindexiert.

- [ ] Auf Basis von O-246–O-249 belegte Ressourcenbezüge verbinden, zum Beispiel
  Java-Transformation mit Stylesheet, Shell-Start mit Java-Klasse oder Servlet mit
  JSP. Nur tatsächlich vorhandene Mechanismen implementieren.
- [ ] Relative Pfade, Classpath-Ressourcen und doppelte Dateinamen im Modulkontext
  auflösen; Referenzherkunft, Position und Auflösungsstatus speichern.

**Abnahme:** Mindestens ein fachlich relevanter Ablauf aus O-240 ist über Sprach-
grenzen nachvollziehbar und jede Kante öffnet einen Beleg. Graph und Chat unterscheiden
`CALLS` von Ressourcen-/Include-/Konfigurationsbeziehungen. Nicht alles in den
Java-Aufrufgraph pressen; semantische Ähnlichkeit ersetzt keine belegte Abhängigkeit.

### O-251 – P1 / Qwen: Chunking, Kontextgrenzen und Retrieval abstimmen

- [ ] Java-Symbole und Text-/XML-/JSP-Chunks mit dem vorgeschriebenen Qwen-4B-
  Embedding-Endpunkt prüfen. 8100 Tokens nicht mit 8100 Zeichen gleichsetzen.
- [x] Einzelne sehr lange Java-/XML-/HTML-Zeilen sowie zusammengesetzte Anfrage-
  Präfixe berücksichtigen; begrenzte Chunks mit stabilen Quellenpositionen erzeugen.
- [ ] Prüfen, ob der Endpunkt Modellpräfixe, einen Dimensionsparameter oder andere
  dokumentierte Anfrageoptionen benötigt; nicht aus dem Modellnamen erraten.
- [x] Batch-/Parallelitätswerte nach dem Serverlimit konfigurieren, Timeout- und
  Überlängenfehler sichtbar machen; keine unbemerkte Trunkierung akzeptieren.

**Lokale Nachbesserung 18.09.2026:** Parser und API senden den Embedding-Kontext
explizit als `8100` und die Dimension als `1024`; diese Werte sind unabhängig vom
Chat-Kontext konfiguriert. Provider-Antworten werden auf Vektoranzahl und Dimension
geprüft, damit weder still verkürzte Batches noch ein gemischter Vektorraum in die
Persistenz gelangen. Migration `0025_o251_qwen_embedding_context` korrigiert das
alte systemseitige Qwen-Standardprofil von 8192 auf 8100; individuelle Profile
bleiben unverändert. Die lokalen Qwen-Vertragstests und die Langzeilen-/Boundary-
Regressionen sind grün. Überlange Eingaben werden vor dem Request anhand einer
konservativen UTF-8-Byte-Obergrenze abgewiesen; diese wird ausdrücklich nicht als
Zeichen- oder exakte Tokenzählung ausgegeben. Die Remote-Abnahme ist noch offen:
der in `.env`
konfigurierte Host lieferte am 18.09.2026 für `/api/embed`, `/embeddings`, `/` sowie
`/api/tags` und `/v1/models` HTTP 404. Modellkennung, Basis-URL und Pfad müssen dort
noch bestätigt werden; ein Pfad wird nicht aus dem Modellnamen erraten.

**Abnahme:** Alle erfolgreichen Embeddings haben 1024 Dimensionen. Deutsche
Fachfragen und exakte Java-/XSLT-Bezeichner finden erwartete Stellen, auch in den
kleinen Sprachanteilen. Gemessene Requests halten Eingabegrenzen ein. API, Worker
und Retrieval verwenden identisches Modell und identische Vorverarbeitung.

### O-252 – P1 / Datenkonsistenz: Änderungen und Reindexierung im Mischbestand

- [ ] Bestehende Java-Inkrementaltests auf relevante Änderungen, Umbenennungen,
  Löschungen und unveränderte Aufrufer ausweiten; neue Parser analog integrieren.
- [ ] Parser-/Profil-/Modul- und Ressourcenänderungen im Fingerprint beziehungsweise
  Abhängigkeitsmodell berücksichtigen. XSLT-Include-Änderungen dürfen abhängige
  Beziehungen nicht unbemerkt veralten lassen.
- [ ] Modellwechsel als kontrollierte vollständige Neueinbettung behandeln.

**Abnahme:** Nach erneutem Import keine doppelten oder verwaisten Entities/Kanten;
Löschungen und verschobene Ziele korrekt, unveränderte Daten sinnvoll wiederverwendet.
Abbruch und Fortsetzung funktionieren ohne Mischbestand unterschiedlicher Embedding-
Modelle. Vorhandene Java-Persistenz-/T5.1-Tests auf isolierter Datenbank ausführen.

### O-253 – P1 / UI und Agent: Mischsprachen korrekt anzeigen und belegen

- [ ] Backend-Sprachlabels, Editor-Spracherkennung, Entitytypen und Quellen-
  Navigation aufeinander abstimmen; XSLT/JSP/Shell nicht als COBOL behandeln.
- [ ] Vorhandene Agenten-Recherche für Java und die Begleitsprachen prüfen.
  O-191–O-197 um passende Beispiele und Ziele für diesen Bestand ergänzen.
- [ ] Unterstützungsniveau in Analysebericht, Graph und Antwort unterscheiden:
  strukturell erkannt, Textfallback, heuristisch verbunden oder unbekannt.

**Abnahme:** Fundstellen öffnen richtige Dateien und Originalzeilen. Normale
Zitatnavigation funktioniert auch ohne die optionalen neuen Live-Ansicht-Tools.
Der Agent erläutert Java-Symbole und Transformationsbezüge anhand von Belegen,
behauptet aus Textindexierung aber keine vollständigen Aufrufgraphen. Die fünf
Sprachen sind in einer kleinen Ende-zu-Ende-Probe berücksichtigt.

### O-254 – P1 / Freigabe: Qualitäts- und Lastprobe des tatsächlichen Bestands

- [ ] Auf Basis von O-240 messbare Abnahmekriterien mit dem Betreiber festlegen:
  Dateiabdeckung, tolerierte Parserfehler, belegte Referenzantworten, benötigte
  Beziehungsauflösung sowie akzeptable Import-/Antwortzeiten.
- [ ] Repräsentative Teilmenge und anschließend Zielumfang auf geeigneter Hardware
  mit Remote-Qwen prüfen; CPU/RAM, Speicher, Embedding-Durchsatz und Graphumfang
  messen. Sprachprozente sind keine Hardwaredimensionierung.
- [ ] Eine Regression für jede kleine Begleitsprache und für mindestens eine reale
  sprachübergreifende Analysefrage aufnehmen; 94 % Java darf den Rest nicht aus
  der Qualitätsbewertung verdrängen.

**Abnahme:** Ergebnisprotokoll mit Datensatzrevision, Doctus-Version, Modellkennungen,
Ressourcen und verbleibenden Analysegrenzen liegt vor. Parallel nutzbarer Chat während
Import und große Graph-/Suchergebnisse bleiben innerhalb vereinbarter Grenzen.
Zuerst Pilotumfang freigeben, weitergehende statische Analyse nur bei nachgewiesener
Abdeckung zusagen. Offline-Generalprobe O-228–O-239 mit diesem Profil durchführen.

### O-255 – P1 / Parser: Maven-Dependencies mit Classifier/Type kollisionsfrei erfassen

- [ ] In `parser/maven/parse.py` den `qualified_name` für `maven_dependency`-Entities
  erweitern, sodass `<classifier>` (z. B. `javadoc`, `tests`) und abweichende `<type>`-Werte
  (z. B. `test-jar`) in die Koordinate einfließen (`...::dependency:groupId:artifactId[:type][:classifier]`).
- [ ] Robuster Fallback: Falls eine POM mehrfach identische Abhängigkeitselemente enthält,
  einen deterministischen Zähler (`#2`, `#3` ...) anfügen, um `UniqueViolation`-Abbrüche
  auf `uq_code_entities_source_variant_file_qname` sicher auszuschließen.
- [ ] Regressionstests in `parser/tests/test_maven_parser.py` und `parser/tests/test_java_persistence.py`
  für mehrfache Abhängigkeiten mit und ohne Classifier ergänzen.
- [ ] Nach Deployment betroffene Dateien im Syncope-Bestand reindizieren und fehlerfreien Status verifizieren:
  `core/rest-cxf/pom.xml`, `ext/camel/rest-cxf/pom.xml`, `ext/flowable/rest-cxf/pom.xml`,
  `ext/oidcclient/rest-cxf/pom.xml`, `ext/saml2sp/rest-cxf/pom.xml`, `ext/scimv2/rest-cxf/pom.xml`.

**Abnahme:** POMs mit mehrfach deklarierten Abhängigkeiten (z. B. Standard + Javadoc/Test-Jar)
werden ohne Datenbankfehler indiziert; alle Abhängigkeiten bleiben als eigene Entities auffindbar.

### O-256 – P1 / Ingest: ISO-8859-1-Fallback für Java-.properties und Resource-Bundles

- [ ] In `parser/connectors/git.py` und `parser/core/source_decoder.py` für `.properties`-Dateien
  (und Resource-Bundles) einen automatischen Fallback auf `ISO-8859-1` (den historischen Standard
  für `java.util.Properties`) implementieren, wenn kein Profil vorgegeben ist und striktes UTF-8
  fehlschlägt.
- [ ] Nach erfolgreicher ISO-8859-1-Dekodierung die bestehende `looks_like_text`-Prüfung
  anwenden, sodass echte Binärdateien weiterhin zuverlässig abgelehnt werden.
- [ ] Regressionstests in `parser/tests/test_source_decoder.py` und `parser/tests/test_git_connector.py`
  für ISO-8859-1-kodierte Umlaute/Akzente (z. B. `\xe9` in französischen/deutschen Bundles) ergänzen.
- [ ] Nach Deployment die 87 im Syncope-Import übersprungenen `.properties`-Dateien
  reindizieren und vollständigen Textindex verifizieren.

**Abnahme:** Lokalisierte Java-Properties-Dateien in ISO-8859-1 werden ohne Dekodierungsfehler
als Text indexiert und gechunkt; Sonderzeichen und Umlaute bleiben im Volltext suchbar.

### O-257 – P1 / Jobs: Verwaiste und doppelte LinkBuilder-Runs im JobCenter bereinigen und Queue-Deduplikation absichern

- [x] In `backend/api/jobs.py` und `backend/api/knowledge_links.py` Deduplikation für
  `knowledge_links`-Runs implementieren: Ist für ein Projekt / einen Scope bereits ein Run im
  Status `pending` oder `running` vorhanden, keinen zweiten Datensatz anlegen, sondern den
  bestehenden Run zurückmelden. Projektzeilen werden beim Enqueue gesperrt; erneutes Starten,
  Wiederaufnehmen und `/knowledge-links/compute` verwenden dieselbe Scope-Deduplikation.
- [x] Verwaiste Runs bereinigen: Wenn das zugehörige Projekt gelöscht wurde (`project_id IS NULL`
  und Zielprojekt im `scope_json` existiert nicht mehr), den Run auf `cancelled` setzen,
  damit er nicht dauerhaft als aktiver Job im JobCenter ("In Warteschlange") verharrt. Die
  Job-Center- und Run-History-Abfragen führen diese Bereinigung aus; doppelte aktive Runs werden
  beendet und ihre Celery-Tasks widerrufen, der älteste Run bleibt erhalten. Bereits widerrufene
  oder anderweitig terminale Runs startet der Parser-Worker nicht mehr.
- [x] Stuck-State-Erkennung: Ein aktiver Run ohne `celery_task_id` wird nach 120 Sekunden als
  `failed` markiert; ein `pending`-Run mit Task-ID nach 30 Minuten. Gespeicherte Celery-Tasks
  werden widerrufen. Fehlertexte und `finished_at` bleiben im JobCenter sichtbar, und
  fehlgeschlagene Runs können erneut gestartet werden.
- [x] Datenbank geprüft: Die beiden verwaisten Alt-Einträge (Run-IDs 82 und 87 aus gelöschten
  Testprojekten 573 und 662) stehen bereits auf `cancelled`.
- [x] Regressionstests in `backend/tests/test_jobs.py` und `backend/tests/test_knowledge_links.py`
  ergänzen; `parser/tests/test_cross_link_builder_cancelled.py` prüft den Worker-Abbruch. O-258
  wird in `backend/tests/test_inference_admission.py` ohne Modellaufruf geprüft.

**Abnahme:** Das JobCenter zeigt pro Scope maximal einen aktiven Wissens-Verknüpfungs-Job an;
gelöschte Testprojekte hinterlassen keine endlosen Geister-Jobs in der Warteschlange.

### Empfohlene Umsetzung für diesen Bestand

1. O-200–O-215 und O-240/O-241 klären: Zielhost, Qwen-Endpunkte, Quellcodezugang,
   reale Versionen und erwartete Analysefragen.
2. Deployment-Blocker O-216/O-217 und Offline-Pflichtaufgaben beheben; parallel im
   Arbeitsablauf O-242–O-245, O-251–O-253 für verlässliche Java-/Textanalyse abarbeiten.
3. O-246–O-250 anhand der fachlichen Referenzfragen priorisieren. Für reine Suche
   kann ehrlicher Textfallback zunächst reichen; für zugesagte Transformations-/
   Web-Abläufe sind die dazu nötigen Strukturbeziehungen vor Abnahme erforderlich.
4. O-254 mit den Offline-Abnahmen O-228–O-239 abschließen. O-190–O-199 bleiben
   optionale Bedienverbesserungen, soweit sie nicht ausdrücklich Teil des Piloten sind.

## 7. Nachweisprotokoll

| Aufgabe | Verantwortlich | Datum | Commit / Paketversion | Prüfung / Ergebnis / verbleibende Einschränkungen |
|---|---|---|---|---|
| Noch keine Umsetzung dokumentiert | – | – | – | – |

Versandfreigabe: **offen**. Verantwortlicher: **offen**.
Freigegebener ZIP-Dateiname und SHA-256: **offen**.
