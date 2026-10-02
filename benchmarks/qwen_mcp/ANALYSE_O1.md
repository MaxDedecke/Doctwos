# Warum der Index (O(1)) im Benchmark nicht schneller macht — und wie wir ihn besser ausspielen

Stand: 2026-10-02. Grundlage: die 180 Sitzungen aus Kapitel 1 und 2, das MCP-Audit der Datenbank
(`mcp_tool_audit_logs`, 368 Aufrufe) und Messungen am Syncope-Checkout. Keine neuen Modellläufe.
Zahlen zu Luna (Kapitel 2) falls nicht anders genannt.

## 1. Kernaussage

Der Index ist **in der Sache** schnell und skaliert. **Im Ablauf** gewinnt der Agent nichts, weil die
Kosten nicht in der Suche liegen, sondern in den **Modellzügen**. Ein Zug (Modellaufruf plus Nachladen des Kontexts)
kostet 4 bis 6,6 s. Ein Indexzugriff kostet 0,03 bis 0,15 s. Der Index macht aus „O(n) Dateien durchsuchen“ ein
„O(1) Treffer holen“, aber der Agent braucht dafür im Mittel 7,9 Aufrufe statt 4,1 mit der Shell.
Es zählt die **Zahl der Interaktionen**, nicht die Dauer der Suche.

## 2. Messungen

| Messgröße | Wert | Quelle |
|---|---|---|
| Serverzeit je MCP-Aufruf | `get_code_entity` 29 ms, `search_code` 145 ms, `research_project` 122 ms, `get_call_flow` 52 ms | Audit, 368 Aufrufe |
| Serverzeit je Luna-Sitzung | 1,4 s von 35 s Wandzeit (4 %); ohne `search_knowledge` 0,7 s | Audit, 30 Sitzungen |
| Zeit je Modellzug | MCP 4,0 s, Shell 6,6 s (Luna); Qwen 3,2 s und 2,3 s | Kapitel 1 und 2 |
| Zügen je Sitzung | Luna MCP 8,9, Shell 5,1; Qwen MCP 4,4, Shell 5,1 | Kapitel 1 und 2 |
| Skalierung des Index | 13.319 → 100.234 Entitäten (7,5×): `search_code` 100 → 168 ms, `get_code_entity` 25 → 37 ms | Audit je Projekt |
| `grep` über den Quelltext | 48 MB / 5,7k Dateien: 0,057 s; 5×: 0,28 s; 20× (800 MB, 115k Dateien): 1,18 s (linear, ca. 1,5 ms/MB, warmer Cache, GNU `grep`) | eigene Messung |
| Hochrechnung | 100 GB: grob 150 s mit `grep` (nicht gemessen, kalter Datenträger deutlich mehr; `rg` parallel etwa 3 bis 5× schneller) | Extrapolation |
| `search_code`-Antwort | im Mittel 10.800 Zeichen, 89 von 156 serverseitig gekürzt | Audit, Luna-Sitzungen |
| `search_knowledge` | Mittel 1,9 s, p95 8,3 s (Embedding-Modell wird im 8-GB-VRAM nachgeladen), 22 s von 42 s Serverzeit | Audit |

Folgerungen:

1. **Im Benchmark kann sich der Index-Vorteil gar nicht zeigen.** Bei 48 MB braucht `grep` 57 ms, `search_code` 145 ms.
   Der Index ist dort pro Aufruf langsamer als die Dateisuche. Erst ab etwa 100 MB wäre die Suche im Index schneller, und
   erst ab einigen GB fiele sie gegenüber der Modellzeit (4 bis 6 s je Zug) ins Gewicht.
2. **Der Index skaliert wie versprochen** (sublinear, grob logarithmisch). Der Beweis für O(1) gegen O(n) braucht aber einen
   Bestand im zweistelligen GB-Bereich, wie ihn der Zielkunde hat.
3. **Der Engpass ist die Interaktionszahl.** Je Aufgabe braucht Luna mit MCP 3,8 bis 11,8 Aufrufe, mit der Shell 3,0 bis 5,4.
   Bei C3 sind es 10,2 gegen 3,6, bei J2 11,8 gegen 5,4.

## 3. Wo die Interaktionen verloren gehen

1. **Kette Suche → ID → Entität → nächste Entität.** Häufigster Übergang bei Luna ist `get_code_entity → get_code_entity`
   (68 mal), danach `search_code → get_code_entity` (30). Im Schnitt 3,7 Entitätsabrufe je Sitzung. Die Shell liest
   dagegen mit einem `sed -n 1,260p` einen zusammenhängenden Block in **einem** Zug.
2. **Blättern statt Nachschlagen.** 43 von 110 `get_code_entity`-Aufrufen betreffen eine bereits geholte Entität
   (33 mit anderen Zeilenbereichen, 10 als Folgeseite per Chunk-Cursor). Der Agent liest also seitenweise wie in einer Datei.
3. **Dicke, gekürzte Treffer.** `search_code` liefert im Mittel 10.800 Zeichen, in 57 % der Fälle gekürzt. Das ist
   viel Eingabe mit niedriger Dichte und löst oft einen Folgeaufruf aus.
4. **Leere Anfragen.** Bei Java gab es in 9 von 15 Sitzungen mindestens eine leere Suche, weil `Klasse.methode` nicht
   gefunden wird (nur `Klasse#methode`) und Mehrwortanfragen wie `authenticate AuthDataAccessor` leer bleiben. Luna
   gleicht das mit Umformulierungen aus (Schritte, keine Qualität), Qwen scheitert daran.
5. **Kein Hinweis wird zum Abkürzer.** `follow_up_actions` nennt den nächsten Aufruf, aber das Modell muss ihn trotzdem
   als eigenen Zug ausführen. Qwen ignoriert ihn meist.
6. **Konfiguration.** `search_knowledge` kostet im Schnitt 1,9 s, weil `bge-m3` auf der 8-GB-GPU aus dem Speicher
   verdrängt und neu geladen wird. Das ist ein Betriebsproblem, kein Konzeptproblem.

## 4. Was mehr Effizienz bringen könnte (Obergrenze, nicht kausal)

Luna-Sitzungen mit höchstens 5 MCP-Aufrufen erreichen Rubrik 0,96 bei 23 s und 76.000 Eingabe-Tokens, Sitzungen mit
mindestens 12 Aufrufen Rubrik 0,85 bei 49 s und 195.000 Tokens. **Achtung:** Die effizienten Sitzungen stammen überwiegend
von leichten Aufgaben (C1: 5, J3: 3, C2: 2 von 10). Der Vergleich ist mit der Aufgabe vermischt und zeigt nur, dass
wenige Züge möglich sind. Würde jede Sitzung wie die effizienten laufen, läge MCP bei etwa 23 s und 76.000 Tokens und damit
vor der Shell (33 s, 81.000). Das ist eine Hypothese, kein Messergebnis.

## 5. Empfehlungen, nach erwartetem Hebel geordnet

| Nr. | Maßnahme | Wirkung | Messung |
|---|---|---|---|
| 1 | **Ein-Aufruf-Kontext** (`explain_symbol` oder `get_context`): Symbol in toleranter Schreibweise → aufgelöste Entität, vollständiger Quelltext der Methode bzw. des Paragraphen mit Zeilennummern, ein Hop Aufrufer und Aufgerufene mit je wenigen Zeilen, Datenzugriffe, alles in einer Antwort mit festem Budget (6 bis 8 k Zeichen) | ersetzt Suche → ID → Entität → Entität; Ziel: Median höchstens 3 Aufrufe | Prototyp, Kapitel 3 mit gleichen Aufgaben |
| 2 | **Auflösung nach Name statt ID**: `get_code_entity` nimmt `qualified_name`, Datei plus Zeile oder mehrere Namen gleichzeitig (Batch mit Gesamtbudget) | spart je Entität einen Zug, entfernt das Blättern | Anteil Folgeaufrufe auf dieselbe Entität (heute 39 %) |
| 3 | **Tolerante Auflösung**: `Klasse.methode` ↔ `Klasse#methode`, Mehrwortanfragen mit Rückfall, bei leerer Antwort „meintest du“ mit Kandidaten | beseitigt die Java-Lücke (heute 9 von 15 Sitzungen) | Anteil leerer Suchen, Qwen-J-Aufgaben |
| 4 | **Dichte Treffer**: `search_code` liefert je Treffer Signatur, Datei:Zeile und eine Zeile Zusammenfassung (ca. 150 Zeichen) statt 10.800 Zeichen mit 57 % Kürzung; Quelltext nur für den besten exakten Treffer | weniger Eingabe, weniger Kürzung | Zeichen je Antwort, Kürzungsrate |
| 5 | **Fakten beim Indexieren berechnen** (die eigentliche „O(1)“-Chance): je Programm bzw. Methode Einstiege, gelesene und geschriebene Dateien, ausgehende Aufrufe und Weiterleitungen (z. B. `XCTL`-Ziele), Bedingungen, Fehlercodes und Meldungstexte als strukturierte Karte. `describe_symbol` liefert sie als Nachschlagewert | verschiebt Erkundung von der Abfragezeit in die Indexzeit; hätte C1 (Weiterleitung nach Benutzertyp) und C3 (Ablehnungscodes, `DALYREJS`) direkt beantwortet | Rubrik je Aufgabe, vor allem bei Qwen |
| 6 | **Nächsten Schritt serverseitig mitliefern** statt `follow_up_actions`: Standardantworten enthalten bei eindeutigem Treffer bereits die Quelle und den ersten Hop | weniger Entscheidungen des Modells | Züge je Sitzung |
| 7 | **Embedding-Modell dauerhaft im Speicher** halten oder Symbolanfragen zuerst lexikalisch beantworten | `search_knowledge` von 1,9 s (p95 8,3 s) auf deutlich unter 1 s | Audit-Dauer |

Die Maßnahmen 1, 2, 4 und 6 senken die **Zahl der Züge** und die **Eingabe je Zug** und damit genau die beiden Größen,
die Zeit und Tokens bestimmen. Maßnahme 3 hilft vor allem schwachen Modellen, Maßnahme 5 hebt die Qualität.

## 6. Wie man den O(1)-Vorteil wirklich zeigt

1. **Maßstab:** Ein Bestand im zweistelligen GB-Bereich (Generator `scripts/generate_synthetic_cobol_corpus.py`
   oder mehrere Repositories). Gemessen wird die Zeit je Werkzeugaufruf (Index gegen `grep`/`rg`) über 1 GB, 10 GB, 50 GB.
2. **Kapitel 3 mit Prototyp:** Dieselben sechs Aufgaben, MCP mit Maßnahmen 1 bis 4 gegen heutiges MCP, gleiche Modelle.
   Primärgrößen: Züge je Sitzung, Wandzeit, Eingabe-Tokens. Das trennt „Index“ von „Schnittstelle“.
3. **Schwerere Aufgaben:** Luna liegt in beiden Werkzeugwegen an der Obergrenze (92 bis 95 %). Ein Vorteil von MCP ist
   nur mit Fragen messbar, die über viele Dateien gehen (Aufrufkette über mehrere Module, Auswirkungsanalyse).

## 7. Grenzen dieser Analyse

* Der Bestand ist klein (48 MB, 5,7k Dateien). Aussagen zum Maßstab sind gemessene Extrapolation, kein Messwert bei 100 GB.
* `grep` wurde mit warmem Cache und GNU `grep` gemessen, nicht mit `rg` und nicht auf kaltem Datenträger.
* Die Beziehung „weniger Aufrufe ↔ bessere Antworten“ ist mit der Aufgabenschwierigkeit vermischt.
* Serverzeiten stammen aus dem Audit und enthalten keine Netzwerk- und Modellzeit.
* Alle Empfehlungen sind Hypothesen; ihr Nutzen ist nicht gemessen.
