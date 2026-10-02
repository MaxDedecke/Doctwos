# Kapitel 2 — Codex CLI mit GPT-6-Luna (Reasoning medium): Protokoll (vorab festgelegt)

Stand: 2026-10-02. Kapitel 2 wiederholt Kapitel 1 (`PROTOCOL.md`) **unverändert**, mit einem anderen Modell
und dessen Agenten-Laufzeit. Gleich bleiben: `tasks.json` (Aufgaben, Rubrik, Schwellen; Hash unverändert),
Arme, Wiederholungen (5), Reihenfolgeplan (gleicher Seed), Auswertung (`analyze.py`, `report_data.py`).
Dieses Dokument und `tasks.json` werden vor dem ersten Lauf per SHA-256 in `manifest_ch2.lock` eingefroren.

## 1. Was sich ändert (und nur das)

| | Kapitel 1 | Kapitel 2 |
|---|---|---|
| Modell | Qwen3-8B (Q4), lokal in Ollama | `gpt-6-luna`, `model_reasoning_effort = medium`, Cloud (ChatGPT-Konto) |
| Agenten-Laufzeit | eigener Harness, max. 10 Züge | **Codex CLI 0.160.0** (`codex exec`), eigene Schleife, Sitzungs-Timeout 600 s |
| Sampling | T = 0,3, Seed 1000 + Wdh. | nicht steuerbar; keine Seeds |
| Kontext | 8 192 Tokens | vom Modell/CLI verwaltet |
| Lokale Werkzeuge (Arm `local`) | `list_dir`, `grep`, `read_file` | Codex-Shell (`bash`, u. a. `rg`, `sed`, `cat`), Sandbox `read-only`, Arbeitsverzeichnis = Checkout |
| Werkzeugausgabe | hart auf 6 000 Zeichen gekürzt | von Codex verwaltet, kein eigenes Limit |

Hinweis zur Vergleichbarkeit: Der lokale Arm ist ein anderes (mächtigeres) Werkzeug als in Kapitel 1.
Kapitel-übergreifende Vergleiche sind **beschreibend**; es gibt keinen Test zwischen den Modellen.

## 2. Arme (äquivalent zu Kapitel 1)

| Arm | Aufbau |
|---|---|
| `none` | Shell-Werkzeug und alle Plugins abgeschaltet, kein MCP, leeres Arbeitsverzeichnis |
| `local` | Shell-Werkzeug aktiv, Sandbox `read-only`, Arbeitsverzeichnis = gepinnter Checkout, kein MCP |
| `mcp` | Doctus-MCP (`http://localhost:8000/mcp`, Bearer-Token), Shell-Werkzeug abgeschaltet, leeres Arbeitsverzeichnis |

In allen Armen: `web_search` aus; Apps, Plugins, Browser, Computer-Use, Bildgenerierung, Memories, Goals,
Skill-Suche, Tool-Vorschläge abgeschaltet; isoliertes `CODEX_HOME` mit leerer Konfiguration; kein
`AGENTS.md`; `--ephemeral`. Der Prompt ist derselbe Text wie in Kapitel 1: gemeinsamer Systemtext,
armspezifischer Hinweis (`project_id` bzw. Verzeichnisse der Wurzel), Frage.

## 3. Mess- und Auswertungsgrößen

Wie Kapitel 1 (Rubrikwert, Nutzbarkeit, Wandzeit, Tokens, Werkzeugaufrufe, -fehler, leere Treffer,
Belegtreue). Abbildung auf die Codex-Ereignisse (`--json`):

* Tokens Prompt = `input_tokens` (inkl. zwischengespeicherter Tokens), Tokens Antwort = `output_tokens`.
  Tokenizer und der große Codex-Systemprompt (≈ 40 000 Tokens je Sitzung) unterscheiden sich von Kapitel 1:
  **Token-Zahlen sind nur innerhalb des Kapitels vergleichbar.**
* Werkzeugaufruf = MCP-Aufruf (`mcp_tool_call`) oder Shell-Befehl (`command_execution`). Shell-Befehl mit
  Exit-Code 1 und leerer Ausgabe zählt als leerer Treffer, jeder andere Exit-Code ≠ 0 als Fehler.
* Antwort = letzte Agentennachricht.
* „Erzwungener Abschluss“ entfällt (es gibt kein Zug- oder Kontextlimit des Harness): Wert 0.

## 4. Zusätzliche Vorkehrung gegen Leckage

Im lokalen Arm ist das Dateisystem lesbar. Daher wird der Checkout in ein neutrales Verzeichnis außerhalb des
Repositories kopiert, und jeder Shell-Befehl wird auf Pfade außerhalb des Arbeitsverzeichnisses sowie auf
Benchmarkbegriffe (`benchmarks`, `Doctwos`, `tasks.json`, `ground_truth`, `.env`) geprüft. Treffer werden
je Sitzung als `leak_flag` protokolliert und im Bericht ausgewiesen; flaggte Sitzungen bleiben in der
Hauptauswertung, werden aber zusätzlich ohne sie berichtet.

## 5. Datenabfluss

Frage, Werkzeugausgaben (Auszüge aus den **öffentlichen** Open-Source-Repositories CardDemo und Syncope) und
Antworten gehen an den Modellanbieter. Bei Kapitel 1 verließen keine Daten den Rechner. Das MCP-Token bleibt
lokal (Verbindung nur zu `localhost`).

## 6. Zusätzliche Gültigkeitsgrenzen

1. Kein Seed, keine Temperaturkontrolle: Streuung zwischen Wiederholungen ist modellbedingt.
2. Cloud-Latenz, Rate-Limits und Serverlast fließen in die Wandzeit ein; Zeiten sind nicht mit Kapitel 1 vergleichbar.
3. Prompt-Caching des Anbieters verkleinert den Eingabeaufwand; Tokens sind nicht kostenäquivalent zu Kapitel 1.
4. Das Modell kann den Benchmark-Code aus dem Training kennen (öffentliche Repositories); der Arm `none`
   misst dieses Vorwissen ausdrücklich mit.
5. Alle Grenzen aus Kapitel 1 (sechs Aufgaben, Regex-Rubrik, Indexqualität = Teil der MCP-Messung) gelten fort.
