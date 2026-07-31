# AVV-Vorlage (Auftragsverarbeitungsvertrag) — Entwurf für den Pilotkunden

> **Kein fertiger Vertrag.** Diese Datei ist ein strukturierter Entwurf nach Art. 28 DSGVO als Startpunkt für das Gespräch mit der Rechtsberatung — sowohl der eigenen als auch der des Kunden. Vor Unterschrift durch eine Juristin/einen Juristen prüfen lassen. Alle `[ ]`-Platzhalter sind auszufüllen.

## 0. Zuerst klären: wird überhaupt ein AVV gebraucht?

Ein AVV ist nur nötig, wenn der Anbieter (Doctus) personenbezogene Daten des Kunden **verarbeitet** — nicht schon, wenn der Kunde die Software nur lizenziert und selbst betreibt. Anhand der tatsächlichen Datenflüsse (`docs/DATENFLUSS_UEBERSICHT.md`) im Scoping-Workshop klären, welcher Fall vorliegt:

| Szenario | AVV mit Doctus-Anbieter nötig? |
|---|---|
| Reines On-Prem-Deployment beim Kunden, kein Remote-Zugriff des Anbieters | Nein — der Kunde ist selbst verantwortliche Stelle und alleiniger Betreiber |
| On-Prem-Deployment, aber Anbieter hat vereinbarten Remote-Support-/Wartungszugriff | Ja |
| EU-gehostete Single-Tenant-Instanz, betrieben durch den Anbieter | Ja |
| Kunde aktiviert ein Cloud-LLM-Profil (`llm.allowCloudProviders: true`) | Kein AVV mit dem Doctus-Anbieter dafür nötig, aber eigener AVV/DPA zwischen Kunde und dem jeweiligen LLM-Anbieter (OpenAI/Google/Anthropic) — siehe Anhang 2 |

Trifft nur die erste Zeile zu, reicht in der Regel ein einfacher Lizenz-/Pilotvertrag ohne AVV-Anlage. Die folgende Vorlage ist für die anderen Fälle gedacht.

---

## 1. Gegenstand und Dauer der Verarbeitung

- Gegenstand: [z.B. Bereitstellung/Betrieb der Doctus-Plattform zur Volltextsuche und BIM/CAD-Analyse für das Pilotprojekt]
- Dauer: gekoppelt an die Laufzeit des Hauptvertrags (Pilotvertrag vom [Datum]), endet automatisch mit dessen Beendigung.

## 2. Art und Zweck der Verarbeitung

- Zweck: Indexierung und durchsuchbare Bereitstellung von Projektdokumenten, BIM/CAD-Modellen und daraus abgeleiteten Chat-Antworten für Mitarbeitende des Auftraggebers.
- Art der Verarbeitung: Speicherung, Volltext-/Vektorindexierung, KI-gestützte Auswertung (RAG/LLM-Inferenz), Bereitstellung über eine webbasierte Oberfläche.

## 3. Art der personenbezogenen Daten

- [ ] Namen und E-Mail-Adressen von Nutzer:innen (aus dem Login/OIDC-Provider des Auftraggebers)
- [ ] In Projektdokumenten enthaltene personenbezogene Daten (z.B. Namen in Besprechungsprotokollen, Verantwortlichkeiten in Leistungsverzeichnissen)
- [ ] Nutzungsmetadaten (Zeitstempel von Chat-Anfragen, aufgerufene Dokumente)
- [ ] Weitere: [ ]

## 4. Kategorien betroffener Personen

- Mitarbeitende des Auftraggebers
- Ggf. in Dokumenten genannte Dritte (z.B. Bauherren, Behördenkontakte, Nachunternehmer)

## 5. Pflichten und Rechte des Auftraggebers

Der Auftraggeber bleibt datenschutzrechtlich Verantwortlicher im Sinne von Art. 4 Nr. 7 DSGVO. Er ist berechtigt, Weisungen zur Verarbeitung zu erteilen; der Auftragnehmer verarbeitet Daten ausschließlich im Rahmen dieser Weisungen und des Hauptvertrags.

## 6. Technische und organisatorische Maßnahmen (TOMs)

- Zugangsdaten zu externen Wissensquellen (Confluence/Jira/Notion) werden verschlüsselt gespeichert (Fernet, `MASTER_ENCRYPTION_KEY`).
- Sitzungs-Cookies sind signiert (`SESSION_SECRET_KEY`) und werden nur über TLS ausgeliefert, sobald ein Reverse-Proxy mit HTTPS vorgeschaltet ist (siehe `docs/DEPLOYMENT.md#tls`).
- Authentifizierung erfolgt über den OIDC-Provider des Auftraggebers, nicht über ein eigenes Passwort-System.
- Zugriffskontrolle auf Team- und Projektebene innerhalb der Anwendung (`docs/TEAM_ACCESS_CONTROL.md`, `docs/PROJECT_ACCESS_CONTROL.md`).
- [ ] Weitere kundenspezifische Maßnahmen ergänzen (z.B. Backup-Verschlüsselung, Netzsegmentierung).

## 7. Unterauftragsverarbeiter

- Grundsätzlich keine, solange `llm.allowCloudProviders: false` bleibt und keine externen Wissensquellen (Confluence/Jira/Notion) angebunden sind.
- Falls ein Cloud-LLM-Profil aktiviert wird: der jeweilige LLM-Anbieter ist Unterauftragsverarbeiter — siehe Anhang 2, eigener AVV mit diesem Anbieter erforderlich.
- Falls Confluence/Jira/Notion angebunden werden: keine neue Unterauftragsverarbeitung durch Doctus, da der Auftraggeber mit diesen Anbietern bereits selbst in vertraglicher Beziehung steht.

## 8. Unterstützungspflichten

Der Auftragnehmer unterstützt den Auftraggeber bei der Erfüllung von Betroffenenrechten (Auskunft, Löschung, Berichtigung) sowie bei Meldepflichten nach Art. 33/34 DSGVO im Fall einer Datenschutzverletzung.

## 9. Löschung und Rückgabe nach Vertragsende

Nach Beendigung des Hauptvertrags: [ ] Frist zur Löschung/Rückgabe vereinbaren (Vorschlag: 30 Tage), danach vollständige Löschung aller Datenbank- und Dateisystem-Inhalte der Instanz.

## 10. Kontrollrechte

Der Auftraggeber ist berechtigt, sich von der Einhaltung der TOMs zu überzeugen (z.B. durch Einsicht in Konfiguration/Deployment-Dokumentation, Vor-Ort-Prüfung).

---

## Anhang 1 — Deployment-spezifische Angaben

- [ ] Konkreter Deployment-Ort (Kunden-Serverraum / Rechenzentrum / EU-Hosting-Anbieter)
- [ ] Verantwortliche Kontaktperson beim Auftragnehmer für Datenschutzanfragen
- [ ] Vereinbarte Form des Remote-Supports, falls zutreffend

## Anhang 2 — Cloud-LLM-Unterauftragsverarbeiter (nur falls `llm.allowCloudProviders: true`)

- [ ] Anbieter: [OpenAI / Google / Anthropic]
- [ ] Eigener AVV/DPA mit diesem Anbieter abgeschlossen: [ ] Ja / [ ] Nein
- [ ] Datenverarbeitungsort des Anbieters (EU-Region falls verfügbar, sonst Drittlandtransfer prüfen — Standardvertragsklauseln erforderlich)
