# Auswertung codex_run

Modell `gpt-6-luna` (Digest ?), Ollama None, Optionen `{"reasoning_effort": "medium", "session_timeout": 600}`, 90 Sitzungen, Pilot: False.

## 1. Kennzahlen je Arm (Mittelwert [Median])

| Kennzahl | none | local | mcp |
|---|---|---|---|
| Rubrikwert (0–1) | 0.06 [0.00] | 0.95 [1.00] | 0.92 [0.96] |
| nutzbar (Rubrik ≥ Schwelle) | 0.03 [0.00] | 1.00 [1.00] | 1.00 [1.00] |
| Antwort geliefert | 1.00 [1.00] | 1.00 [1.00] | 1.00 [1.00] |
| ohne erzwungenen Abschluss | 1.00 [1.00] | 1.00 [1.00] | 1.00 [1.00] |
| Wandzeit s | 5.80 [5.37] | 33.43 [33.72] | 35.24 [34.36] |
| Tokens gesamt | 8284.13 [8277.00] | 82164.63 [78083.50] | 128926.87 [122668.00] |
| Tokens Prompt (summiert) | 8193.17 [8193.50] | 80977.63 [76707.00] | 127800.63 [121428.00] |
| Tokens Antwort | 90.97 [79.00] | 1187.00 [1268.50] | 1126.23 [1189.00] |
| Werkzeugaufrufe | 0.00 [0.00] | 4.07 [4.00] | 7.90 [7.00] |
| Werkzeug überhaupt genutzt | 0.00 [0.00] | 1.00 [1.00] | 1.00 [1.00] |
| Werkzeugfehler | 0.00 [0.00] | 0.23 [0.00] | 0.03 [0.00] |
| leere Treffer | 0.00 [0.00] | 0.03 [0.00] | 0.40 [0.00] |
| Werkzeugausgabe Zeichen | 0.00 [0.00] | 69108.07 [66141.50] | 54992.17 [49429.00] |
| Beleg: Datei existiert | 1.00 [1.00] | 1.00 [1.00] | 1.00 [1.00] |
| Beleg: Zeile plausibel | – | 1.00 [1.00] | 1.00 [1.00] |

## 2. Gepaarte Effekte (Differenz = erster − zweiter Arm)

95-%-KI per Cluster-Bootstrap über Aufgaben (10 000 Ziehungen); p aus exaktem Vorzeichen-Permutationstest über alle (Aufgabe, Wiederholung)-Paare, nicht für Mehrfachvergleiche korrigiert. d_z = standardisierter gepaarter Effekt.

### mcp − local

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | -0.032 | [-0.075; 0.009] | 0.0670 | -0.35 | 30 | -3 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Wandzeit s | 1.808 | [-4.460; 7.363] | 0.4098 | 0.15 | 30 | 5 % |
| Tokens gesamt | 46762.233 | [19049.433; 73936.433] | 0.0000 | 0.90 | 30 | 57 % |
| Tokens Prompt (summiert) | 46823.000 | [20062.433; 74928.900] | 0.0000 | 0.90 | 30 | 58 % |
| Tokens Antwort | -60.767 | [-207.500; 90.733] | 0.3116 | -0.19 | 30 | -5 % |
| Werkzeugaufrufe | 3.833 | [1.867; 5.867] | 0.0000 | 1.09 | 30 | 94 % |
| Werkzeug überhaupt genutzt | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Werkzeugfehler | -0.200 | [-0.633; 0.067] | 0.3125 | -0.25 | 30 | -86 % |
| leere Treffer | 0.367 | [0.000; 0.800] | 0.0039 | 0.60 | 30 | 1100 % |
| Werkzeugausgabe Zeichen | -14115.900 | [-41505.500; 12480.767] | 0.0911 | -0.32 | 30 | -20 % |
| Beleg: Datei existiert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Beleg: Zeile plausibel | 0.000 | [0.000; 0.000] | 1.0000 | – | 26 | 0 % |

### mcp − none

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | 0.858 | [0.791; 0.908] | 0.0000 | 5.75 | 30 | 1459 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.967 | [0.867; 1.000] | 0.0000 | 5.29 | 30 | 2900 % |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Wandzeit s | 29.438 | [21.822; 36.989] | 0.0000 | 2.30 | 30 | 508 % |
| Tokens gesamt | 120642.733 | [87583.800; 153964.767] | 0.0000 | 2.14 | 30 | 1456 % |
| Tokens Prompt (summiert) | 119607.467 | [86069.700; 153323.800] | 0.0000 | 2.14 | 30 | 1460 % |
| Tokens Antwort | 1035.267 | [735.067; 1304.000] | 0.0000 | 2.49 | 30 | 1138 % |
| Werkzeugaufrufe | 7.900 | [5.633; 10.267] | 0.0000 | 2.16 | 30 | – |
| Werkzeug überhaupt genutzt | 1.000 | [1.000; 1.000] | 0.0000 | – | 30 | – |
| Werkzeugfehler | 0.033 | [0.000; 0.133] | 1.0000 | 0.18 | 30 | – |
| leere Treffer | 0.400 | [0.067; 0.833] | 0.0020 | 0.64 | 30 | – |
| Werkzeugausgabe Zeichen | 54992.167 | [36739.533; 75480.200] | 0.0000 | 1.89 | 30 | – |
| Beleg: Datei existiert | 0.000 | [0.000; 0.000] | 1.0000 | – | 1 | 0 % |

### local − none

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | 0.891 | [0.816; 0.955] | 0.0000 | 5.78 | 30 | 1514 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.967 | [0.867; 1.000] | 0.0000 | 5.29 | 30 | 2900 % |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| Wandzeit s | 27.630 | [20.267; 34.041] | 0.0000 | 2.49 | 30 | 476 % |
| Tokens gesamt | 73880.500 | [57278.767; 93525.367] | 0.0000 | 2.32 | 30 | 892 % |
| Tokens Prompt (summiert) | 72784.467 | [56634.333; 92561.633] | 0.0000 | 2.30 | 30 | 888 % |
| Tokens Antwort | 1096.033 | [814.967; 1299.567] | 0.0000 | 3.02 | 30 | 1205 % |
| Werkzeugaufrufe | 4.067 | [3.400; 4.867] | 0.0000 | 2.98 | 30 | – |
| Werkzeug überhaupt genutzt | 1.000 | [1.000; 1.000] | 0.0000 | – | 30 | – |
| Werkzeugfehler | 0.233 | [0.000; 0.667] | 0.1250 | 0.30 | 30 | – |
| leere Treffer | 0.033 | [0.000; 0.133] | 1.0000 | 0.18 | 30 | – |
| Werkzeugausgabe Zeichen | 69108.067 | [47739.433; 91447.200] | 0.0000 | 1.77 | 30 | – |
| Beleg: Datei existiert | 0.000 | [0.000; 0.000] | 1.0000 | – | 1 | 0 % |

## 3. Rubrikwert und Zeit je Aufgabe (Mittel über Wiederholungen)

| Aufgabe | none Rubrik | local Rubrik | mcp Rubrik | none s | local s | mcp s |
|---|---|---|---|---|---|---|
| C1-SIGNON | 0.13 | 0.96 | 0.93 | 5.50 | 17.35 | 20.03 |
| C2-BILLPAY | 0.00 | 0.93 | 0.89 | 5.21 | 32.67 | 39.31 |
| C3-POSTING | 0.00 | 1.00 | 0.90 | 5.37 | 37.11 | 42.68 |
| J1-AUTHENTICATE | 0.09 | 0.92 | 0.92 | 6.31 | 43.76 | 37.94 |
| J2-LOCKOUT | 0.04 | 0.91 | 0.87 | 5.64 | 36.14 | 43.98 |
| J3-CREATE-USER | 0.09 | 0.98 | 0.98 | 6.77 | 33.55 | 27.49 |

## 4. Erfüllte Rubrikitems (Anteil der Sitzungen)

| Aufgabe / Item | none | local | mcp |
|---|---|---|---|
| C1-SIGNON · admin-target | 1/5 | 5/5 | 5/5 |
| C1-SIGNON · user-target | 1/5 | 5/5 | 5/5 |
| C1-SIGNON · selector | 0/5 | 5/5 | 5/5 |
| C1-SIGNON · usrsec-file | 1/5 | 5/5 | 5/5 |
| C1-SIGNON · password-compare | 0/5 | 5/5 | 4/5 |
| C1-SIGNON · xctl | 0/5 | 3/5 | 3/5 |
| C2-BILLPAY · transact-write | 0/5 | 5/5 | 5/5 |
| C2-BILLPAY · acctdat-update | 0/5 | 5/5 | 5/5 |
| C2-BILLPAY · cxacaix-read | 0/5 | 5/5 | 5/5 |
| C2-BILLPAY · txn-id | 0/5 | 3/5 | 2/5 |
| C2-BILLPAY · balance | 0/5 | 5/5 | 5/5 |
| C2-BILLPAY · txn-attrs | 0/5 | 5/5 | 5/5 |
| C2-BILLPAY · nothing-to-pay | 0/5 | 5/5 | 5/5 |
| C3-POSTING · code-100 | 0/5 | 5/5 | 5/5 |
| C3-POSTING · code-101 | 0/5 | 5/5 | 5/5 |
| C3-POSTING · code-102 | 0/5 | 5/5 | 5/5 |
| C3-POSTING · code-103 | 0/5 | 5/5 | 5/5 |
| C3-POSTING · rejects-file | 0/5 | 5/5 | 2/5 |
| C3-POSTING · post-transact | 0/5 | 5/5 | 5/5 |
| C3-POSTING · post-tcatbal | 0/5 | 5/5 | 5/5 |
| C3-POSTING · post-account | 0/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · special-users | 0/5 | 3/5 | 4/5 |
| J1-AUTHENTICATE · lookup-attrs | 0/5 | 5/5 | 4/5 |
| J1-AUTHENTICATE · not-found | 0/5 | 5/5 | 4/5 |
| J1-AUTHENTICATE · suspended | 0/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · auth-statuses | 0/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · internal-then-passthrough | 1/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · mfa | 4/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · success-reset | 0/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · failure-increment | 0/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · result-record | 0/5 | 2/5 | 3/5 |
| J2-LOCKOUT · caller | 0/5 | 5/5 | 5/5 |
| J2-LOCKOUT · suspend-call | 0/5 | 5/5 | 5/5 |
| J2-LOCKOUT · workflow | 0/5 | 4/5 | 3/5 |
| J2-LOCKOUT · max-attempts | 1/5 | 4/5 | 4/5 |
| J2-LOCKOUT · account-policy | 0/5 | 4/5 | 4/5 |
| J2-LOCKOUT · strict-greater | 0/5 | 5/5 | 4/5 |
| J2-LOCKOUT · throttler | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · do-create | 5/5 | 5/5 | 5/5 |
| J3-CREATE-USER · before-create | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · invalid-realm | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · entitlement | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · security-checks | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · provisioning | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · after-create | 0/5 | 5/5 | 5/5 |
| J3-CREATE-USER · pre-authorize | 0/5 | 4/5 | 4/5 |

## 5. Werkzeugnutzung (Aufrufe gesamt)

- **local**: shell ×122
- **mcp**: get_code_entity ×110, search_code ×86, research_project ×18, search_knowledge ×18, get_call_flow ×5

Auf das Zeichenlimit gekürzte Werkzeugausgaben insgesamt: 0.
