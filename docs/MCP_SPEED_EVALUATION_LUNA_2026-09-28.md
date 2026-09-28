# Kapitel 5 – Codex-Laufzeit mit und ohne Doctus-MCP (GPT-6 Luna)

## Aufbau

Am 28.09.2026 wurden drei randomisierte Paare mit Codex CLI 0.158.0 und
ausschließlich `gpt-6-luna` (Reasoning `high`) ausgeführt. Jede der sechs
Messungen lief in einer frischen, ephemeral Codex-Sitzung mit read-only
Sandbox. Der identische CardDemo-Incident-Prompt verlangte `research_project`
und `get_call_flow`, falls Doctus MCP verfügbar war, und lokale Quelltextprüfung
in beiden Armen. Die MCP-Sitzungen verwendeten einen kurzlebigen Testtoken,
der nach dem letzten Lauf widerrufen wurde.

Gemessen wurde die Wandzeit von direkt vor `codex exec` bis Prozessende,
einschließlich CLI-/MCP-Verbindungsaufbau, Modellgenerierung und Toolwartezeit.
Die Reihenfolge wurde je Paar mit Seed `20260928` randomisiert.

## Laufzeiten

| Paar | Ohne Doctus-MCP | Mit Doctus-MCP | Differenz (MCP schneller +) |
|---:|---:|---:|---:|
| 1 | 181,3 s | 80,1 s | +101,2 s |
| 2 | 146,0 s | 110,7 s | +35,3 s |
| 3 | 105,5 s | 153,8 s | −48,3 s |
| **Median** | **146,0 s** | **110,7 s** | **+35,3 s** |
| Mittelwert | 144,3 s | 114,9 s | +29,4 s |

Der MCP-Median lag in diesem kleinen Versuch 24 % niedriger (1,32× so schnell);
der MCP-Mittelwert lag 20 % niedriger. Doctus war in zwei von drei Paaren
schneller, im dritten jedoch 48,3 Sekunden langsamer. Die MCP-Zeiten streuten
von 80,1 bis 153,8 Sekunden. Das spricht in diesem Szenario für einen möglichen
Zeitvorteil, belegt bei nur drei Paaren aber keinen stabilen allgemeinen
Beschleunigungseffekt.

Luna rief in jedem MCP-Lauf tatsächlich `list_visible_projects`,
`research_project` und `get_call_flow` auf (neun MCP-Aufrufe insgesamt); im
Kontrollarm gab es keine MCP-Aufrufe. Die Toolresultate lokalisierten COPAUA0C
und den Call-Flow-Einstieg. Die Antwortqualität wurde nach derselben
11-Punkte-Fallrubrik manuell bewertet:

| Arm | Paar 1 | Paar 2 | Paar 3 | Mittel |
|---|---:|---:|---:|---:|
| Ohne Doctus-MCP | 8/11 | 8/11 | 8/11 | 8,0/11 |
| Mit Doctus-MCP | 8/11 | 7/11 | 8/11 | 7,7/11 |

Alle sechs Antworten trafen die Kernentscheidung und vermieden eine Behauptung
erfolgreicher IMS-Persistenz ohne Laufzeitbeleg. Alle sechs verfehlten jedoch
die Unsicherheit, ob `PA-TRANSACTION-AMT` beim Summary-Update bereits den
konkreten Antragsbetrag enthält. Die MCP-Antwort in Paar 2 ließ zusätzlich die
Fehler-/Statusgrenze beim MQ-Versand aus. Ein Qualitätsgewinn durch MCP ist in
diesen Antworten nicht sichtbar.

## Einordnung

Für diese Fallfrage war Luna mit Doctus MCP im Median schneller, die
Einzelzeiten waren aber uneinheitlich und die Rubrikwerte praktisch gleich.
Das Ergebnis gilt nur für diesen Prompt, diesen Checkout und diese lokale
MCP-/Modellkonfiguration. Es ist ein explorativer Laufzeitvergleich, keine
allgemeine Aussage zur Geschwindigkeit von Luna oder zum Qualitätsgewinn von
Doctus. Details und CLI-Ausgaben der sechs Läufe liegen unter
`/root/doctus_ab_probe/chapter5_luna_speed_ab/`.
