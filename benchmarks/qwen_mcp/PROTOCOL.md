# Qwen3-8B × Doctus-MCP — Benchmark-Protokoll (vorab festgelegt)

Stand: 2026-10-02. Dieses Dokument und `tasks.json` werden vor dem ersten gewerteten Lauf
per SHA-256 in `manifest.lock` eingefroren; der Runner verweigert gewertete Läufe bei Abweichung.
Pilotläufe (`--pilot`) dienen nur dem Test des Harness und gehen nicht in die Auswertung ein.

## 1. Fragestellung

Verbessert die Doctus-MCP-Schnittstelle ein **kleines lokales Modell** (Qwen3-8B, Q4, 8-GB-GPU) bei Fragen
zu großen Codebeständen? Vier getrennte Teilfragen:

| Nr. | Dimension | Frage |
|---|---|---|
| H1 | Qualität | Beantwortet das Modell mit MCP fachlich mehr Rubrikpunkte als ohne? |
| H2 | Geschwindigkeit | Ist die Wandzeit je Antwort mit MCP kürzer? |
| H3 | Token-Effizienz | Verbraucht es mit MCP weniger Tokens (Prompt + Antwort)? |
| H4 | Nutzbarkeit | Wird die Antwort mit MCP überhaupt erst brauchbar (Rubrik ≥ 0,5)? |

Zusätzlich beschreibend: Belegtreue (Existenz zitierter Dateien/Zeilen), Werkzeugdisziplin
(Aufrufanzahl, Fehler, leere Treffer, Kürzungen).
Alle Hypothesen sind zweiseitig; es wird **keine** Richtung unterstellt. Die Codex-Vorarbeit
(TODO O-342 ff.) fand für große Modelle nur ~0,4–4,7 Prozentpunkte Qualitätsgewinn bei
12–22 s Mehraufwand; für 8B ist beides offen.

## 2. Design

Gepaartes Messwiederholungsdesign: 6 Aufgaben × 3 Arme × 5 Wiederholungen = 90 Sitzungen.

| Arm | Werkzeuge | Rolle |
|---|---|---|
| `none` | keine | Kontrollboden: Wissen des Modells allein |
| `local` | `list_dir`, `grep`, `read_file` auf dem gepinnten Checkout | **Hauptkontrolle** (entspricht dem „ohne MCP“-Arm der Codex-Studie: Agent mit Dateizugriff) |
| `mcp` | alle 8 Doctus-MCP-Werkzeuge (Streamable HTTP, Bearer-Token) | Behandlung |

Primärvergleich: `mcp − local`. Sekundär: `mcp − none` und `local − none`.

Konstant über alle Arme: Modell (`qwen3:8b`, Digest wird protokolliert), Systemprompt (bis auf den
armspezifischen Werkzeughinweis), Frage, Sampling (`temperature 0.3, top_p 0.9`), `think=false`,
`num_ctx 8192` (Produktstandard von Doctus), `num_predict 1500` je Zug, höchstens 10 Zug, Werkzeugausgabe hart auf 6 000 Zeichen gekürzt.
Der Seed einer Sitzung ist `1000 + Wiederholung`. Die Armreihenfolge wird je (Aufgabe, Wiederholung)
zufällig (fester Seed) gemischt, um Drift (GPU-Wärme, Cache) nicht mit einem Arm zu konfundieren.
Ein verworfener Aufwärmlauf lädt die Modelle.

Gleiche Information zur Orientierung: der MCP-Arm erhält die `project_id`, der lokale Arm die
Verzeichnisse der Repository-Wurzel. Beide Arme müssen den Ort der Antwort selbst finden.

Erzwungener Abschluss: erreicht das Modell 10 Zug oder `num_ctx − 1700` Tokens, wird es einmalig
ohne Werkzeuge zur Antwort aufgefordert (`forced_final`), die Sitzung zählt dann als „nicht
ohne erzwungenen Abschluss“. Werkzeugfehler gehen an das Modell zurück (kein Abbruch).

Kontextwahl: `num_ctx 8192` ist der Doctus-Standard und die größte Einstellung, bei der Chat-Modell
(5,6 GB) und Embedding-Modell `bge-m3` (0,66 GB) gleichzeitig vollständig im 8-GB-VRAM bleiben
(gemessen: bei 12 288/16 384 verdrängen sie sich bzw. ein Teil des Chat-Modells läuft auf der CPU, was die
Zeitmessung verfälschen würde). Die Wahl wurde nach einem Pilot an einer Aufgabe und einer Hardwareprüfung
getroffen, **vor** dem ersten gewerteten Lauf. Der kleine Kontext bestraft werkzeugausgabenreiche Arme
bewusst realistisch; dazu dient der Kennwert „erzwungener Abschluss“. Eine Sensitivitätsmessung mit
größerem Kontext ist optional und wird getrennt berichtet.

## 3. Aufgaben („Disziplinen“)

Sechs Aufgaben aus zwei Beständen mit festem Commit (CardDemo/COBOL, Syncope/Java), je mit
Ground Truth an Datei und Zeile. Beide Bestände sind vollständig in Doctus indexiert (Stand: Parser
nach Commit `ed19866`/`ab30eee`); Index und Checkout stammen aus demselben Commit.

| Disziplin | Aufgabe | Bestand |
|---|---|---|
| Einfacher Flow | C1-SIGNON | COBOL |
| Datenzugriff | C2-BILLPAY | COBOL |
| Regeln und Batch | C3-POSTING | COBOL |
| Methodenablauf | J1-AUTHENTICATE | Java |
| Aufrufkette | J2-LOCKOUT | Java |
| Create-Pfad | J3-CREATE-USER | Java |

Die Aufgaben wurden vor dem ersten Lauf aus dem Quelltext abgeleitet und nicht an Modellantworten
angepasst. Sie sind damit klein; Aussagen gelten für diese sechs Aufgaben, nicht für „Code-Fragen“
allgemein (siehe Gültigkeitsgrenzen).

## 4. Messgrößen

Primär: **Rubrikwert** je Sitzung = erfüllte Gewichte / Gesamtgewicht (0–1).
Die Rubrik ist deterministisch (Regex-Gruppen je Item, siehe `tasks.json`), **kein LLM-Richter**:
kein Selbstbewertungs-Bias, vollständig reproduzierbar, aber unempfindlich gegen reine Paraphrasen.
Nutzbar = Rubrikwert ≥ 0,5.

Sekundär je Sitzung: Wandzeit; Modellzeit und Werkzeugzeit getrennt; Tokens (Prompt summiert über
alle Züge – Ollama meldet nur neu ausgewertete Tokens, Cache-Treffer sind nicht enthalten –,
Antwort, gesamt); Werkzeugausgabe in Zeichen (cache-unabhängiges Eingabevolumen); Anzahl
Werkzeugaufrufe, -fehler, leere Treffer; Antwort geliefert; erzwungener Abschluss; Belegtreue
(Anteil zitierter Dateien, die im gepinnten Checkout existieren; Anteil zitierter Zeilen innerhalb der Datei).

## 5. Statistik

* Einheit der Paarung: (Aufgabe, Wiederholung) → 30 Paare je Armvergleich.
* Effekt = Mittel der gepaarten Differenzen mit **95-%-Cluster-Bootstrap-KI** (10 000 Ziehungen;
  Aufgaben werden gezogen, innerhalb der Aufgabe die Wiederholungen), standardisiert als d_z.
* Test: exakter Vorzeichen-Permutationstest (zweiseitig). Es gibt 4 Primärkennzahlen
  (Rubrik, Zeit, Tokens, Nutzbarkeit) im Primärvergleich; Bonferroni-Schwelle α = 0,05/4 = 0,0125.
  Alle übrigen p-Werte sind explorativ und unkorrigiert.
* Aufgabenweise Ergebnisse werden **beschreibend** berichtet (n = 5 je Zelle trägt keine Einzeltests).
* Fehlende/abgebrochene Sitzungen werden nicht verworfen: sie gehen mit Rubrikwert der gelieferten
  Antwort (leer = 0) in die Wertung ein.

## 6. Gültigkeitsgrenzen (vorab benannt)

1. **Ein Modell, eine Quantisierung, eine GPU**; Ergebnisse gelten nicht für größere Modelle.
2. **Sechs Aufgaben, zwei Bestände**: begrenzte Breite; Generalisierung nur vorsichtig.
3. **Regex-Rubrik**: kann korrekte, anders formulierte Antworten untererfassen und sprachlich
   passende, fachlich falsche übererfassen. Gegenmaßnahme: großzügige Alternativen, Belegprüfung,
   stichprobenartige manuelle Sichtung (Anhang im Bericht). Eine unabhängige menschliche
   Zweitbewertung steht aus.
4. **Kontrollarm ist ein selbst gebautes Dateiwerkzeug-Trio**, nicht Codex/IDE-Tooling; Ergebnis hängt
   davon ab, wie gut `grep`/`read_file` für 8B gestaltet sind.
5. **MCP-Qualität = Indexqualität + Werkzeugvertrag**: Ein MCP-Verlust kann an Indexlücken, Cursor- und
   Kürzungsverhalten oder am Modell liegen. Der Benchmark misst das Gesamtsystem; Fehlerzuordnung
   (Index/Retrieval/Projektion/Modell) erfolgt qualitativ im Anhang.
6. **Sampling-Varianz** (T = 0,3): fünf Wiederholungen schätzen sie, eliminieren sie nicht.
7. Wandzeit enthält Ollama-Modellzeit, MCP-Serverzeit und Netzwerk (loopback); Lasten anderer
   Prozesse (Import, Backups) wurden während des Laufs vermieden, aber nicht technisch ausgeschlossen.

## 7. Artefakte

`results/raw/<run>.jsonl` (Rohdaten je Sitzung inkl. Werkzeugaufrufe und Antwort),
`results/<run>_report.md` (Tabellen), `results/<run>_report.html` (visueller Bericht),
`manifest.lock` (Hashes), Harness in `harness/`.
