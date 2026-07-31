# Datenfluss-Übersicht — welche Daten fließen wohin

Ein-Seiter für den Scoping-Workshop mit dem Pilotkunden (siehe `ROADMAP_PILOTKUNDE.md`). Grundlage für das Gespräch mit der Kunden-IT/Datenschutzbeauftragten, bevor echte Projektdaten eingespielt werden. Basiert auf der tatsächlichen Architektur (`docs/DEPLOYMENT.md`, `docs/POSITIONING.md`), nicht auf einer generischen Checkliste.

## Grundmodell: Doctus läuft on-prem beim Kunden

Doctus ist Self-Hosted, Single-Tenant: eine Instanz pro Kunde, auf dessen eigener Infrastruktur (`docs/DEPLOYMENT.md`). Im Standardfall verlässt **keine** Projektdatei, kein Chat-Log und kein Dokumentinhalt das Netzwerk des Kunden:

| Datenart | Speicherort | Verlässt das Kundennetzwerk? |
|---|---|---|
| Hochgeladene Dokumente, IFC/DWG-Modelle, GAEB-Dateien | PostgreSQL + Dateisystem des Kunden-Docker-Hosts | Nein |
| Vektor-Embeddings der Dokumente | pgvector (selbe PostgreSQL-Instanz) | Nein |
| Chat-Nachrichten/Sitzungen | PostgreSQL des Kunden-Hosts | Nein |
| LLM-Inferenz (Chat-Antworten, Embeddings) | Ollama-Container auf Kunden-Hardware (`mistral-nemo`, `bge-m3`) | Nein |
| Login/Authentifizierung | Kunden-eigener OIDC-Provider (Keycloak/Entra ID/Okta/...) | Nein — Doctus selbst führt kein eigenes Nutzerverzeichnis |
| Zugangsdaten für Confluence/Jira/Notion-Connectoren | Verschlüsselt in PostgreSQL (`MASTER_ENCRYPTION_KEY`, Fernet) | Nein, außer an die vom Kunden selbst konfigurierte Confluence/Jira/Notion-Instanz (siehe unten) |

## Ausnahmen — wo tatsächlich Daten das Kundennetzwerk verlassen

**1. Vom Kunden selbst konfigurierte Wissensquellen (Confluence, Jira, Notion).**
Wenn der Kunde eine dieser Quellen einbindet, ruft Doctus Daten von der vom Kunden angegebenen Instanz ab (z.B. seiner eigenen Confluence-Cloud-Instanz) — das ist ein Datenfluss, den der Kunde selbst bereits mit diesem Anbieter vereinbart hat, Doctus fügt hier keine neue Partei hinzu.

**2. Cloud-LLM-Provider — standardmäßig deaktiviert.**
Doctus unterstützt zusätzlich zu Ollama eine Profil-Umschaltung auf OpenAI/Google Gemini/Anthropic. Das ist **standardmäßig ausgeschaltet** (`config/features.json` → `llm.allowCloudProviders: false`) — das Backend lehnt entsprechende Anfragen hart ab (`backend/core/config.py::cloud_llm_allowed`, geprüft sowohl im Chat als auch im Code-Compliance-Checker), das Frontend zeigt die Option gar nicht erst an. Nur wenn ein Kunde das **explizit** wünscht (z.B. für größere Modelle als lokal sinnvoll betreibbar), wird der Flag umgestellt — und erst dann fließen Anfragen inkl. des jeweils abgerufenen Dokumentenkontexts an den gewählten externen Anbieter. In diesem Fall: eigene AVV mit dem jeweiligen LLM-Anbieter prüfen/abschließen (siehe `AVV_VORLAGE.md`), bevor der Flag umgestellt wird.
>
> ✅ **Ehemalige Lücke, seit 2026-07-09 geschlossen:** Der Code-Compliance-Checker (`POST /aec/projects/{id}/run-compliance`) prüfte `allowCloudProviders` zeitweise nicht, obwohl er (seit dem Multi-Provider-Umbau) ebenfalls gegen einen Cloud-Provider laufen konnte. `backend/api/aec_workflows.py::run_compliance_checker` lehnt einen Cloud-Provider jetzt vor dem Celery-Dispatch mit derselben Prüfung ab wie der Chat. Siehe `docs/GAPS.md` Punkt 6.

**3. Support/Wartungszugriff durch den Doctus-Anbieter.**
Falls im Pilotvertrag Remote-Support vereinbart wird (z.B. VPN-Zugriff zur Fehlerdiagnose): dokumentieren, wer wann worauf Zugriff hat. Ohne einen solchen Zugriff ist der Doctus-Anbieter kein datenschutzrechtlicher Auftragsverarbeiter, da er die Instanz weder betreibt noch einsieht.

## Fragen, die im Scoping-Workshop zu klären sind

- Gibt es eine Datenschutzbeauftragte/einen Datenschutzbeauftragten beim Kunden, der/die das Deployment vorab freigeben muss?
- Sollen Confluence/Jira/Notion überhaupt angebunden werden, oder reicht FolderWatch (lokaler Ordner/NAS, `docs/FOLDER_WATCH.md`) für den PoC?
- Besteht der Wunsch nach einem Cloud-LLM-Profil? Falls ja: welcher Anbieter, und liegt bereits eine AVV mit diesem vor?
- Wird Remote-Support während des PoC benötigt, und wenn ja, in welcher Form (VPN, geteilter Bildschirm, Log-Export)?
