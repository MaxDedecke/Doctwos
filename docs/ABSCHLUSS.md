# Doctus — Abschlussdokumentation

Stand: 02.08.2026. Dieses Dokument fasst zusammen, was der Implementierungsauftrag
(`docs/IMPLEMENTIERUNGSPLAN.md`, AP-0…AP-9) geliefert hat und was zur Übergabe an
den Auftraggeber (Fujitsu/DRV) ansteht. Für laufende Detailarbeit siehe weiterhin
`docs/UMSETZUNGSSTAND.md`; für Einzelentscheidungen `docs/ENTSCHEIDUNGEN.md`.

## 1. Ergebnis

Alle zehn Arbeitspakete (AP-0 bis AP-9) sind für den Implementierungsauftrag
abgeschlossen. Doctus ist ein lauffähiger On-Premise-Wissensassistent für
COBOL-Bestände: natürlichsprachliche Fragen, Antworten mit klickbaren Quellen im
Originalcode, Navigation Programm→Section→Paragraph, Aufrufgraph-Visualisierung,
Multi-Branch-Monorepo-Ingestion, Konnektoren (Git/Confluence/Jira/WebDAV/Folder/
Upload), lokale Auth, Job-Center, vollständiges Design-Token-System.

Traceability (Anforderung → Arbeitspaket) siehe `docs/IMPLEMENTIERUNGSPLAN.md`
§15 — dort sind alle F-/NF-IDs mit Status hinterlegt.

## 2. Architekturprinzipien — Umsetzungsstand

1. **On-Premise per Default.** Erfüllt. Ollama lokal, Cloud-LLM-Profile nur
   Opt-in über `cloud_llm_allowed()`.
2. **Strikt Open Source (nur MIT/BSD/Apache-2.0).** Bis auf einen bekannten
   Fund erfüllt: `Unidecode` (GPL-2.0-or-later) hängt transitiv über
   `mcp-atlassian` (Confluence-/Jira-Konnektor) mit rein. Dokumentiert in
   E-7 (`docs/ENTSCHEIDUNGEN.md`), CI-Job `licenses` bewusst rot als
   **Release-Blocker**, wartet auf Auftraggeber-Rückmeldung.
3. **Keine zusätzlichen Services.** Erfüllt — kein Neo4j/ElasticSearch/
   ANTLR-Runtime.
4. **Skalierung by Default.** Weitgehend erfüllt; ein realer Engpass wurde im
   AP-9-Lasttest mit synthetischem Korpus gefunden und behoben (E-8:
   Embedding-Batchgröße/Timeout, siehe unten). Persistenz-Durchsatz
   (~19 Dateien/s bei Pass-1-Einzel-Flush) ist als Risiko dokumentiert, aber
   nur an einem echten 100-GB-Bestand abschließend zu bewerten.
5. **Zeilennummern sind heilig.** Erfüllt — Copybooks werden nie expandiert,
   jede Entity/Kante trägt physische Start-/Endzeilen.

## 3. In dieser Abschluss-Session zusätzlich umgesetzt

- **npm-CVE-Fixes (Frontend):** `next` 16.2.10→16.2.12, `sharp`-Override auf
  `^0.35.3` (behebt CVE-2026-33327/33328/35590/35591), `brace-expansion` über
  `npm audit fix`. `npm audit` meldet danach **0 Vulnerabilities**. `npx tsc
  --noEmit`, `npm run test` (4/4) und `npm run build` grün.
- **E-8 (Embedding-Batchgröße vs. CPU-only-Timeout) umgesetzt:**
  `ollama_client.get_embeddings_batch()` teilt Texte jetzt in Sub-Batches von
  maximal `EMBED_BATCH_MAX_CHUNKS` (Default 20) statt alle Chunks eines
  Dokuments in einem Request zu schicken; der Timeout ist über
  `EMBED_BATCH_TIMEOUT` konfigurierbar (Default 120s, wie
  `COMPLIANCE_LLM_TIMEOUT`). Verhindert, dass ein großes Dokument bei
  CPU-only-Kunden in Timeout-Retry-Schleifen hängen bleibt. Neue Tests
  (`parser/tests/test_ollama_client.py`), Parser-Suite 155/155 grün
  (152 vorher + 3 neue).

## 4. Übergabepunkte an den Auftraggeber (nicht ad hoc lösbar)

Drei Punkte aus dem ursprünglichen AP-9-Umfang bleiben offen — nicht weil
Arbeit fehlt, sondern weil sie Zugriff/Autorität brauchen, die außerhalb
dieses Implementierungsauftrags liegt (siehe E-9, `docs/ENTSCHEIDUNGEN.md`):

| Punkt | Braucht vom Auftraggeber | Was bereits vorbereitet ist |
|---|---|---|
| **Formale Lasttest-Abnahme** | Zugriff auf einen echten DRV-COBOL-Bestand | `scripts/generate_synthetic_cobol_corpus.py` liefert reale Messwerte an einem Ersatzkorpus (807 Programme/s Parsen, ~19 Dateien/s Persistenz, ~1,1 Chunks/s CPU-Embedding) — kein Ersatz für die Abnahme selbst |
| **BITV-Abnahme** | Verbindlicher Prüfumfang, ggf. akkreditierte Prüfstelle für den manuellen Teil | Automatisierter axe-core-Basis-Check (WCAG2A/AA) läuft in CI (`frontend/e2e/accessibility.spec.ts`), fünf reale Befunde bereits behoben |
| **Farbkontrast-Nachbesserung** | Freigabe der Markenverantwortlichen für abweichende Fujitsu-Farbtöne | Betroffene Stellen sind dokumentiert (`docs/UMSETZUNGSSTAND.md`, Abschnitt „Bewusst nicht mitgefixt — Farbkontrast"), Design-Token-System (AP-7) macht die spätere Änderung an einer zentralen Stelle möglich |

Zusätzlich unverändert offen, unabhängig von AP-9:

- **E-7 (GPL `Unidecode`):** Release-Blocker, Rechtsfrage — braucht
  Fujitsu/DRV-Freigabe oder Entscheidung für Alternative (siehe
  `docs/ENTSCHEIDUNGEN.md`).
- **`backend/api/projects.py`-Nachfolgearbeiten:** keine offenen Punkte mehr
  bekannt aus AP-9 (beide 500er behoben, siehe AP-9-Abschnitt in
  `docs/UMSETZUNGSSTAND.md`).

## 5. Wie es weitergeht

Sobald ein echter (oder repräsentativer) COBOL-Bestand verfügbar ist:
Lasttest gegen `docs/UMSETZUNGSSTAND.md`-Abschnitt „AP-9 — Härtung" fahren,
Persistenz- und Embedding-Engpässe an realen Zahlen erneut prüfen. Sobald
Fujitsu/DRV Prüfumfang (BITV) bzw. Freigabe (Farbkontrast, `Unidecode`)
liefert, sind die jeweiligen Umsetzungsschritte in `docs/ENTSCHEIDUNGEN.md`
(E-7, E-9) und `docs/UMSETZUNGSSTAND.md` vorgezeichnet.
