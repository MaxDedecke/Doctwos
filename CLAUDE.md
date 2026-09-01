# Claude Instructions — Doctus

Kontext für KI-Agenten, die an Doctus arbeiten.

**Was Doctus ist:** ein On-Premise-Wissensassistent für große COBOL-Bestände.
Nutzer stellen Fragen in natürlicher Sprache, bekommen Antworten mit klickbaren
Quellen im Originalcode, und navigieren Programm→Section→Paragraph sowie den
Aufrufgraphen. Entstanden als Fork des Condo-Templates (AEC/BIM) mit
ausgetauschter Fachlogik — siehe `docs/IMPLEMENTIERUNGSPLAN.md`.

**Vor jeder Arbeit lesen:** `docs/OFFENE_ENTWICKLUNGSPUNKTE.md` (zentrale Liste
offener Änderungen) und `docs/ENTSCHEIDUNGEN.md` (festgelegte Streitpunkte).

## Architekturprinzipien

1. **On-Premise per Default, Cloud nur als Opt-in.** Ab Werk läuft alles lokal
   über Ollama (`http://ollama:11434`). Cloud-LLM-Profile (OpenAI/Gemini/Anthropic)
   sind ein ausdrückliches Opt-in pro Kunde, gated über `cloud_llm_allowed()` in
   `backend/core/config.py` — nie Default.
2. **Strikt Open Source.** Nur MIT/BSD/Apache-2.0. Jede neue Abhängigkeit muss in
   im für AP-9 vorgesehenen Lizenz-/Provenienzartefakt nachgetragen werden
   (Release-Voraussetzung).
3. **Keine zusätzlichen Services.** Kein Neo4j, kein ElasticSearch, keine
   ANTLR-/tree-sitter-Runtime. Jede Komponente kostet OSS-Clearing,
   Offline-Bundle-Aufwand und Betriebsrisiko. **Ausnahme (E-11):** eine
   aktiv genutzte Sprachparser-Grammatik-Runtime (`antlr4-python3-runtime`,
   reines Python, kein JRE im Laufzeit-Image) ist erlaubt, wenn ein Visitor
   die Grammatik-Ausgabe aktiv in `ParseResult` überführt — keine
   Importierung auf Vorrat. Details/Bedingungen: `docs/ENTSCHEIDUNGEN.md`
   E-11.
4. **Skalierung by Default.** Alles muss 100-GB-Monorepos überstehen: streamen
   statt laden, wiederaufsetzbar statt „von vorn", asynchron im Celery-Worker.
5. **Zeilennummern sind heilig.** Jede Entity und jede Kante trägt die physische
   Start-/Endzeile der Originaldatei. Copybooks werden **nie** in den Programmtext
   expandiert — sonst verschieben sich alle Zeilennummern und die Navigation bricht.

## Tech-Stack

- **Frontend:** Next.js (React), Tailwind, Monaco Editor, Framer Motion — `frontend/`
- **Backend:** FastAPI — `backend/`
- **Parser:** Celery-Worker — `parser/`, COBOL-Parser unter `parser/cobol/`
- **DB:** PostgreSQL + pgvector (HNSW, bge-m3 = 1024 Dimensionen)
- **Queue:** Redis/Valkey
- **LLM:** Ollama (`mistral-nemo`), Embeddings `bge-m3`
- **Modell-Duplikat:** `backend/models/database.py` und `parser/models/database.py`
  sind getrennte physische Dateien (getrennte Docker-Build-Kontexte) und müssen
  **byte-identisch** bleiben — dasselbe gilt für `crypto_types.py`. Wer ORM-Modelle
  ändert, ändert beide.

## Umgebung

- DB: `postgresql://admin:password@db:5432/doctus`
- Redis: `redis://redis:6379/0`, Ollama: `http://ollama:11434`
- Frontend: `http://localhost:3000`, Backend: `http://localhost:8000`
- Erststart legt einen Superuser an (`BOOTSTRAP_SUPERUSER`, Passwort aus
  `BOOTSTRAP_SUPERUSER_PASSWORD` oder generiert + einmalig im Startlog).

## Arbeitsweise

- **Branch:** `develop`. `main` bleibt stabilen Releases vorbehalten.
- **Lange Läufe** (Klonen, Parsen, Einbetten) gehören in Celery-Tasks im
  `parser`-Service, nie in einen Request-Handler.
- **Vor dem Stagen:** `npx tsc --noEmit` in `frontend/`, `pytest` in `backend/`
  und `parser/`.
- **Parser-Änderungen:** Golden-File-Tests unter `parser/tests/cobol_corpus/`
  laufen lassen — Regressionen dort sind blockierend (F-033).

## Coding-Regeln

1. `app/page.tsx` bleibt schlank — Unterkomponenten nach `frontend/components/`.
2. UI-lokaler State bleibt in der Komponente, nicht auf Seitenebene.
3. Backend bleibt zustandslos: API-Keys kommen im Request-Payload, nicht in
   globalem Serverstate.
4. Keine schweren SDKs — `httpx` (Python) / `axios` (TS) direkt.
5. Kommentare nur für nicht-offensichtliche Invarianten und Workarounds, nicht
   für das, was der Code ohnehin sagt.
6. `User.password_hash` darf in keinem Serializer, Log oder Diagnose-Bundle
   auftauchen (F-005).
