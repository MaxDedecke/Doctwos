# Doctus lokal beim Kunden deployen — Schritt-für-Schritt (für Einsteiger)

Diese Anleitung richtet sich an jemanden, der Doctus bei einem Kunden vor Ort (oder per Remote-Zugriff auf dessen Server) installiert und dabei nicht jeden Docker-/Linux-Befehl auswendig kennt. Jeder Schritt enthält den genauen Befehl, was er bewirkt, und woran man erkennt, dass er geklappt hat.

Für die technische Referenz (alle `.env`-Variablen im Detail, Air-Gapped-Installation, Backup/Restore, Monitoring) siehe [`DEPLOYMENT.md`](./DEPLOYMENT.md) — dieses Dokument hier ist der praktische Einstieg für den Kundentermin selbst.

---

## 1. Was muss beim Kunden vorher vorhanden/geklärt sein

Vor dem Termin abklären, sonst steht man vor Ort fest:

| Voraussetzung | Warum | Wie prüfen |
|---|---|---|
| Ein Linux-Server (Ubuntu 22.04/24.04 empfohlen), x86_64 | Doctus läuft in Docker-Containern, getestet auf Ubuntu | `cat /etc/os-release` |
| Embedding-Pilot: 8 GB RAM / 4 CPU-Kerne; Auslieferung mit lokalem 12B-LLM: mindestens 16 GB / 8 Kerne und möglichst GPU | Bis zur ersten Auslieferung ist `LLM_MODEL=disabled`; auf dem kleinen Pilot-Host läuft nur `bge-m3`. Das 12B-LLM darf dort nicht aktiviert werden. | `free -h` und `nproc` |
| Mindestens ~25 GB freier Speicherplatz | BGE-M3, Docker-Images/Build-Cache und wachsende Datenbank/Repos; ein später aktiviertes Q4-LLM benötigt zusätzlich ~7,5 GB | `df -h /` |
| Root- oder sudo-Zugriff auf dem Server | Für Docker-Installation und Firewall-Regeln nötig | — |
| Internetzugang des Servers während der Installation | Docker-Images und KI-Modelle werden heruntergeladen (**Online-Pfad**). Ohne Internet: Air-Gapped-Pfad, siehe `DEPLOYMENT.md` | `curl -I https://github.com` sollte eine Antwort liefern |
| Ein Identity Provider (IdP) für den Login, z.B. Keycloak, Microsoft Entra ID, Okta, Authentik | Doctus hat kein eigenes Login-System, sondern meldet sich über OIDC beim Kunden-IdP an. Ohne echten IdP kann man nur mit einem Test-Login (`testuser`/`testpass`) demonstrieren, siehe Abschnitt 8 | Vom Kunden-IT erfragen: **Issuer-URL**, **Client-ID**, **Client-Secret** |
| Wissen, ob der Zugriff nur aus dem lokalen Netzwerk (LAN) erfolgt oder auch von außen (Internet) erreichbar sein muss | Bestimmt, welche IP-Adresse man in Schritt 4 einträgt | Mit dem Kunden klären, bevor man anfängt |

### Faustregel für die Server-Größe

- **Aktueller Embedding-Pilot ohne lokales Chat-LLM:** 8 GB RAM / 4 vCPU; Suche/Indexierung funktionieren, Chat und LLM-basierte Compliance sind bewusst deaktiviert.
- **Auslieferung mit lokalem Mistral NeMo 12B:** mindestens 16 GB RAM / 8 vCPU und möglichst GPU; `LLM_MODEL` vor der Installation explizit setzen.
- **Mehrere gleichzeitige Nutzer oder große Repos (viel Parsing nebenbei):** eher eine GPU einplanen (lokal oder gemietet, z.B. RunPod) statt CPU-only hochzuskalieren — 12B-Modelle sind auf CPU spürbar langsam.
- Hat der Server eine NVIDIA-GPU, nutzt Ollama sie automatisch — Antworten werden spürbar schneller. Beim Kunden vorher fragen, ob eine GPU vorhanden ist. Ohne GPU vor Ort: Ollama kann alternativ gegen einen extern gehosteten GPU-Endpoint (z.B. RunPod) zeigen, statt gegen den lokalen `ollama`-Container — das ist aber noch nicht als Standard-Deployment-Pfad verdrahtet, sondern derzeit manuelle Konfiguration.
- **Bei 24+ GB VRAM:** vor der Installation `LLM_MODEL=hf.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF:Q8_0` in `.env` setzen (Premium-Tier) — laut `docs/COMPLIANCE_EVAL.md` niedrigere Übersehquote (False-Negative-Rate) beim Compliance-Checker als der Standard-Tier `Q4_K_M`, bei sonst gleicher Qualität. Siehe `DEPLOYMENT.md`, Abschnitt "Model mode".

---

## 2. Docker installieren

Prüfen, ob Docker schon da ist:

```sh
docker --version
docker compose version
```

Kommt `command not found`, Docker fehlt noch. Installation (Ubuntu/Debian):

```sh
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

Das installiert Docker Engine **inklusive** des `docker compose`-Plugins (kein separates `docker-compose` mehr nötig — moderne Syntax ist `docker compose`, mit Leerzeichen).

✅ **Prüfen:** `docker compose version` zeigt eine Versionsnummer an, kein Fehler.

Falls der Docker-Dienst nicht automatisch läuft:

```sh
sudo systemctl status docker      # Status ansehen
sudo systemctl start docker       # falls "inactive"
```

---

## 3. Repository holen

```sh
git clone --branch main --single-branch https://github.com/MaxDedecke/Doctus.git
cd Doctus
```

`main` ist der freigegebene Branch für Kunden-Deployments. Änderungen werden zuerst auf `develop` entwickelt und geprüft und anschließend nach `main` übernommen.

---

## 4. Die Server-Adresse herausfinden — der wichtigste Schritt

Doctus besteht aus mehreren Teilen (Frontend im Browser, Backend-API, Login-Server), die sich gegenseitig über eine feste Adresse finden müssen. Diese Adresse **muss überall exakt gleich** eingetragen werden — der häufigste Fehler bei diesem Deployment ist, dass irgendwo noch `localhost` steht, obwohl der Browser auf einem anderen Rechner läuft.

### Fall A: Zugriff nur aus dem lokalen Netzwerk (LAN) — der Normalfall beim Kunden vor Ort

Das ist die IP-Adresse, unter der der Server **innerhalb des Firmennetzwerks** erreichbar ist (z. B. `192.168.1.50`).

```sh
hostname -I
```

Gibt eine oder mehrere IP-Adressen aus, getrennt durch Leerzeichen — z. B.:

```
192.168.1.50 172.17.0.1
```

Meist ist die **erste** die richtige (die reale Netzwerkkarte). Die zweite (`172.17.x.x`) ist typischerweise eine interne Docker-Netzwerk-Adresse und **nicht** die richtige.

Zur Sicherheit genauer nachsehen, welche Adresse zu welcher Netzwerkkarte gehört:

```sh
ip a
```

Man sucht nach einem Eintrag wie:

```
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
    inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0
```

`eth0` (oder `ens18`, `enp0s3` — der Name variiert je nach Server) ist meist die "echte" Netzwerkkarte. Docker-eigene Interfaces heißen typischerweise `docker0`, `br-...` oder `veth...` — die ignorieren.

### Fall B: Server muss auch von außerhalb des Firmennetzes erreichbar sein (z. B. Homeoffice-Zugriff, Cloud-Server)

Dann braucht man die **öffentliche** IP-Adresse, nicht die interne:

```sh
curl -4 ifconfig.me
```

oder alternativ:

```sh
curl -4 https://api.ipify.org
```

Beide geben nur die öffentliche IP aus, z. B. `82.165.216.180`. **Wichtig:** Diese Adresse funktioniert nur, wenn der Kunde-Router/die Firewall die Ports 3000 und 8000 (und ggf. 8080 für Test-Keycloak, siehe Abschnitt 8) auch tatsächlich zum Server durchleitet (Port-Forwarding). Das mit der Netzwerk-/IT-Abteilung des Kunden vorher klären — das kann man von der Konsole aus nicht selbst einrichten.

### Fall C: Server hat einen festen Domainnamen (z. B. `doctus.kundenfirma.de`)

Dann diesen Domainnamen anstelle einer IP-Adresse verwenden — funktioniert genauso, ist aber stabiler (IP-Adressen können sich ändern, ein DNS-Name bleibt). Für eine echte Produktivumgebung beim Kunden ist das ohnehin empfehlenswert, siehe Abschnitt 9 (TLS).

> **Merke:** Egal welcher Fall — man trägt am Ende **eine feste Adresse** (IP oder Domain) ein und verwendet **exakt dieselbe** an allen drei Stellen in der `.env`-Datei (Schritt 5). Nicht mischen (nicht `localhost` an einer Stelle und die IP an einer anderen).

---

## 5. Konfigurationsdatei (`.env`) anlegen

```sh
cp .env.example .env
```

Jetzt `.env` mit einem Editor öffnen (z. B. `nano .env`) und der Reihe nach ausfüllen:

### 5.1 Datenbank-Passwort setzen

```
POSTGRES_PASSWORD=<ein selbstgewähltes, sicheres Passwort>
```

Ein zufälliges Passwort generieren, falls keins zur Hand ist:

```sh
openssl rand -base64 24
```

### 5.2 Zwei Sicherheits-Schlüssel generieren

Diese verschlüsseln gespeicherte Zugangsdaten UND Dokumentinhalte (alle Chunks aus Git/Confluence/Jira/Notion/IFC/DWG/GAEB/Upload, Chat-Nachrichten, Compliance-Zitate — siehe `backend/models/crypto_types.py`) bzw. signieren die Login-Session. **Einmal generiert, nicht mehr ändern**, sobald echte Kundendaten im System sind (sonst werden gespeicherte Tokens und Dokumentinhalte unlesbar).

```sh
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
→ Ergebnis in `.env` bei `MASTER_ENCRYPTION_KEY=` eintragen.

```sh
openssl rand -base64 32
```
→ Ergebnis in `.env` bei `SESSION_SECRET_KEY=` eintragen.

### 5.3 Die Server-Adresse aus Schritt 4 eintragen

Angenommen, die ermittelte Adresse ist `192.168.1.50` — dann in `.env`:

```
API_URL=http://192.168.1.50:8000
FRONTEND_URL=http://192.168.1.50:3000
OIDC_REDIRECT_URI=http://192.168.1.50:8000/auth/callback
```

**Alle drei müssen dieselbe Adresse verwenden.** Das ist der Schritt, den man beim Testen von einem anderen Rechner aus als erstes falsch macht, wenn man `.env.example` unverändert lässt (dort steht überall `localhost`).

### 5.4 OIDC-Zugangsdaten des Kunden eintragen

Vom Kunden-IT-Team erfragt (oder Test-Setup aus Abschnitt 8 nutzen):

```
OIDC_ISSUER_URL=<vom Kunden erhaltene Issuer-URL>
OIDC_CLIENT_ID=<vom Kunden erhaltene Client-ID>
OIDC_CLIENT_SECRET=<vom Kunden erhaltenes Client-Secret>
```

Zusätzlich beim Kunden-IdP registrieren (das muss der Kunde/dessen IT in ihrem IdP eintragen): die exakte `OIDC_REDIRECT_URI` aus 5.3 als **erlaubte Redirect-URI** für den Client.

### 5.5 Ersten Admin-Nutzer festlegen

```
ADMIN_EMAILS=vorname.nachname@kundenfirma.de
```

Diese E-Mail-Adresse (muss mit der E-Mail aus dem IdP-Login übereinstimmen) bekommt beim ersten Login automatisch Admin-Rechte. Mehrere Adressen mit Komma trennen.

---

## 6. Firewall — nicht alles nach außen offen lassen

Die mitgelieferte `docker-compose.yml` veröffentlicht standardmäßig auch die Datenbank (Port 5432), Redis (6379) und Ollama (11434) auf allen Netzwerk-Interfaces. Das sind interne Komponenten, die **niemand von außen direkt ansprechen** sollte.

Prüfen, was tatsächlich von außen erreichbar ist:

```sh
sudo ss -tulpn | grep LISTEN
```

Für den produktiven Kundeneinsatz empfiehlt sich eine Firewall, die nur die wirklich benötigten Ports nach außen freigibt (3000 für das Frontend, 8000 für die API — 5432/6379/11434 nur lokal). Mit `ufw` (falls auf dem System vorhanden):

```sh
sudo ufw allow 3000/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

Genaue Regeln hängen vom Kundennetzwerk ab — im Zweifel mit der IT-Abteilung des Kunden abstimmen, bevor man die Firewall aktiviert (sonst sperrt man sich womöglich selbst aus, falls der Zugriff z. B. über SSH auf einem anderen Port läuft).

---

## 7. Stack starten

```sh
./install.sh
```

Der Installer baut die drei unterschiedlichen Images bewusst nacheinander; ein paralleles `docker compose up -d --build` kann unter Docker 29 beim gemeinsam genutzten Parser-/Beat-Image mit `image ... already exists` abbrechen. Der erste Lauf dauert einige Minuten. Fortschritt prüfen:

```sh
docker compose ps
```

✅ **Prüfen:** Alle 7 Zeilen (`db`, `redis`, `ollama`, `backend-api`, `parser-worker`, `parser-beat`, `frontend`) müssen `Up` bzw. `running` zeigen. Steht dort `Restarting`, ist etwas kaputt — dann:

```sh
docker compose logs <servicename>
```

anschauen (z. B. `docker compose logs backend-api`), um die Fehlermeldung zu sehen.

Im aktuellen Pilotmodus lädt der Installer ausschließlich `bge-m3`. Prüfen:

```sh
docker exec doctus-ollama ollama list
```

Auf dem 8-GB-/4-vCPU-Host darf hier nur `bge-m3` erscheinen. Ein lokales Chat-/Compliance-LLM erst auf geeigneter Auslieferungshardware über `LLM_MODEL` aktivieren; Details stehen in `DEPLOYMENT.md`.

---

## 8. Kein Kunden-IdP verfügbar? Test-Login einrichten

Für eine Demo oder ersten Funktionstest, bevor der Kunde seinen eigenen Identity Provider bereitstellt, liegt im Repo ein fertiges Test-Setup (Keycloak mit vorkonfiguriertem Nutzer). **Nur für Demos/Tests — niemals mit echten Kundendaten produktiv einsetzen**, da Passwort und Client-Secret öffentlich im Repository stehen.

```sh
docker run -d --name test-keycloak -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  -e KC_HOSTNAME=192.168.1.50 \
  -e KC_HTTP_ENABLED=true -e KC_HOSTNAME_STRICT_HTTPS=false \
  -v "$(pwd)/.github/keycloak:/opt/keycloak/data/import" \
  -v "$(pwd)/.github/keycloak/themes/doctus:/opt/keycloak/themes/doctus" \
  quay.io/keycloak/keycloak:25.0 start-dev --import-realm
```

(`192.168.1.50` durch die eigene Server-Adresse aus Schritt 4 ersetzen.)

Ca. 30 Sekunden warten, dann prüfen ob Keycloak bereit ist:

```sh
curl -sf http://192.168.1.50:8080/realms/doctus/.well-known/openid-configuration && echo "Keycloak bereit"
```

Im Keycloak-Adminbereich (`http://192.168.1.50:8080`, Login `admin`/`admin`) unter *Clients → doctus-backend → Settings → Valid redirect URIs* die eigene `OIDC_REDIRECT_URI` (aus Schritt 5.3) ergänzen, falls sie nicht schon `http://192.168.1.50:8000/auth/callback` enthält.

In `.env` eintragen:

```
OIDC_ISSUER_URL=http://192.168.1.50:8080/realms/doctus
OIDC_CLIENT_ID=doctus-backend
OIDC_CLIENT_SECRET=ci-only-keycloak-client-secret
ADMIN_EMAILS=testuser@example.com
```

Ändern von `.env` wird erst nach folgendem Befehl wirksam (**nicht** `restart` verwenden — das liest `.env` nicht neu ein):

```sh
docker compose up -d
```

Login im Browser unter `http://192.168.1.50:3000` mit **Benutzername `testuser`, Passwort `testpass`**.

---

## 9. Verschlüsselung (TLS/HTTPS) für den echten Kundenbetrieb

Doctus selbst liefert nur unverschlüsseltes HTTP (Port 3000/8000). Für eine echte Produktivnutzung beim Kunden **immer** einen Reverse Proxy mit TLS davorschalten (z. B. Caddy, nginx, Traefik — oder was die Kunden-IT bereits einsetzt). Ohne HTTPS wird das Login-Cookie unverschlüsselt übertragen. Details und ein Caddy-Beispiel stehen in [`DEPLOYMENT.md`](./DEPLOYMENT.md#tls).

---

## 10. Abschlusscheck

- [ ] `docker compose ps` → alle 7 Container `Up`
- [ ] `curl http://<server-adresse>:8000/health` → `{"status":"healthy"}`
- [ ] Browser auf `http://<server-adresse>:3000` → Login-Seite erscheint, kein CORS-Fehler in der Browser-Konsole (F12)
- [ ] Login mit Kunden-IdP oder Test-User erfolgreich, Startseite lädt
- [ ] `.env` an einem sicheren Ort gesichert (enthält alle Geheimnisse — siehe Backup-Kapitel in `DEPLOYMENT.md`)

---

## Die 3 häufigsten Fehler (und wie man sie erkennt)

1. **"Login-Button tut nichts" / Backend gibt 500 zurück auf `/auth/login`**
   → `OIDC_ISSUER_URL`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` sind noch leer oder falsch. Prüfen mit `docker compose logs backend-api`.

2. **Login beim IdP klappt, aber man landet danach auf einer Fehlerseite oder "Seite nicht erreichbar"**
   → Irgendwo steht noch `localhost` statt der echten Server-Adresse (`API_URL`, `FRONTEND_URL` oder `OIDC_REDIRECT_URI` in `.env`, oder die Redirect-URI ist beim IdP nicht exakt gleich eingetragen). Alle vier Stellen müssen wortwörtlich übereinstimmen, inklusive `http://` vs. `https://`.

3. **`.env` geändert, aber nichts passiert**
   → `docker compose restart` reicht nicht. Immer `docker compose up -d` verwenden, damit die Container mit den neuen Werten neu erstellt werden.

4. **Kunde meldet ein Problem, das nicht sofort klar ist**
   → **Bevor irgendetwas neu gestartet wird:** einmal `python scripts/generate_diagnostics.py` im Projektordner ausführen. Das Skript sammelt Logs, Container-Status, DB-Metadaten (ohne Kundendokumente/Chat-Inhalte) und Systeminfos in einer `.tar.gz`-Datei — sicher zum Weiterleiten, Geheimnisse aus `.env` sind automatisch geschwärzt. Ein Neustart löscht die Logs sofort und unwiderruflich, also erst das Diagnose-Bundle erzeugen, dann neu starten. Details siehe `DEPLOYMENT.md` → "Diagnostics bundle".
