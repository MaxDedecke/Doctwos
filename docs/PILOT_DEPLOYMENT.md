# Interner Java/Maven-Pilot: GitLab, Issues und Confluence

## Lieferpaket bauen

```sh
./scripts/build-offline-bundle.sh pilot-20261102 --remote-inference
```

Der Remote-Modus liefert API, Parser (inklusive Scheduler/Link-Worker), Frontend, PostgreSQL und Valkey, aber keine Ollama-Images oder Modellgewichte. Ohne `--remote-inference` werden lokales Ollama und die konfigurierten Modelle mitgeliefert. Der Builder setzt keine laufenden Dienste neu auf.

Das Verzeichnis `dist/doctus-offline-bundle-<version>` als ZIP oder tar übertragen. Keine echte `.env`, Entwicklungsdatenbank oder Zugangsdaten hinzufügen. Enthalten sind Prüfsummen, Build-/Modell-/Imagemanifest, Feature-Konfiguration, Installer sowie Confluence-/Inferenz-Prüfskripte. Die Basisimages erhalten versionierte lokale Namen; das Imagemanifest hält ihre gepinnten Upstream-Referenzen fest. So ist der Start nach `docker load` nicht von erhalten gebliebenen Registry-Digest-Metadaten abhängig.

## Zielhost vorbereiten

Linux x86_64 ist der Standard-Build. Docker Engine und Compose mit `--wait`/`--pull never` müssen vorhanden sein. Für andere Architekturen bereits auf der Build-Maschine `DOCKER_DEFAULT_PLATFORM` setzen. Genug Speicher für Archiv, entpackte Images, Datenbank und Repository-Spiegel einplanen.

Im entpackten Paket `.env.example` nach `.env` kopieren. `POSTGRES_PASSWORD` durch einen eigenen Wert ersetzen. Nicht leere vorhandene Schlüssel bei Updates erhalten. Fehlende `MASTER_ENCRYPTION_KEY`, `SESSION_SECRET_KEY` und `DEPLOYER_TOKEN` werden beim Installieren aus dem bereits geladenen Backend-Image beziehungsweise OpenSSL erzeugt; dafür sind weder Host-Python noch Internet nötig.

Adressen und Modelle konfigurieren, Beispiel für zwei interne OpenAI-kompatible Server:

```dotenv
API_URL=https://doctus.intern/api
FRONTEND_URL=https://doctus.intern
LLM_PROVIDER=vllm
LLM_BASE_URL=http://chatserver.intern:8000/v1
LLM_MODEL=<exakte Modellkennung>
LLM_API_KEY=
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=http://embeddingserver.intern:8000/v1
OLLAMA_EMBED_MODEL=<exakte Embedding-Modellkennung>
EMBEDDING_API_KEY=
EMBEDDING_AUTO_PULL=false
```

### Modellserver als Container auf demselben Host (OpenAI-Format, API-Key)

`localhost` ist in den Doctus-Containern der jeweilige Container selbst; `http://localhost:<port>/v1` erreicht den Modellserver deshalb nicht. Zwei Wege:

1. **Port auf allen Schnittstellen veröffentlicht** (`-p 8000:8000`, nicht `-p 127.0.0.1:8000:8000`): `LLM_BASE_URL=http://host.docker.internal:8000/v1`. Das Remote-Overlay (`docker-compose.remote-inference.yml`) trägt `host.docker.internal` für API, Parser und Link-Worker ein. Eine Host-Firewall muss Verbindungen aus dem Docker-Bridge-Netz auf diesen Port zulassen.
2. **Port nur an 127.0.0.1 gebunden:** Den Modellcontainer ins Doctus-Netz hängen (`docker network connect doctus_default <modellcontainer>`) und `LLM_BASE_URL=http://<modellcontainer>:<interner port>/v1` setzen. Nach einer Neuanlage des Modellcontainers die Verbindung wiederholen.

```dotenv
LLM_PROVIDER=vllm            # jeder selbst betriebene OpenAI-kompatible Server; llamacpp für llama-server
LLM_BASE_URL=http://host.docker.internal:8000/v1
LLM_MODEL=<exakte Modellkennung des Servers, z. B. qwen3-coder:30b>
LLM_API_KEY=<Schlüssel>      # wird als Bearer-Token gesendet
OLLAMA_NUM_CTX=32768         # Kontextlänge des Servers, bemisst das Beweispaket; später im Profil änderbar
```

Ein solches Profil ist „Remote“, nicht „Cloud“; eine Cloud-Freigabe ist nicht nötig. Der Server muss **Tool-Aufrufe** im OpenAI-Format liefern, sonst arbeitet der Chat-Agent nicht. Qwen3-Coder unter vLLM: `--enable-auto-tool-choice --tool-call-parser qwen3_coder`; llama.cpp: `--jinja`; Ollama unterstützt das ohne Zusatz. Ein vorgeschaltetes Gateway muss `tools` und `tool_calls` unverändert durchreichen. `./test-remote-inference.sh` prüft Chat, einen erzwungenen Tool-Aufruf und das Embedding; Einstellungen > KI > Profil testen prüft dasselbe am angelegten Profil. Embeddings (bge-m3, 1024 Dimensionen) brauchen einen eigenen Endpunkt, wenn der Modellserver keine liefert.

Die URLs müssen zur tatsächlichen Reverse-Proxy-Konfiguration passen. Chat und Embeddings dürfen verschiedene Server/Schlüssel verwenden. Ein neues Embedding-Profil gilt nur für neue Projekte; bestehende Projekte wechseln ihr Modell einzeln unter Einstellungen > Projekte > Embedding-Modell (neue Vektoren entstehen neben den alten, Umschalten und Rücknahme in einem Schritt, siehe `docs/ENTSCHEIDUNGEN.md` E-20). Modell und Dimension eines bereits genutzten Profils lassen sich nicht ändern.

Für interne HTTPS-Zertifikate ein PEM-Bundle bereitstellen (bei Bedarf Unternehmens- und öffentliche Root-CAs zusammen):

```dotenv
CUSTOM_CA_FILE=/absoluter/pfad/unternehmen-ca.pem
GIT_SSL_CAINFO=/certs/custom-ca.pem
SSL_CERT_FILE=/certs/custom-ca.pem
```

`CUSTOM_CA_FILE` wird für Web-Connectoren eingebunden; Git und die Inferenz-Clients erhalten die beiden weiteren Einstellungen. Kein pauschales Abschalten der TLS-Prüfung erforderlich.

Installation:

```sh
./install-offline.sh --remote-inference
./test-remote-inference.sh
```

Bei eigenen Modellpfaden/Modellen können dem Prüfskript `--chat-url`, `--chat-model`, `--chat-provider`, `--embedding-url`, `--embedding-model`, `--embedding-provider` und `--ca` übergeben werden. Das Skript läuft im geladenen Backend-Image und prüft echte Chat- und Embedding-Antworten. Zugangsschlüssel stammen aus der Container-Umgebung.

Bei Updates wählt der Installer die Version des gelieferten Pakets, erhält Kundenkonfiguration und Schlüssel und wartet auf gesunde Dienste. Zuvor Datenbank, Repositories und `.env` sichern. Migrationen können einen Datenbank-Restore statt eines bloßen Image-Downgrades erfordern.

## Quellen anlegen

### GitLab-Code

Einstellungen > Quellen > Git > GitLab. Die eigene Instanz einschließlich etwaigem Kontextpfad als **GitLab Server URL** angeben. Repository und Branch wählen. Der Token benötigt Leserechte auf das Repository; ohne Benutzernamen verwendet der Assistent `oauth2` für HTTPS-Token-Authentifizierung. Projektpfade mit Untergruppen werden unterstützt, Listen werden paginiert.

### GitLab Issues mit Kommentaren

Einstellungen > Quellen > **GitLab Issues**. Server-URL und Read-API-Token angeben. Unter Projekte explizite numerische Projekt-IDs oder Pfade wie `gruppe/untergruppe/projekt`, durch Komma getrennt, eintragen. Keine instanzweite `ALL`-Auswahl.

Jeder Lauf liest offene und geschlossene Issues sowie sämtliche Seiten menschlicher Kommentare neu ein. Das erfasst auch geänderte/gelöschte Kommentare, wenn GitLab den Issue-Zeitstempel nicht aktualisiert. Titel, Beschreibung, Status, Labels, Kommentarautor/-datum und Original-URL werden indexiert. Stabile Schlüssel verwenden numerische Projekt-ID und Issue-IID. Unveränderte Chunks behalten über den bestehenden Reindex-Pfad ihre Links/Embeddings.

Vertrauliche Issues und interne/vertrauliche Kommentare werden ausgeschlossen. Importierte Inhalte sind für berechtigte Mitglieder des Doctwos-Projekts sichtbar; es gibt keine benutzerweise Spiegelung der GitLab-ACL. Ein vollständig erfolgreicher Scan entfernt gelöschte oder inzwischen vertrauliche Issues. Scheitert ein API-/Kommentarabruf, wird kein Löschabgleich durchgeführt. Die Webansicht zeigt den indexierten Tickettext einschließlich Kommentaren; ein Live-Adapter ist nicht erforderlich.

### Confluence Server/Data Center

Einstellungen > Quellen > Confluence. Instanz-URL einschließlich Kontextpfad, Space-Auswahl und Servicezugang angeben. PAT ohne Benutzername, Basic Auth mit Benutzername plus Passwort/Token. Kommentare bei Bedarf aktivieren. Lesebeschränkte Seiten und Unterseiten bleiben standardmäßig ausgeschlossen.

Vorabprüfung aus dem Paket:

```sh
docker compose run --rm --no-deps --entrypoint python \
  -v "$PWD:/pilot:ro" backend-api /pilot/check_confluence.py \
  --url https://confluence.intern/confluence --token '<PAT>' --space DOCS --ca /certs/custom-ca.pem
```

Token sicher eingeben und keine Befehls-/Diagnoseausgaben mit Zugangsdaten weitergeben. Nach der Einrichtung je eine Seite, ein Issue einschließlich Kommentar und eine Java-Fundstelle in Suche und Webansicht prüfen.

## Lokale Freigabe und verbleibende Zielprüfung

Die lokalen Testfälle prüfen Parsing, Import, Pagination, Kommentaränderungen, Löschungen, Ausschluss vertraulicher Inhalte, unabhängige Inferenz-Endpunkte und frische Installation. Ein simulierter Modellserver bestätigt das Protokoll, nicht die fachliche Qualität des Kundenmodells. Im Firmennetz bleiben DNS/Routing, CA, tatsächliche Token-Rechte, Serverversionen, reale Maven-Profile und fachliche Antwortqualität abzunehmen.
