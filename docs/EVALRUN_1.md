# EVALRUN_1 – Apache Syncope und AWS CardDemo mit RunPod

**Zweck:** Reproduzierbare fachliche und technische Evaluation der bestehenden
Doctus-Projekte Apache Syncope (Java) und AWS CardDemo (COBOL), sobald der
RunPod-Endpunkt bereitgestellt wird. Bei der Aufforderung „Schau dir
`EVALRUN_1.md` an und let's go – hier ist der Pod“ dieses Dokument als
Arbeitsablauf verwenden.

**Status:** Vorbereitet, noch nicht ausgeführt. Kein RunPod-Aufruf und keine
Reindexierung im Rahmen der Vorbereitung.

## Festgelegte Projekte und Indexstand

Stand der Doctus-Datenbankabfrage: 20.09.2026. Beide Quellen waren vollständig
abgeschlossen; die Synchronisation lief zuletzt am 18.09.2026.

| Sprache | Projekt-ID | Quelle-ID | Branch | Git-Commit | Dateien / geparst | Entities | Kanten | Chunks |
|---|---:|---:|---|---|---:|---:|---:|---:|
| Java | 727 – Apache Syncope 2.1.14 | 563 | `syncope-2.1.14` | `84ed68fb63cb05a723a90325aee8d2a2f081b4eb` | 4.648 / 4.458 | 31.036 | 246.468 | 43.829 |
| COBOL | 728 – AWS CardDemo (Mainframe Modernization Reference App) | 564 | `main` | `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e` | 329 / 254 | 10.400 | 6.987 | 3.635 |

Die Chunks beider Quellen sind mit `qwen3-embedding:4b`, Dimension 1024,
gespeichert. Das aktuell aktive Doctus-Profil heißt „RunPod Ollama – Qwen 32B“
(`qwen3:32b`, Protokoll `ollama`); als Embedding-Profil ist „RunPod Qwen
Embedding 4B (1024d)“ mit Kontext 8100 aktiv. Endpunkte und Schlüssel stehen
absichtlich nicht in dieser Datei. Beim Start den tatsächlich bereitgestellten
Pod mit diesen Profilen abgleichen und Zugangsdaten ausschließlich in Doctus'
Profilverwaltung verwenden.

Compose-Dienste waren bei der Vorbereitung gesund. Der Code-Branch stand auf
`65c86f1`; im Worktree lagen Änderungen zu O-273. Für den Lauf zählt der
tatsächlich ausgerollte Stand: Version/SHA aus der laufenden API festhalten und
nicht annehmen, dass der lokale Worktree bereits deployed ist.

### Bekannte Indexlücken vor der Bewertung

- **Syncope:** 87 `.properties`-Dateien stehen im aktuellen Journal noch auf
  `skipped`; der ISO-8859-1-Fallback wurde erst nach der letzten Synchronisation
  ergänzt. Außerdem sind 6 Maven-Dateien als `error` und 15 XML-Dateien als
  `partial` markiert. Vor einer Qualitätsbewertung muss geprüft werden, ob der
  Parser-Worker mit den aktuellen Änderungen ausgerollt ist. Danach Syncope
  erneut verarbeiten und kontrollieren, ob die 87 Resource-Bundles jetzt
  dekodiert und indexiert sind. Die sechs Maven-Fehler bleiben einzeln zu
  prüfen.
- **CardDemo:** 21 COBOL-Dateien sind `complete`, 13 `partial` und 10
  `text_fallback`; 57 Copybooks sind `complete`, 5 `partial`. 61 JCL-Dateien
  liegen als `text_fallback` vor. 13 Binär- und 62 sonstige Textdateien sind
  übersprungen. Das ist der dokumentierte Ist-Stand, kein pauschales
  Parser-Pass/Fail-Kriterium. 62 `COPY`-Kanten sind aktuell unaufgelöst; ein
  Teil davon verweist auf nicht mitgelieferte MQ-Copybooks.
- Beide Quellen zuletzt am 18.09.2026 synchronisiert. Für einen Lauf gegen den
  aktuellen Parserstand zuerst Synchronisationsstatus und Deploy-SHA prüfen.
  Keine Datenbank oder Quelle löschen. Bei einer Reindexierung jeweils nur die
  betroffene Quelle verwenden und den Abschluss samt Fehlerstatus abwarten.
- Das aktive Embedding-Modell entspricht bereits dem in den Chunks gespeicherten
  Modell. Falls der Pod ein anderes Embedding-Modell oder eine andere Dimension
  nutzt, nicht einfach mit gemischten Vektorräumen fortfahren: Profilwechsel
  und notwendige Neueinbettung beider Testquellen zuerst klären.

## Startablauf, sobald der Pod vorliegt

1. **Pod-Daten aufnehmen:** erreichbare Basis-URL, Chat- und Embedding-Pfad,
   Modellkennungen, Protokoll, Auth-Verfahren und Laufzeitfenster erfassen.
   Keine Schlüssel in dieses Markdown oder Git schreiben.
2. **Doctus-Zustand aufnehmen:** laufende API-Version/SHA, Compose-Health,
   aktives Chat- und Embedding-Profil, Quellstatus, letzter Commit und
   Chunk-Modell/Dimension für Projekt 727 und 728 festhalten.
3. **Profile separat prüfen:** Chat-Antwort und Embedding-Aufruf mit dem
   bereitgestellten Pod verifizieren. Kontext, Tool-Aufrufe und 1024
   Embedding-Dimension bestätigen. Erst dann den Fragenkatalog starten.
4. **Indexstand aktualisieren:** aktuelle Parseränderungen ausrollen, falls sie
   noch nicht aktiv sind; danach Syncope wegen der 87 übersprungenen
   `.properties`-Dateien reindizieren. CardDemo nur dann reindizieren, wenn der
   Quellen-/Parserstand nicht dem vereinbarten Laufstand entspricht. Vorher
   aktuellen Status und mögliche Laufzeit prüfen; der frühere CardDemo-Erstlauf
   dauerte laut Backlog etwa 75 Minuten.
5. **Projektweise ausführen:** pro Frage das passende Projekt explizit im Chat
   auswählen. Java-Fragen ausschließlich in Projekt 727, COBOL-Fragen in
   Projekt 728. Je Frage Antwort, Quellenbelege, sichtbare Tool-Schritte und
   Zeiten im Ergebnisprotokoll sichern.
6. **Lastprobe separat kennzeichnen:** nach den Einzelabfragen optional einen
   begrenzten Import-/Chat-Paralleltest ausführen. Chat-First-Token-Zeit,
   Importfortschritt, Wartezeit, Fehler und – soweit vom Pod sichtbar – GPU-
   Auslastung erfassen. Kein unbegrenzter Lasttest.

## Fester Fragenkatalog

Die Fragen wörtlich stellen und Antworten mit Quellenbelegen bewerten. Die
erwarteten Fakten unten dienen als Prüfhilfe, nicht als Text, der dem Modell
vorab gegeben wird. Eine offene oder dynamische Kante darf korrekt als solche
benannt werden; sie darf nicht als aufgelöste Beziehung ausgegeben werden.

### Java – Projekt 727 Apache Syncope

**J1 – Klassen- und Typbeziehungen**

> Erkläre anhand des indizierten Codes, wie `UserServiceImpl` im Modul
> `core/rest-cxf` typisiert ist. Welche Klasse erweitert sie, welches Interface
> implementiert sie, und welche Syncope-Typen nutzt sie? Bitte mit Fundstellen
> und Zeilenangaben.

Prüfpunkte: Datei
`core/rest-cxf/src/main/java/org/apache/syncope/core/rest/cxf/service/UserServiceImpl.java`;
`AbstractAnyService<UserTO,UserPatch>`, `UserService`, `UserDAO` und
`UserLogic` sind im aktuellen Index als Beziehungen vorhanden.

**J2 – REST-Service zu Logik**

> Verfolge in Syncope den Weg von `UserServiceImpl.create` zur fachlichen
> Benutzerlogik. Zeige die belegten Methoden und Kanten. Kennzeichne ausdrücklich,
> welche Aufrufkante aufgelöst ist und welche im Index offen bleibt.

Prüfpunkte: `UserServiceImpl` nutzt `UserLogic`; der aktuelle Graph zeigt bei
`create` unter anderem `logic.create` als unaufgelösten Aufruf. Eine Antwort,
die eine vollständig aufgelöste Aufrufkette behauptet, ist ein Fehler.

**J3 – Maven-Modulbaum**

> Welche Untermodule deklariert `core/pom.xml`, und wie unterscheidet Doctus das
> Modul `logic` dort vom gleichnamigen Modul in `ext/flowable/pom.xml`? Zeige
> beide Quellfundstellen.

Prüfpunkte: Beide `logic`-Module existieren. Die Qualified Names enthalten den
jeweiligen POM-Pfad und dürfen nicht zusammenfallen. Maven wird statisch
analysiert, nicht ausgeführt.

**J4 – XSLT-Struktur**

> Zeige in `core/rest-cxf/src/main/resources/wadl2html/index.xsl` die Templates
> `wadl:resource`, `methods` und `wadl:method`. Welche statisch belegten
> Template-Aufrufe oder Beziehungen verbindet Doctus zwischen ihnen?

Prüfpunkte: Templates und Quellzeilen müssen aus genau dieser XSL-Datei stammen.
Nicht im Graph belegte Aufrufpfade als Lücke melden.

**J5 – Mehrdeutiger Namensraum / Unsicherheit**

> Es gibt mehrere Klassen mit dem einfachen Namen `UserServiceImpl`. Finde die
> Syncope-Kernklasse im Modul `core/rest-cxf`, grenze sie von gleichnamigen
> Klassen in Erweiterungen oder FIT-Tests ab und nenne den vollständigen Pfad.

Prüfpunkte: Erwartet wird die Klasse unter
`core/rest-cxf/src/main/java/org/apache/syncope/core/rest/cxf/service/`;
gleichnamige Erweiterungs- und Testklassen dürfen nicht vermischt werden.

### COBOL – Projekt 728 AWS CardDemo

**C1 – Kontrollfluss im Autorisierungsprogramm**

> Beschreibe den belegten Kontrollfluss von `COPAUA0C.MAIN-PARA`. Welche
> Paragraphen werden ausgeführt und welche Folgeschritte ruft
> `1000-INITIALIZE` auf? Bitte mit Datei- und Zeilenbelegen und mit dem Status
> der Kanten.

Prüfpunkte: Datei
`app/app-authorization-ims-db2-mq/cbl/COPAUA0C.cbl`. `MAIN-PARA` führt unter
anderem `1000-INITIALIZE` und `2000-MAIN-PROCESS` aus; `9000-TERMINATE` ist
unaufgelöst. `1000-INITIALIZE` führt zu `3100-READ-REQUEST-MQ` und
`1100-OPEN-REQUEST-QUEUE`. Der Aufruf `MQOPEN` ist im aktuellen Graph
unaufgelöst.

**C2 – COPY und Copybook-Grenzen**

> Welche Copybooks bindet `COPAUA0C` ein? Trenne aufgelöste Repository-
> Copybooks von nicht aufgelösten MQ-Copybooks und nenne Beispiele für beide
> Gruppen.

Prüfpunkte: Aufgelöste Beispiele sind `CCPAURQY`, `CCPAURLY`, `CCPAUERY`,
`CIPAUSMY`, `CIPAUDTY`, `CVACT03Y`, `CVACT01Y` und `CVCUS01Y`. `CMQODV`,
`CMQMDV`, `CMQV` und weitere MQ-Namen sind im aktuellen Graph unaufgelöst.
Keine externe Definition erfinden.

**C3 – DB2-Embedded-SQL**

> Finde in CardDemo ein konkretes COBOL-Programm mit eingebetteten DB2-SQL-
> Blöcken. Erkläre anhand eines ausgewählten Blocks, welche Tabellen/Felder und
> Operationen der Quelltext tatsächlich belegt; zitiere die Originalzeilen.

Prüfpunkte: `COTRTLIC.cbl` enthält mehrere persistierte `sql_block`-Entities.
Tabellen- und Feldnamen müssen aus dem geöffneten Originalauszug stammen; keine
fachliche Bedeutung allein aus Bezeichnern ableiten.

**C4 – Feldverwendung**

> Verfolge für `COPAUA0C` ein in einem Copybook definiertes Datenfeld bis zu
> einer Verwendung im Programm. Zeige Definition, aufgelöste `COPY`-Beziehung
> und `USES`-Fundstelle. Wenn sich keine durchgängige Kette belegen lässt,
> benenne genau die fehlende Kante.

Prüfpunkte: Definitionen und Verwendungen müssen mit korrekter Quell- und
Zeilenangabe belegt sein; gleiche Namen allein beweisen keine Verbindung.

**C5 – Grenzen und Indexvollständigkeit**

> Welche Teile der CardDemo-Analyse sind strukturell belegt, welche liegen nur
> als Textfallback vor und welche Ziele bleiben dynamisch oder unaufgelöst?
> Nutze ein konkretes Beispiel aus COBOL und eines aus JCL.

Prüfpunkte: JCL ist im aktuellen Import Textfallback; nicht behaupten, daraus
sei ein vollständiger JCL-Jobgraph abgeleitet. Dynamische oder unaufgelöste
Ziele als solche kennzeichnen.

## Bewertung je Frage

Jede Frage mit 0–2 Punkten in drei Kategorien bewerten (maximal 6 Punkte):

| Kategorie | 0 Punkte | 1 Punkt | 2 Punkte |
|---|---|---|---|
| Fundstellen | keine oder falsche Quelle | richtige Datei, aber ungenaue/unvollständige Zeilen | richtige Datei und überprüfbare Zeilen |
| Fachliche Richtigkeit | wesentliche Erfindung oder falsche Beziehung | überwiegend richtig, wichtige Lücke/Unsicherheit fehlt | korrekt und Grenzen passend benannt |
| Doctus-Nachvollziehbarkeit | keine passenden Treffer/Tools | teilweise passende Treffer oder unvollständige Tool-Schritte | passende Recherche, sichtbare Tool-Schritte und nachvollziehbarer Belegpfad |

Zusätzlich pro Antwort First-Token-Zeit, Gesamtdauer, Anzahl der Tool-Aufrufe,
Fehler/Timeout und benötigte Nutzerkorrektur erfassen. Bei nicht belegbaren
Erwartungen den Fall als „Index-/Parserlücke“ protokollieren, nicht als reinen
LLM-Fehler.

## Ergebnisprotokoll

Vor dem Start ausfüllen; RunPod-Schlüssel oder vollständige geheime URLs nicht
eintragen.

| Feld | Wert |
|---|---|
| Datum / Zeitzone | Offen |
| Doctus API-Version und SHA | Offen |
| RunPod GPU / VRAM | Offen |
| Chat-Profil / exakte Modellkennung | Offen |
| Embedding-Profil / exakte Modellkennung / Dimension | Offen |
| Chat- und Embedding-Erreichbarkeit bestätigt | Offen |
| Syncope Reindex-Stand / 87 Properties geprüft | Offen |
| CardDemo Reindex-Stand | Offen |
| Import-/Parser-Metriken | Offen |
| Durchschn. / Median First Token | Offen |
| Durchschn. / Median Antwortzeit | Offen |
| Gesamtpunkte Java (30 mögliche Punkte) | Offen |
| Gesamtpunkte COBOL (30 mögliche Punkte) | Offen |
| Fehlerfälle, Indexlücken und Folge-Todos | Offen |

### Einzelresultate

| Fall | Retrieval-Beleg / Datei + Zeile | Punkte (0–6) | First Token | Gesamtzeit | Tool-Schritte | Befund / Follow-up |
|---|---|---:|---:|---:|---:|---|
| J1 |  |  |  |  |  |  |
| J2 |  |  |  |  |  |  |
| J3 |  |  |  |  |  |  |
| J4 |  |  |  |  |  |  |
| J5 |  |  |  |  |  |  |
| C1 |  |  |  |  |  |  |
| C2 |  |  |  |  |  |  |
| C3 |  |  |  |  |  |  |
| C4 |  |  |  |  |  |  |
| C5 |  |  |  |  |  |  |

## Entscheidung nach dem Lauf

Ergebnis je Sprache getrennt bewerten. Vorab keine pauschale Freigabe aus einer
Gesamtpunktzahl ableiten. Für jede kritische Fehlantwort die Ursache als
Retrieval, Parser/Index, Agenten-Tool-Nutzung, Modellantwort oder fehlendes
Referenzwissen einordnen. Danach priorisierte Folge-Todos mit konkreten
Fundstellen und reproduzierbaren Fällen in `docs/OFFENE_ENTWICKLUNGSPUNKTE.md`
übernehmen.
