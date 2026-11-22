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

1. **Port auf allen Schnittstellen veröffentlicht** (`-p 8000:8000`, nicht `-p 127.0.0.1:8000:8000`): `LLM_BASE_URL=http://host.docker.internal:8000/v1`. Die Compose-Dateien tragen `host.docker.internal` für API, Parser und Link-Worker ein, mit und ohne `--remote-inference`. Eine Host-Firewall muss Verbindungen aus dem Docker-Bridge-Netz auf diesen Port zulassen.
2. **Port nur an 127.0.0.1 gebunden:** Den Modellcontainer ins Doctus-Netz hängen (`docker network connect doctus_default <modellcontainer>`) und `LLM_BASE_URL=http://<modellcontainer>:<interner port>/v1` setzen. Nach einer Neuanlage des Modellcontainers die Verbindung wiederholen.

```dotenv
LLM_PROVIDER=vllm            # jeder selbst betriebene OpenAI-kompatible Server; llamacpp für llama-server
LLM_BASE_URL=http://host.docker.internal:8000/v1
LLM_MODEL=<exakte Modellkennung des Servers, z. B. qwen3-coder:30b>
LLM_API_KEY=<Schlüssel>      # wird als Bearer-Token gesendet
OLLAMA_NUM_CTX=32768         # Kontextlänge des Servers, bemisst das Beweispaket; später im Profil änderbar
```

Ein solches Profil ist „Remote“, nicht „Cloud“; eine Cloud-Freigabe ist nicht nötig. Der Server muss **Tool-Aufrufe** im OpenAI-Format liefern, sonst arbeitet der Chat-Agent nicht. Qwen3-Coder unter vLLM: `--enable-auto-tool-choice --tool-call-parser qwen3_coder`; llama.cpp: `--jinja`; Ollama unterstützt das ohne Zusatz. Ein vorgeschaltetes Gateway muss `tools` und `tool_calls` unverändert durchreichen. `./test-remote-inference.sh` prüft Chat, einen erzwungenen Tool-Aufruf in der gestreamten Form des Chats und das Embedding; Einstellungen > KI > Profil testen prüft am angelegten Profil Erreichbarkeit und Modell, bei vLLM und llama.cpp auch einen ungestreamten Tool-Aufruf. Embeddings (bge-m3, 1024 Dimensionen) brauchen einen eigenen Endpunkt, wenn der Modellserver keine liefert.

### Beispiel: Ollama mit Qwen3-Coder und bge-m3 plus Firmen-LLM im OpenAI-Format

Unter Einstellungen > KI entstehen dafür zwei KI-Profile und ein Embedding-Profil:

| Profil | Art | Einstellungen |
|---|---|---|
| Chat „Qwen3-Coder 30B“ | Lokal, wenn es das mitgelieferte Ollama (`http://ollama:11434`) ist; sonst Remote mit Protokoll Ollama und `http://host.docker.internal:11434` | Modell `qwen3-coder:30b`; unter Erweitert LLM-Kontext `32768` (Vorgabe 8192) |
| Embedding „bge-m3“ | Embedding-Profil, kein KI-Profil | Ollama, Modell `bge-m3`, 1024 Dimensionen; gilt für neue Projekte, unabhängig vom aktiven Chat-Profil |
| Chat „Firmen-LLM“ | Remote, Protokoll „OpenAI-kompatibel“ oder „vLLM“ | URL `http://host.docker.internal:<port>/v1`, API-Key, exakte Modellkennung, LLM-Kontext des Servers; unter Erweitert die Embedding-URL des Ollama eintragen (Pflichtfeld, wird beim Profiltest geprüft) |

### GPU-Bemessung: Qwen3-Coder 30B auf 24 GB + 16 GB

Mit zwei Karten (24 GB und 16 GB, zusammen 40 GB) ist **64k Kontext** die Empfehlung. Ollama verteilt die
Schichten selbst über beide Karten, weil das Modell samt Cache nicht in die 24-GB-Karte allein passt.

| Posten | Bedarf (Q4_K_M, 8-Bit-KV-Cache) |
|---|---|
| Gewichte `qwen3-coder:30b` | ~18,6 GB |
| KV-Cache je parallele Anfrage bei 64k | ~3,2 GB (48 Schichten × 4 KV-Köpfe × 128 × 2 ≈ 50 KB je Token) |
| Rechenpuffer und Laufzeit | ~1–1,5 GB |
| `bge-m3` (Embeddings) | ~1,2 GB |

Mit zwei parallelen Anfragen sind das rund 28 GB, es bleibt Reserve. Drei gehen noch (~31 GB); bei vier wird es
knapp. Ohne den 8-Bit-Cache (16 Bit) braucht jede Anfrage bei 64k rund 6 GB.

```dotenv
OLLAMA_CONTEXT_LENGTH=65536   # Vorgabe des Ollama-Servers
OLLAMA_NUM_CTX=65536          # Vorgabe für neue Doctus-Profile
OLLAMA_NUM_PARALLEL=2         # jede parallele Anfrage hält einen eigenen Cache
OLLAMA_FLASH_ATTENTION=1      # Voraussetzung für den 8-Bit-Cache (Standard)
OLLAMA_KV_CACHE_TYPE=q8_0     # Standard
```

Im KI-Profil „Qwen3-Coder 30B“ unter Erweitert **LLM-Kontext `65536`** und **Parallelität `2`** eintragen; die
Parallelität in Doctus darf nicht über `OLLAMA_NUM_PARALLEL` liegen, sonst warten Anfragen im Ollama statt in
Doctus. Nach dem Start mit `ollama ps` prüfen, dass `PROCESSOR` „100% GPU“ zeigt (sonst ist etwas auf die CPU
ausgewichen), und mit `nvidia-smi` die Verteilung auf beide Karten. Die Werte sind aus der Modellarchitektur
gerechnet; Flash Attention auf den Turing-Karten (RTX 6000/5000) beim ersten Start einmal messen.

Was 64k im Chat bringt: Anhänge dürfen 30 % des Fensters belegen (rund 69.000 Zeichen statt 8.600 bei 8k), der
Verlauf bleibt länger wörtlich erhalten, und Belegpaket und Werkzeugergebnisse werden seltener gekürzt.

Die Art **Cloud** passt für das Firmen-LLM nicht: Sie ist fest an die Adressen von OpenAI, Anthropic und Gemini
gebunden (OpenAI über die Responses-API), hat kein URL-Feld und verlangt die Cloud-Freigabe. Technisch nutzt
„Remote, OpenAI-kompatibel“ denselben Anfrageweg wie ein OpenAI-Cloud-Profil mit Bearer-Key. Mit „vLLM“ prüft der
Profiltest zusätzlich einen (ungestreamten) Tool-Aufruf; `./test-remote-inference.sh` prüft ihn bei beiden gestreamt.

Der Chat nutzt das **aktive** KI-Profil; ein Wechsel gilt für alle Nutzer zugleich. Ein Vergleich beider Modelle in
der Evaluierung braucht daher getrennte Zeitfenster.

Ist der OpenAI-Container nur eine **Brücke zu einem Firmen-LLM**, belegt er keine GPU; Qwen3-Coder und Firmen-LLM
sind dann beide nutzbar. Fragen, Belegauszüge aus Code und Dokumenten sowie Werkzeugergebnisse gehen in diesem Fall an
den Firmendienst; ob das zulässig ist, entscheidet dessen Betreiber. Der Chat sendet **gestreamt**
(`stream`, `stream_options.include_usage`) mit `tools` und `tool_choice`; die Brücke muss das unverändert
durchreichen und Tool-Aufrufe als `tool_calls` im Stream zurückgeben. Der Profiltest in der Oberfläche fragt
ungestreamt; nur `./test-remote-inference.sh` prüft genau die Anfrageform des Chats. Als LLM-Kontext die echte
Fensterlänge des Firmenmodells eintragen. Prüfen, wenn der Schlüssel nicht in der `.env` steht:

```sh
LLM_API_KEY=<schlüssel> ./test-remote-inference.sh --chat-url http://host.docker.internal:<port>/v1 \
  --chat-model <modellkennung> --chat-provider vllm \
  --embedding-url http://ollama:11434 --embedding-model bge-m3 --embedding-provider ollama
```

Läuft dagegen hinter dem Container ein Modell auf denselben GPUs, konkurriert es mit Qwen3-Coder um den Speicher: Das mitgelieferte Ollama hält Modelle dauerhaft geladen
(`OLLAMA_KEEP_ALIVE=-1`), und zwei Modelle der 30B-Klasse passen nicht gleichzeitig auf 24 + 16 GB.

Mit mitgeliefertem Ollama wird das Paket ohne `--remote-inference` gebaut, `LLM_MODEL=qwen3-coder:30b
./scripts/build-offline-bundle.sh <version>`; es enthält dann rund 20 GB Modellgewichte. Die GPU-Ergänzung
richtet der Installer bei vorhandenem NVIDIA Container Toolkit selbst ein.

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
