# Auswertung main_run_final

Modell `qwen3:8b` (Digest 500a1f067a9f), Ollama 0.30.7, Optionen `{"temperature": 0.3, "top_p": 0.9, "num_ctx": 8192, "num_predict": 1500}`, 90 Sitzungen, Pilot: False.

## 1. Kennzahlen je Arm (Mittelwert [Median])

| Kennzahl | none | local | mcp |
|---|---|---|---|
| Rubrikwert (0–1) | 0.18 [0.14] | 0.09 [0.00] | 0.20 [0.09] |
| nutzbar (Rubrik ≥ Schwelle) | 0.00 [0.00] | 0.03 [0.00] | 0.23 [0.00] |
| Antwort geliefert | 1.00 [1.00] | 1.00 [1.00] | 1.00 [1.00] |
| ohne erzwungenen Abschluss | 1.00 [1.00] | 0.70 [1.00] | 0.97 [1.00] |
| Wandzeit s | 13.28 [11.71] | 11.92 [9.76] | 14.30 [11.64] |
| Tokens gesamt | 924.80 [857.00] | 5425.57 [3212.00] | 12242.93 [8689.00] |
| Tokens Prompt (summiert) | 213.67 [216.50] | 4988.67 [2963.00] | 11673.80 [8459.50] |
| Tokens Antwort | 711.13 [653.00] | 436.90 [408.00] | 569.13 [401.00] |
| Werkzeugaufrufe | 0.00 [0.00] | 4.13 [2.50] | 3.40 [3.00] |
| Werkzeug überhaupt genutzt | 0.00 [0.00] | 0.53 [1.00] | 1.00 [1.00] |
| Werkzeugfehler | 0.00 [0.00] | 3.27 [0.00] | 0.30 [0.00] |
| leere Treffer | 0.00 [0.00] | 0.20 [0.00] | 0.93 [0.50] |
| Werkzeugausgabe Zeichen | 0.00 [0.00] | 1007.60 [238.50] | 7077.17 [6023.00] |
| Beleg: Datei existiert | 0.56 [0.67] | 0.82 [1.00] | 0.95 [1.00] |
| Beleg: Zeile plausibel | 1.00 [1.00] | – | – |

## 2. Gepaarte Effekte (Differenz = erster − zweiter Arm)

95-%-KI per Cluster-Bootstrap über Aufgaben (10 000 Ziehungen); p aus exaktem Vorzeichen-Permutationstest über alle (Aufgabe, Wiederholung)-Paare, nicht für Mehrfachvergleiche korrigiert. d_z = standardisierter gepaarter Effekt.

### mcp − local

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | 0.108 | [-0.089; 0.312] | 0.0615 | 0.36 | 30 | 125 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.200 | [-0.067; 0.533] | 0.0703 | 0.41 | 30 | 600 % |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | 0.267 | [-0.067; 0.600] | 0.0215 | 0.51 | 30 | 38 % |
| Wandzeit s | 2.373 | [-4.423; 10.471] | 0.3277 | 0.18 | 30 | 20 % |
| Tokens gesamt | 6817.367 | [340.667; 13776.267] | 0.0006 | 0.68 | 30 | 126 % |
| Tokens Prompt (summiert) | 6685.133 | [650.300; 13319.133] | 0.0005 | 0.69 | 30 | 134 % |
| Tokens Antwort | 132.233 | [-234.200; 560.100] | 0.1932 | 0.24 | 30 | 30 % |
| Werkzeugaufrufe | -0.733 | [-4.333; 2.567] | 0.4216 | -0.15 | 30 | -18 % |
| Werkzeug überhaupt genutzt | 0.467 | [0.133; 0.833] | 0.0001 | 0.92 | 30 | 88 % |
| Werkzeugfehler | -2.967 | [-6.467; 0.467] | 0.0019 | -0.62 | 30 | -91 % |
| leere Treffer | 0.733 | [-0.200; 1.667] | 0.0119 | 0.52 | 30 | 367 % |
| Werkzeugausgabe Zeichen | 6069.567 | [2501.733; 10418.033] | 0.0000 | 1.02 | 30 | 602 % |
| Beleg: Datei existiert | 0.167 | [0.000; 0.667] | 1.0000 | 0.50 | 4 | 20 % |

### mcp − none

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | 0.011 | [-0.104; 0.154] | 0.7640 | 0.06 | 30 | 6 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.233 | [0.000; 0.533] | 0.0156 | 0.54 | 30 | – |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | -0.033 | [-0.133; 0.000] | 1.0000 | -0.18 | 30 | -3 % |
| Wandzeit s | 1.021 | [-3.573; 6.137] | 0.4878 | 0.13 | 30 | 8 % |
| Tokens gesamt | 11318.133 | [7044.833; 16075.467] | 0.0000 | 1.58 | 30 | 1224 % |
| Tokens Prompt (summiert) | 11460.133 | [7387.433; 16106.367] | 0.0000 | 1.66 | 30 | 5364 % |
| Tokens Antwort | -142.000 | [-345.000; 67.867] | 0.0266 | -0.43 | 30 | -20 % |
| Werkzeugaufrufe | 3.400 | [2.900; 3.900] | 0.0000 | 2.85 | 30 | – |
| Werkzeug überhaupt genutzt | 1.000 | [1.000; 1.000] | 0.0000 | – | 30 | – |
| Werkzeugfehler | 0.300 | [0.000; 0.967] | 0.2500 | 0.29 | 30 | – |
| leere Treffer | 0.933 | [0.200; 1.767] | 0.0001 | 0.84 | 30 | – |
| Werkzeugausgabe Zeichen | 7077.167 | [3149.200; 11454.067] | 0.0000 | 1.20 | 30 | – |
| Beleg: Datei existiert | 0.250 | [0.000; 0.500] | 1.0000 | 0.71 | 2 | 33 % |

### local − none

| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |
|---|---|---|---|---|---|---|
| Rubrikwert (0–1) | -0.097 | [-0.199; 0.020] | 0.0090 | -0.48 | 30 | -53 % |
| nutzbar (Rubrik ≥ Schwelle) | 0.033 | [0.000; 0.133] | 1.0000 | 0.18 | 30 | – |
| Antwort geliefert | 0.000 | [0.000; 0.000] | 1.0000 | – | 30 | 0 % |
| ohne erzwungenen Abschluss | -0.300 | [-0.633; 0.000] | 0.0039 | -0.64 | 30 | -30 % |
| Wandzeit s | -1.353 | [-6.196; 2.630] | 0.4684 | -0.14 | 30 | -10 % |
| Tokens gesamt | 4500.767 | [1187.733; 8339.200] | 0.0000 | 0.77 | 30 | 487 % |
| Tokens Prompt (summiert) | 4775.000 | [1459.767; 8432.100] | 0.0000 | 0.85 | 30 | 2235 % |
| Tokens Antwort | -274.233 | [-598.600; -27.367] | 0.0003 | -0.67 | 30 | -39 % |
| Werkzeugaufrufe | 4.133 | [0.833; 7.600] | 0.0000 | 0.92 | 30 | – |
| Werkzeug überhaupt genutzt | 0.533 | [0.167; 0.900] | 0.0000 | 1.05 | 30 | – |
| Werkzeugfehler | 3.267 | [0.133; 6.533] | 0.0002 | 0.74 | 30 | – |
| leere Treffer | 0.200 | [0.000; 0.533] | 0.1250 | 0.33 | 30 | – |
| Werkzeugausgabe Zeichen | 1007.600 | [72.867; 3063.000] | 0.0000 | 0.36 | 30 | – |
| Beleg: Datei existiert | 0.125 | [-0.227; 0.750] | 0.6875 | 0.22 | 8 | 21 % |

## 3. Rubrikwert und Zeit je Aufgabe (Mittel über Wiederholungen)

| Aufgabe | none Rubrik | local Rubrik | mcp Rubrik | none s | local s | mcp s |
|---|---|---|---|---|---|---|
| C1-SIGNON | 0.11 | 0.20 | 0.00 | 5.77 | 9.09 | 9.69 |
| C2-BILLPAY | 0.29 | 0.00 | 0.40 | 11.15 | 5.07 | 21.89 |
| C3-POSTING | 0.13 | 0.00 | 0.45 | 22.71 | 15.87 | 26.05 |
| J1-AUTHENTICATE | 0.26 | 0.23 | 0.23 | 18.60 | 18.88 | 14.92 |
| J2-LOCKOUT | 0.07 | 0.00 | 0.00 | 8.88 | 10.28 | 5.51 |
| J3-CREATE-USER | 0.24 | 0.09 | 0.09 | 12.55 | 12.34 | 7.72 |

## 4. Erfüllte Rubrikitems (Anteil der Sitzungen)

| Aufgabe / Item | none | local | mcp |
|---|---|---|---|
| C1-SIGNON · admin-target | 0/5 | 1/5 | 0/5 |
| C1-SIGNON · user-target | 0/5 | 1/5 | 0/5 |
| C1-SIGNON · selector | 0/5 | 1/5 | 0/5 |
| C1-SIGNON · usrsec-file | 0/5 | 1/5 | 0/5 |
| C1-SIGNON · password-compare | 5/5 | 2/5 | 0/5 |
| C1-SIGNON · xctl | 0/5 | 0/5 | 0/5 |
| C2-BILLPAY · transact-write | 4/5 | 0/5 | 3/5 |
| C2-BILLPAY · acctdat-update | 0/5 | 0/5 | 3/5 |
| C2-BILLPAY · cxacaix-read | 0/5 | 0/5 | 2/5 |
| C2-BILLPAY · txn-id | 0/5 | 0/5 | 0/5 |
| C2-BILLPAY · balance | 4/5 | 0/5 | 4/5 |
| C2-BILLPAY · txn-attrs | 0/5 | 0/5 | 0/5 |
| C2-BILLPAY · nothing-to-pay | 0/5 | 0/5 | 0/5 |
| C3-POSTING · code-100 | 2/5 | 0/5 | 0/5 |
| C3-POSTING · code-101 | 0/5 | 0/5 | 0/5 |
| C3-POSTING · code-102 | 0/5 | 0/5 | 0/5 |
| C3-POSTING · code-103 | 0/5 | 0/5 | 0/5 |
| C3-POSTING · rejects-file | 0/5 | 0/5 | 4/5 |
| C3-POSTING · post-transact | 2/5 | 0/5 | 4/5 |
| C3-POSTING · post-tcatbal | 0/5 | 0/5 | 5/5 |
| C3-POSTING · post-account | 4/5 | 0/5 | 5/5 |
| J1-AUTHENTICATE · special-users | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · lookup-attrs | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · not-found | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · suspended | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · auth-statuses | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · internal-then-passthrough | 5/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · mfa | 5/5 | 5/5 | 5/5 |
| J1-AUTHENTICATE · success-reset | 1/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · failure-increment | 0/5 | 0/5 | 0/5 |
| J1-AUTHENTICATE · result-record | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · caller | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · suspend-call | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · workflow | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · max-attempts | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · account-policy | 0/5 | 0/5 | 0/5 |
| J2-LOCKOUT · strict-greater | 4/5 | 0/5 | 0/5 |
| J2-LOCKOUT · throttler | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · do-create | 5/5 | 5/5 | 5/5 |
| J3-CREATE-USER · before-create | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · invalid-realm | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · entitlement | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · security-checks | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · provisioning | 4/5 | 0/5 | 0/5 |
| J3-CREATE-USER · after-create | 0/5 | 0/5 | 0/5 |
| J3-CREATE-USER · pre-authorize | 0/5 | 0/5 | 0/5 |

## 5. Werkzeugnutzung (Aufrufe gesamt)

- **local**: list_dir ×95, grep ×22, read_file ×7
- **mcp**: search_code ×54, research_project ×23, get_code_entity ×19, search_knowledge ×5, trace_data_access ×1

Auf das Zeichenlimit gekürzte Werkzeugausgaben insgesamt: 21.
