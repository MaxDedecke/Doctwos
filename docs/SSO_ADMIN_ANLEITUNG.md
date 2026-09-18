# SSO in Doctus konfigurieren

Diese Anleitung richtet sich an Doctus-Administratoren und beschreibt die Einrichtung von Single Sign-On über OpenID Connect (OIDC). Unterstützt werden unter anderem Keycloak, Microsoft Entra ID, Okta und Authentik.

SSO ergänzt den lokalen Passwort-Login. Der lokale Login bleibt als Notfall- und Administrationszugang erhalten.

## 1. Voraussetzungen

Benötigt werden:

- ein erreichbarer OIDC-Identity-Provider (IdP),
- die Issuer-URL des IdP,
- eine Client-ID,
- ein Client-Secret für einen vertraulichen OIDC-Client,
- eine von Browser und IdP erreichbare Doctus-Adresse.

`API_URL` muss auf die öffentliche Backend-Adresse zeigen. Die Redirect-URI wird daraus automatisch gebildet:

```text
<API_URL>/auth/oidc/callback
```

Beispiel:

```text
https://doctus.example.com/auth/oidc/callback
```

Diese URI muss im IdP exakt eingetragen werden. Schon ein anderer Hostname, Port, Pfad oder ein zusätzlicher Slash führt zu einem Redirect-Fehler.

## 2. OIDC-Client im IdP anlegen

Im Identity-Provider einen neuen OIDC-Client anlegen:

- Flow: Authorization Code / Standard Flow
- Client-Typ: vertraulich (`confidential`), sofern der IdP diese Unterscheidung anbietet
- Redirect-URI: die aus `API_URL` gebildete URI
- Scopes: mindestens `openid`, zusätzlich `profile` und `email`
- Client-Secret: erzeugen und sicher aufbewahren

Die genaue Bezeichnung der Einstellungen hängt vom IdP ab. Für Keycloak ist die Issuer-URL normalerweise die Realm-URL, zum Beispiel:

```text
https://sso.example.com/realms/doctus
```

## 3. Doctus konfigurieren

In der `.env` des Doctus-Deployments folgende Werte setzen:

```dotenv
API_URL=https://doctus.example.com
FRONTEND_URL=https://doctus.example.com

OIDC_ISSUER=https://sso.example.com/realms/doctus
OIDC_CLIENT_ID=doctus
OIDC_CLIENT_SECRET=<geheimes-client-secret>
```

SSO wird nur aktiviert, wenn alle drei `OIDC_*`-Werte gesetzt sind. Die Namen sind fest vorgegeben; insbesondere heißt die Variable `OIDC_ISSUER`, nicht `OIDC_ISSUER_URL`.

Die Änderungen übernehmen:

```sh
docker compose up -d
```

`docker compose restart` reicht für `.env`-Änderungen nicht zuverlässig aus, weil Compose die Variablen beim Erzeugen des Containers übergibt.

## 4. Rollen und Teams automatisch zuordnen

Ohne zusätzliche Konfiguration wird jeder neue SSO-Nutzer als normaler Doctus-Nutzer (`user`) angelegt. Teams und Administratorrechte werden dann manuell unter **Einstellungen → Nutzer** vergeben.

### Standard-Team

Alle neuen SSO-Nutzer können automatisch einem vorhandenen Doctus-Team zugeordnet werden:

```dotenv
OIDC_DEFAULT_TEAM=Alle Mitarbeiter
```

Das Team muss in Doctus bereits existieren. Nicht vorhandene Teams werden nicht automatisch angelegt.

### IdP-Rollen zu Superusern abbilden

Nur ausdrücklich benannte IdP-Rollen dürfen Administratorrechte erhalten:

```dotenv
OIDC_ADMIN_ROLES=doctus-admin,doctus-superuser
```

Besitzt ein SSO-Nutzer eine dieser Rollen, erhält er in Doctus die Rolle `superuser`. Ist `OIDC_ADMIN_ROLES` gesetzt, wird die Doctus-Rolle bei jedem SSO-Login anhand der IdP-Rollen synchronisiert. Deshalb sollten hier nur vertrauenswürdige, eng gefasste Rollen stehen.

### IdP-Gruppen oder Rollen auf Doctus-Teams abbilden

Als JSON:

```dotenv
OIDC_TEAM_MAPPING={"developers":"Entwicklung","operations":"Betrieb"}
```

Oder als kurze Kommaliste:

```dotenv
OIDC_TEAM_MAPPING=developers=Entwicklung,operations=Betrieb
```

Die Zielteams müssen vorher in Doctus angelegt werden. Die Synchronisation fügt die passenden Teammitgliedschaften hinzu und entfernt keine manuell vergebenen Mitgliedschaften.

### Abweichende Claim-Namen

Standardmäßig liest Doctus Rollen aus `roles` und Gruppen aus `groups`. Für abweichende Claim-Namen oder verschachtelte Claims können die Pfade angepasst werden:

```dotenv
OIDC_ROLES_CLAIM=realm_access.roles
OIDC_GROUPS_CLAIM=groups
```

Keycloak-Rollen aus `realm_access.roles` und `resource_access.*.roles` werden zusätzlich automatisch berücksichtigt. Für andere IdPs sollten die tatsächlich gelieferten Claims mit deren Token-/Claim-Ansicht geprüft werden.

## 5. Einrichtung in der Doctus-Oberfläche prüfen

Mit einem lokalen Doctus-Administrator anmelden und **Einstellungen → System & SSO** öffnen.

Dort stehen zur Verfügung:

- SSO-Status, Issuer und Client-ID,
- Status des Client-Secrets, ohne das Secret anzuzeigen,
- die kopierbare Redirect-URI,
- **IdP-Verbindung testen** für die OIDC-Discovery,
- eine Mapping-Simulation für Rollen und Gruppen,
- die konfigurierten Zielteams und deren Existenz in Doctus.

Die Oberfläche zeigt die Konfiguration nur an und testet sie. Änderungen an `.env` werden weiterhin auf dem Server vorgenommen und anschließend mit `docker compose up -d` übernommen.

## 6. Erster Login

1. Prüfen, dass die SSO-Schaltfläche auf der Doctus-Anmeldeseite erscheint.
2. Mit einem Testkonto des IdP anmelden.
3. Prüfen, ob der Nutzer unter **Einstellungen → Nutzer** angelegt wurde.
4. Rolle und Teamzuordnung kontrollieren.
5. Erst danach die Einrichtung für weitere Benutzer freigeben.

Der erste SSO-Nutzer erhält nur dann automatisch Zugriff auf Inhalte, wenn ein passendes Standard-Team oder Mapping konfiguriert ist. Ohne Teamzuordnung kann ein Administrator den Nutzer nachträglich einem Team zuweisen.

## 7. Fehlersuche

### Keine SSO-Schaltfläche

Prüfen, ob alle drei Variablen im Backend-Container vorhanden sind:

```sh
docker compose exec backend-api env | grep '^OIDC_'
```

Danach die Container mit `docker compose up -d` neu erzeugen.

### Redirect-URI wird vom IdP abgelehnt

`API_URL` prüfen und die daraus gebildete URI exakt im IdP eintragen:

```text
<API_URL>/auth/oidc/callback
```

`API_URL` muss die Adresse sein, die der Browser erreicht. `localhost` funktioniert nur, wenn der Browser auf demselben Rechner wie der Doctus-Server läuft.

### Verbindungstest schlägt fehl

- `OIDC_ISSUER` auf Schreibfehler und den richtigen Realm/Tenant prüfen.
- Vom Backend-Container aus muss `https://<issuer>/.well-known/openid-configuration` erreichbar sein.
- Proxy-, Firewall- und DNS-Regeln prüfen.
- Backend-Logs ansehen:

```sh
docker compose logs --tail=100 backend-api
```

### Nutzer wird angelegt, sieht aber keine Projekte

Prüfen, ob `OIDC_DEFAULT_TEAM` oder `OIDC_TEAM_MAPPING` auf ein tatsächlich vorhandenes Doctus-Team zeigt. Alternativ den Nutzer unter **Einstellungen → Nutzer** manuell einem Team zuweisen.

## 8. Sicherheit

- Doctus und den IdP produktiv nur über HTTPS betreiben.
- Das Client-Secret niemals in Git, Screenshots oder Support-Tickets veröffentlichen.
- `OIDC_ADMIN_ROLES` nur mit ausdrücklich freigegebenen Admin-Rollen befüllen.
- Den lokalen Bootstrap-Administrator als Notfallzugang geschützt aufbewahren.
- Nach einer Änderung der IdP-Rollen mit einem Testkonto prüfen, ob Rolle und Teamzuordnung wie erwartet synchronisiert werden.
