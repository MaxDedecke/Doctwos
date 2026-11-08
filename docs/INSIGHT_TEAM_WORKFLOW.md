# Erkenntnisse im Team pflegen

## Arbeitsablauf

Die Ansicht „Erkenntnisse prüfen“ zeigt standardmäßig offene Prüfaufgaben.
Die Liste lädt 25 Einträge pro Seite. Suche, Status, eigene Verantwortung,
zugewiesene Prüfungen und unzugewiesene Aufgaben werden auf dem Server gefiltert.
Ohne Suchtext stehen überfällige Termine zuerst, danach Priorität,
Prüfstatus, Termin und Alter. Mit Suchtext hat die Textrelevanz Vorrang.
Die Statuszähler beziehen sich auf das ganze Projekt, die Trefferzahl auf die
aktuell gesetzten Filter.

Neue Entwürfe erhalten ihren Autor als Verantwortlichen. Bestehende Erkenntnisse
bleiben unzugewiesen, bis ein Projekt-Admin eine Zuständigkeit festlegt.
Admins können Verantwortlichen, Prüfer, Priorität und Prüftermin ändern.
Verantwortliche dürfen die Aussage und ihre Belege überarbeiten und eine
Prüfung bei einem aktiven Projekt-Admin anfordern. Diese Zuweisung erteilt keine
neuen Freigaberechte. Die Vier-Augen-Regel und die bestehende Ausnahme für
globale Admins bleiben erhalten.

„Details öffnen“ lädt Aussage, Quellenstände, Belege und die letzten 20
Historieneinträge. Beim Überarbeiten werden Codeobjekte, Dateien, andere
Erkenntnisse und CI-Läufe im Projekt gesucht und einzeln hinzugefügt oder
entfernt. Dateibelege besitzen bearbeitbare Zeilenbereiche. Der Server prüft
Projektzugehörigkeit, Fundstellen, Zeilen und CI-Commit. Auch ältere Dokumentchunks
ohne direkte Projekt-ID werden über ihre projektgebundene Quelle geprüft.
Fingerprints stammen aus dem Index; vom Client mitgebrachte Fingerprints werden
nicht als aktuelle Belege übernommen. Alte Aussagen, Belege und Freigaben bleiben
in der Historie erhalten.

Ein überarbeiteter Eintrag wird zum Entwurf. Ist eine referenzierte Erkenntnis
geändert worden, werden freigegebene abhängige Erkenntnisse ebenfalls zur
Prüfung vorgelegt. Reine Zuständigkeitsänderungen verwenden eine eigene
`work_revision` und invalidieren keine fachlichen Erkenntnisreferenzen.

## Persönliche Hinweise

„Meine Hinweise“ ist in der Sidebar und in der Prüfansicht für das ausgewählte
Projekt verfügbar. Hinweise entstehen bei Zuweisung, angeforderter Prüfung,
Quellenänderung, Änderung einer referenzierten Erkenntnis sowie Freigabe/Verwerfen.
Bei Quellenänderungen werden Verantwortlicher und ausgewählter oder bisheriger
Prüfer benachrichtigt. Der Handelnde erhält keinen Hinweis auf seine eigene Aktion.

Die Hinweise werden innerhalb derselben Datenbanktransaktion wie die Änderung
gespeichert. Pro Empfänger, Ereignis und Änderungszyklus wird dedupliziert.
Eine bereits veraltete Erkenntnis erzeugt nicht bei jedem weiteren Commit einen
neuen Hinweis. Beim Freigeben oder Verwerfen werden die bisherigen Aufgabenhinweise
geschlossen. Neue Ereignisse bleiben separat erkennbar.

Das Öffnen eines Hinweises markiert genau diesen als gelesen; „Hinweise als gelesen
markieren“ bestätigt alle eigenen Hinweise dieses Projekts. Die Inbox lädt bis
zu 25 Hinweise und zeigt weitere offene Einträge durch Zähler/Kürzungshinweis.
Bei sichtbarer Anwendung wird einmal pro Minute nachgeladen. Projekt- und
Teamrechte werden bei jedem Abruf erneut geprüft; Antworten sind nicht cachebar.
Es gibt keine externe E-Mail-/Messenger-Zustellung.

## Mehrere geprüfte Erkenntnisse freigeben

Nach dem Öffnen eines freigabefähigen Eintrags lässt er sich für die gemeinsame
Freigabe auswählen. Höchstens 20 Einträge bilden eine Auswahl.
Die ausdrückliche Bestätigung bezieht sich auf jede ausgewählte Aussage und
ihren angezeigten Quellenstand. Der Server prüft pro Eintrag erneut Revision,
Quellenversionen, vollständig indizierten Stand und Vier-Augen-Regel.

Das Ergebnis enthält Erfolg beziehungsweise Konflikt je Eintrag.
Es handelt sich um einzelne Freigaben, nicht um eine atomare Gesamttransaktion.
Eine neue Version wird niemals allein deshalb freigegeben, weil ihre Belegdateien
unverändert sind. Bei zwischenzeitlicher Änderung sind Aktualisierung und erneute
Prüfung erforderlich.

## Relevanz und Begrenzung

Die Textsuche nutzt einen PostgreSQL-GIN-Index und `ts_rank_cd`.
Im Chat-/MCP-Kontext werden Texttreffer und semantische Treffer per
Rangfusion kombiniert; konkrete Belegbeziehungen bleiben ein zusätzlicher Zugang.
Nur freigegebene, aktuelle Erkenntnisse mit passender Quellenbindung gelangen in
den Antwortkontext.

Der vorhandene Parser-Worker aktualisiert alle zwei Minuten bis zu 25 fehlende
oder veraltete Erkenntnis-Embeddings. Unveränderte Texte werden bei erneuter
Freigabe nicht neu eingebettet. Profilidentität und vollständiger Text-Hash
verhindern die Nutzung von Vektoren für andere Texte oder Modellkonfigurationen.
Der Vektor bezieht sich auf höchstens 4.000 UTF-8-Bytes von Titel und Aussage;
das Datenmodell bleibt bei 1.024 Dimensionen. Ein HNSW-Index unterstützt die
begrenzte Kandidatensuche. Eine ungefähre semantische Suche ist kein Anspruch
auf vollständige Treffer.

Fehlt ein passendes Profil oder ist der Embedding-Endpunkt nicht erreichbar,
bleiben indizierte Textsuche und Belegbeziehungen nutzbar. Zusätzliche
Query-Embeddings sind auf drei Sekunden begrenzt; der Standard-Chat verwendet
seinen bereits erzeugten Query-Vektor bei übereinstimmender Konfiguration erneut.
Die Rangfusion arbeitet mit bis zu 40 Kandidaten pro Suchkanal.
Versionsprüfung und Belegbudget gelten danach weiterhin.

Diese Regeln sind technisch regressionsgeprüft. Ein Qualitätsvorsprung der
Modellantworten oder ein bestimmter Teamdurchsatz ist damit nicht zugesichert.

## API und Betrieb

- `GET /projects/{id}/insight-worklist`: Suche, Filter, Priorität,
  `limit` 1–50, `offset` 0–100.000, Trefferzahl und Statuszähler.
- `GET /projects/{id}/insight-assignees`: aktive Projektmitglieder,
  Freigabefähigkeit und eigene Verwaltungsberechtigung; bis zu 500 Kandidaten.
- `GET /projects/{id}/insights/{insight_id}`: Detail mit begrenzter Historienanzeige.
- `PATCH /projects/{id}/insights/{insight_id}/assignment`:
  `expected_revision`, `expected_work_revision` und zu ändernde Zuständigkeiten.
- `POST /projects/{id}/insights/{insight_id}/review`: zusätzlich optional `evidence`;
  beim Überarbeiten mindestens ein und höchstens 50 Belege, Aussage bis 32.000 Zeichen.
- `GET /projects/{id}/insight-evidence-options`: begrenzte Auswahl im Projekt.
- `GET /projects/{id}/insight-notifications` und zugehörige `POST .../read`-Routen:
  persönliche Inbox und Lesebestätigung.
- `POST /projects/{id}/insight-batch-approval`: ausdrückliche Sammelfreigabe.
- Die bisherige `GET .../insights`-Array-API bleibt erhalten, lädt aber höchstens
  100 Einträge; `offset` erlaubt bestehenden Clients weitere Seiten.

Migration `0048_insight_team_workflow` und Modellpaket `1.10.0` benötigen ein
gemeinsames Update von Backend und Parser. Die PostgreSQL-spezifischen
Text-/JSON-Indizes sind für kleine SQLite-Parserfixtures konditional.
Der vorhandene Beat und Parser-Worker führen die Embedding-Pflege aus; neue
Dienste, Bibliotheken und Datenübertragungen an externe Benachrichtigungsdienste
werden dafür nicht benötigt.

Neue Regressionen stehen in `backend/tests/test_insight_maintenance.py`,
`parser/tests/test_insight_embeddings.py` und den Komponentenprüfungen der
Prüfliste, Belegbearbeitung und Inbox. Datenbankmigrationen sind auf einer
isolierten Datenbank vorwärts/rückwärts/vorwärts geprüft.

## Nachweis für diesen Stand

Die Abschlussprüfung bestand mit 954 Backend-Tests (1 Skip), 857 Parser-Tests
(7 Skips) und 1.116 Frontend-Tests. TypeScript, ESLint ohne Fehler,
Design-Token-Prüfung, Ruff und Formatprüfung bestanden.
Die Worklist-Prüfung legt 10.000 Erkenntnisse in einer isolierten Datenbank an
und prüft Reihenfolge, Filter, getrennte Seiten und begrenzte Antworten.
Dies ist ein funktionaler Skalierungsnachweis, keine Mehrbenutzer-Latenzzusage.

Die Tests prüfen außerdem persönliche Lesebestätigungen und Rollen,
Belegüberarbeitung einschließlich Dokumentchunks über Quellenzugehörigkeit,
Quellenänderungen, Projektwissen nach Hinzufügen einer Git-Quelle,
referenzierte Erkenntnisse, Sammelfreigabekonflikte,
profil-/textgebundene Vektoren und Wiederholung des Hintergrundlaufs.
Embeddings und Modellantworten werden in diesen Regressionen simuliert.
