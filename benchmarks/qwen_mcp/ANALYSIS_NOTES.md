# Nachträgliche Ergänzungen der Auswertung (explorativ)

Das eingefrorene Protokoll (`PROTOCOL.md`, `tasks.json`, siehe `manifest.lock`) blieb unverändert.
Folgende Auswertungsgrößen wurden **nach** Beobachtung der ersten 10 Sitzungen ergänzt und sind explorativ:

* **Werkzeug genutzt** (Anteil der Sitzungen mit mindestens einem Werkzeugaufruf). Anlass: Im lokalen Arm
  beantwortete Qwen3-8B mehrere Fragen ohne einen einzigen Aufruf und behauptete, der Code sei nicht im
  Repository. Die Kennzahl trennt „Werkzeug schlecht genutzt“ von „Werkzeug gar nicht genutzt“.
  Sie ist rein aus den Rohdaten ableitbar; keine Sitzung wurde dafür geändert oder wiederholt.

* **Ersetzte Sitzung:** `J1-AUTHENTICATE / none / rep4` scheiterte mit HTTP 500, weil der Linux-OOM-Killer in WSL
  den Ollama-Runner beendete (Arbeitsspeicher 7,7 GB erschöpft, Swap). Das ist ein Infrastrukturfehler, kein
  Modellergebnis. Die Sitzung wurde mit identischem Seed (1003+… = 1004), Konfiguration und Prompt wiederholt.
  Rohdaten: `results/raw/main_run.jsonl` (Original, unverändert), `main_run_rerun65.jsonl` (Wiederholung),
  `main_run_final.jsonl` (zusammengeführt, Grundlage der Auswertung).

## Kapitel 2 (Codex CLI, gpt-6-luna)

* **Korrektur im eingefrorenen Protokoll (`PROTOCOL_CH2.md`, Abschnitt 3):** Dort steht, der Codex-Systemtext umfasse
  „≈ 40 000 Tokens je Sitzung“. Das stammt aus einem Pilot und ist falsch. Gemessen: Der Arm `none` (ein Modellaufruf,
  keine Werkzeuge) hat im Mittel 8 193 Eingabe-Tokens. Die 80 000 bis 130 000 Eingabe-Tokens der Arme `local` und `mcp`
  entstehen durch mehrere Modellaufrufe je Sitzung (die Eingabe wird je Aufruf neu gezählt, rund 80 % davon aus dem
  Zwischenspeicher des Anbieters). Das Protokoll wurde nicht nachträglich geändert (Prüfsumme).
* **Keine Abweichungen im Lauf:** 90 von 90 Sitzungen ohne Fehler, ohne Zeitüberschreitung, ohne Leckage-Markierung.
* **Deckeneffekt:** `local` und `mcp` erreichen bei Luna 100 % Nutzbarkeit; die Rubrik trennt dort kaum.
