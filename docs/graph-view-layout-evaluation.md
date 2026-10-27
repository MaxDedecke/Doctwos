# Wissensgraph: Evaluation der Bedienoberfläche

Stand: 27.10.2026, lokales Produktionsfrontend nach Commit `dc5e389`.

## Befund

Die vorhandenen Funktionen lassen sich erhalten. Das Hauptproblem ist die fehlende Trennung zwischen dauerhaft sichtbaren Werkzeugen, Filtern und kontextabhängigen Aktionen. Die Toolbar wächst durch Zeilenumbrüche nach unten; ihre rechte Bediengruppe kann gleichzeitig seitlich abgeschnitten werden. Die Auswahl zwischen seitlichem Detailbereich und unterem Drawer berücksichtigt nur die Anzahl der Views.

Empfehlung: tatsächliche Panelbreite **und** Panelhöhe als Grundlage verwenden, der Toolbar ein begrenztes Platzbudget geben und die vollständigen Filter sowie Details bei Bedarf in gezielt geöffneten Bereichen anbieten. Eine kleinere Schrift oder ein pauschales Drei-Punkte-Menü für alle Funktionen würde die Bedienung verschlechtern.

## Methode und Grenzen

Playwright gegen das lokal laufende Produktionsfrontend; acht Kombinationen aus Fenstergröße, View-Anzahl und Split-Verhältnis. Die API wurde ausschließlich im Testbrowser abgefangen. Testdaten: vier dargestellte Knotenkategorien, sieben übliche Beziehungsfamilien, drei Kantenrichtungen und zwei Quellen mit langen Namen. Eine Dokumentauswahl öffnete die vorhandenen Detailbereiche. Zusätzlich wurden in den kompakten Layouts Details und Legende geöffnet, bei 1440×900 auch die Nachbarschaft mit „Weitere Verbindungen laden“.

Die Messungen zeigen das Verhalten der echten UI mit kontrollierten Daten, keine Statistik über reale Projekte. Alle Angaben sind gerundete CSS-Pixel bei aktueller UI-Skalierung, offener App-Seitenleiste und deutscher Sprache. Die Canvas-Höhe ist die Größe **vor** darüberliegenden Detail- und Legendenflächen. Die global mit dem Viewport wachsende rem-Basis beeinflusst auch große Bildschirmgrößen.

[Messwerte](evidence/graph-layout-audit-2026-10-27/measurements.json) und Screenshots liegen im gleichen Evidenzordner. Das [Prüfskript](graph-view-layout-audit.cjs) dokumentiert die Browserfälle. Es wurden weder Produktionsdaten noch bestehende Sessions geändert.

| Fenster | Views | Graph-Inhalt B×H | Filter-/Werkzeugleiste H | Canvas H vor Overlays |
|---|---:|---:|---:|---:|
| 1440×900 | 1 | 1139×746 | 113 | 633 |
| 1440×900 | 2 | 568×746 | 174 | 572 |
| 1440×900 | 3 | 378×746 | 286 | 460 |
| 1440×900 | 4 | 564×333 | 174 | 159 |
| 1280×800 | 3 | 324×646 | 374 | 271 |
| 1280×800 | 4 | 484×283 | 230 | 53 |
| 1920×1080 | 3 | 537×905 | 260 | 645 |
| 1440×900, Graph bei 25 % | 2 | 283×746 | 374 | 371 |

## Konkrete Schwächen

1. **Die Werkzeugleiste wächst ohne Höhenbudget.** Filtergruppen brechen intern um; ihre Gruppen und die vertikalen Trenner brechen zusätzlich als äußere Flex-Elemente um. Das erzeugt viele Zeilen und unnötige Lücken. Bei vier Views und 1280×800 verbraucht die Toolbar rund 81 % der Graph-Inhaltshöhe.
2. **Werkzeuge werden tatsächlich unerreichbar.** Die rechte Gruppe verwendet `shrink-0` und enthält Quellenwahl, Zähler, Zoom und weitere Aktionen. Mit zwei Quellen ist sie im Test schon in der Übersicht ungefähr 474 px breit. Das Panel kann wesentlich schmaler sein. Der umgebende Panel-Container schneidet Überstand ab. In der Nachbarschaft kommen Zurück-/Nachladeaktionen hinzu; dort verschärft sich der Überstand.
3. **Zwei Views bedeuten nicht automatisch genug Platz für Details rechts.** Der feste 260-px-Detailbereich überdeckt bei 568 px Breite fast die Hälfte des Graphen. Bei einem 25-%-Split und 283 px Panelbreite bleiben seitlich praktisch nur 23 px frei.
4. **Drei und vier Views haben unterschiedliche Engpässe.** Drei Spalten sind schmal und hoch; das Vierer-Raster ist eher breiter und kurz. Ein gemeinsames `isCompactLayout` bildet das nicht ab. Selbst bei 1920 px Fensterbreite können Bedienaktionen im Drei-Spalten-Panel abgeschnitten werden.
5. **Der Detail-Drawer bekommt einen Anteil der ohnehin verbleibenden Canvas-Höhe.** Seine 60-%-Grenze lässt bei kleinen Vierer-Panels kaum Raum für Inhalt. Bei 1440×900 bleiben im geöffneten Drawer 52 px Inhaltsfläche, bei 1280×800 sogar 0 px. Legende und Drawer teilen sich außerdem dieselbe Fläche. Im 1280×800-Vierer-Test blockiert der Detailbereich den Klick auf die Legende.
6. **Die Legende wiederholt viele Informationen aus den Filterchips.** Auf schmalen Flächen konkurrieren diese beiden Darstellungen um Platz. Kappungs-/Fehlerhinweise liegen ebenfalls oben im Canvas, ebenso die kompakte Legende.
7. **Die Erkennbarkeit von Zuständen ist schwach.** Knoten- und Linkfilter zeigen ihren Zustand hauptsächlich über Opazität; die Richtungsfilter haben zusätzlich `aria-pressed`. Die Legende und der Drawer werden über klickbare `div`s bedient. Eine Überarbeitung sollte echte Buttons, Tastaturbedienung, sichtbare Auswahl und eindeutige Beschriftungen vereinheitlichen.

Beispiele: [drei Views](evidence/graph-layout-audit-2026-10-27/1280x800-3-views.png), [vier Views](evidence/graph-layout-audit-2026-10-27/1280x800-4-views.png), [Details und Legende](evidence/graph-layout-audit-2026-10-27/1440x900-4-views-details-legend.png), [Nachbarschaft](evidence/graph-layout-audit-2026-10-27/1440x900-3-views-neighborhood.png).

## Vorgeschlagene Anordnung

### 1. Stabile Werkzeugleiste mit sichtbarem Zustand

Breite Panels erhalten beschriftete Schaltflächen; schmale Panels erhalten die gleiche Reihenfolge mit kürzeren Beschriftungen. Eine normale kompakte Leiste soll etwa eine Zeile benötigen; maximal zwei bewusst gestaltete Zeilen, wenn Quelle oder Nachbarschaftsstatus eine zweite Zeile brauchen. Startziel: etwa 44–88 CSS-px bei normaler Skalierung, anschließend mit der tatsächlichen rem-Skalierung überprüfen.

- **Filter** bleiben als eigener, sichtbarer Einstieg erhalten. Der Button zeigt beispielsweise „2 ausgeblendet“. Keine unbegrenzte Chip-Liste in der dauerhaften Toolbar.
- **Quelle bevorzugen** bleibt ein eigener Einstieg mit verkürztem ausgewähltem Namen und vollständig zugänglichem Namen. Diese Funktion priorisiert eine Quelle in der begrenzten Übersicht; sie darf nicht irreführend als exklusiver Quellenfilter dargestellt werden.
- **Ansicht einpassen** bleibt direkt erreichbar. Zoom +/− kann bei ausreichend Platz daneben stehen; bei sehr schmalen Panels erhält es einen klaren gemeinsamen Einstieg „Zoom“ oder liegt unter „Ansicht“.
- **Neu laden, Legende und Detailbereich** erhalten stabile Positionen unter einem beschrifteten „Ansicht“-Menü, soweit sie nicht direkt Platz finden. Das Menü darf nicht sämtliche wichtigen Aktionen verschlucken.
- **Nachbarschaft** bekommt einen eigenen Status-/Navigationsstreifen: „Übersicht → [Fokus]“, Zurück und Nachladen. Bei Platzmangel bleibt ein kompakter Zurück-Button sichtbar; der Fokusname wird gekürzt. Nachladen bleibt in diesem Kontext direkt erreichbar.
- **Zähler** zeigen klar bezeichnete Knoten-/Beziehungszahlen, bei wenig Platz in der Statuszeile statt zwischen Bedienelementen.

Die endgültige Priorisierung muss mit den echten Mindestbreiten gerechnet werden. Ein neuer starrer rechter Buttonblock würde den aktuellen Fehler wiederholen.

### 2. Vollständige Filterfläche bei Bedarf

„Filter“ öffnet eine zusammenhängende Fläche mit den drei bestehenden Gruppen **Knoten**, **Beziehungen** und **Richtung**. Die Liste darf innerhalb dieser Fläche scrollen; der Graph und die Toolbar bleiben stabil. Auf großen Panels können häufig genutzte Gruppen zusätzlich direkt sichtbar sein, solange das Höhenbudget eingehalten wird.

Alle bisherigen Typen bleiben einzeln schaltbar. Auswahlzustände werden eindeutig angezeigt. Eine Suchmöglichkeit und „Alle anzeigen“ sind sinnvolle Ergänzungen bei vielen Typen. Versteckte Typen bleiben in der Liste verfügbar, damit sie wieder eingeblendet werden können. Filter bleiben beim Resize und beim Öffnen anderer Bedienflächen erhalten.

Die Legende kann dieselben Farb-/Symbolinformationen verwenden, muss aber ihre Bedeutung erklären. Sie bleibt ausdrücklich erreichbar und erhält einen eigenen scrollbaren Bereich, statt unkontrolliert über Details oder Hinweise zu liegen.

### 3. Details nach Platzangebot, nicht nach View-Anzahl

| Tatsächlicher Platz | Darstellung |
|---|---|
| Breit, z. B. ab ungefähr 960 px | Seitlicher Inspector möglich; Mindestfläche für den Graphen reservieren. |
| Mittelbreit und ausreichend hoch | Optional unterer, größenveränderbarer Detailbereich; Höhe aus dem gesamten Graph-Inhalt ableiten und einen nutzbaren Canvas-Rest sichern. |
| Schmal oder sehr niedrig | Kompakte Auswahlleiste mit „Details“. Beim bewussten Öffnen nutzt der Inspector den Panel-Inhaltsbereich als zusammenhängende Fläche mit Rückkehr zum Graphen. |

Diese Grenzen sind Startwerte für einen Prototyp. Relevant sind auch Höhe, Schrift-/UI-Skalierung, lange Namen und das Split-Verhältnis. Ein Vierer-Panel sollte insbesondere keine winzige Detailscrollfläche unter einer großen Toolbar erhalten.

Ein Auswahlwechsel aktualisiert die bestehende Auswahlleiste. Er soll nicht automatisch ein zuvor geschlossenes großes Overlay öffnen. Beim Wechsel der Darstellungsform bleiben Auswahl und geöffneter Detailzustand erhalten. Nur explizites Schließen soll sie schließen.

### 4. Gemeinsame Regeln für überlagerte Flächen

Filter, Legende und Inspector müssen koordiniert werden. Auf kleinen Panels ist jeweils nur eine große Bedienfläche im Vordergrund; ihre Daten und Auswahlzustände bleiben erhalten. Schließen, Escape und Rückkehr zum aufrufenden Button müssen funktionieren. Menüs dürfen nicht vom `overflow-hidden` des Panels abgeschnitten werden; Portal-Flächen brauchen begrenzte Höhe und Kollisionsbehandlung.

Kappungs- und Fehlermeldungen erhalten eine definierte Statusposition. Ein knappes Symbol mit Kurztext kann die Meldung kompakt halten; die vollständige Information muss weiterhin zugänglich sein.

## Funktionsumfang vollständig erhalten

| Bestehende Funktion | Künftiger Ort |
|---|---|
| Knoten-/Beziehungs-/Richtungstypen einzeln umschalten | Filterfläche mit sichtbarer Zusammenfassung |
| Quelle priorisieren | Eigene Quellenwahl |
| Zoom +/− und alles einpassen | Direkte Werkzeuge bzw. klarer Zoom-Einstieg |
| Übersicht neu laden | Ansicht-Menü, bei Platz auch direkt |
| Lokalen Knotenfokus setzen/aufheben | Inspector und sichtbarer Fokusstatus |
| Nachbarschaft laden, Richtung und 1–5 Hops | Inspector mit bestehenden Einstellungen |
| Zurück zur Übersicht / weitere Verbindungen laden | Nachbarschafts-Navigation |
| Knoten-/Kantendetails und verbundene Knoten | Adaptiver Inspector |
| Passende Code-/Dokumentansicht öffnen, Original öffnen | Inspector, unveränderte Ziele |
| Code-/Dokumentbelege einer Kante öffnen | Kanten-Inspector |
| Manuelle Verbindung erstellen, Ziel suchen, Richtung und Beschreibung setzen | Bestehender Verbindungsdialog aus dem Inspector |
| Legende ein-/ausklappen | Eigener Einstieg unter Ansicht, bei Platz direkt |
| Graph verschieben/zoomen, Knoten verschieben und fixieren | Unveränderte Canvas-Interaktion |
| Auswahl, Filter, Zoom, Fokus und Ladezustände | Beim Wechsel der Darstellung beibehalten |

## Technische Umsetzung und Abnahme

Die Layoutmessung muss am **gesamten Graph-Panelinhalt** stattfinden. Der vorhandene `ResizeObserver` misst den Canvas nach Abzug der Toolbar. Diese Größe als alleinige Grundlage für die Toolbar zu verwenden kann beim Umschalten Rückkopplungen erzeugen. CSS-Container-Queries eignen sich für die Darstellung; wo ein Observer erforderlich ist, einen stabilen äußeren Container messen und Grenzflattern verhindern.

Die bestehende Graphinstanz nicht anhand der Layoutstufe remounten. Graphdaten, Kamera, Auswahl und Filter bleiben derselbe Zustand. Ebenso Nachbarschafts-Cursor, Richtung/Hops und Ladezustände erhalten. Die vorhandene gemeinsame Detaildarstellung weiterverwenden, statt pro Breakpoint eigene Funktionskopien anzulegen.

Empfohlene Reihenfolge:

1. Toolbar begrenzen, rechte Gruppe auflösen, Filter-/Ansicht-Flächen einführen und anhand der acht Messfälle prüfen.
2. Inspector und Legende anhand von Breite **und** Höhe anpassen; Overlay-Kollisionen beseitigen.
3. Tastatur-/Fokusverhalten und Zustandswahrung absichern, danach mit echten datenreichen Projekten gegenprüfen.

Abnahmekriterien: Keine abgeschnittenen Aktionen bei 280–1200 px Panelbreite; jede Bestandsfunktion mit Maus und Tastatur erreichbar; auch im niedrigen Vierer-Panel eine nutzbare Graphfläche bei geschlossenen Bedienflächen; sämtliche Detailaktionen innerhalb einer sinnvoll großen Scrollfläche erreichbar; keine Zustandsverluste beim Ziehen der Splitter; Filter, Nachbarschaft, lange Namen, offene Legende/Details sowie deutsche und englische Texte berücksichtigen. Browser-Zoom und globale UI-Skalierung zusätzlich prüfen.

Ausgangspunkt im Code: `frontend/components/KnowledgeGraphView.tsx` (Toolbar ab ca. 1734, Detailwahl ab ca. 1236, Legende/Inspector ab ca. 2048), `GraphSourceFocus.tsx`, `WorkspaceShell.tsx` sowie `frontend/app/globals.css` (rem-Skalierung).

## Umsetzung und erneute Browsermessung

Die adaptive Oberfläche wurde anschließend umgesetzt. Die Hauptleiste bleibt in den ursprünglichen acht Fällen 66 px hoch, bei 1920×1080 durch die größere rem-Basis 75 px. Die Filterfläche enthält weiterhin sämtliche Typen und Richtungen, ergänzt um Suche, eindeutige Auswahlzustände, eine sichtbare Anzahl ausgeblendeter Typen und „Alle Typen anzeigen“. Quellenpriorisierung und Einpassen bleiben direkt erreichbar; Zoom, Neuladen, Legende und Auswahlaktionen befinden sich im Ansichtsmenü.

Der Inspector misst das äußere Graph-Panel: ab 960 px Breite seitlich, ab 460 px Breite und 560 px Höhe unten, sonst als flächige Detailansicht innerhalb des Panels. Auswahl und expliziter Öffnungszustand überleben Größenwechsel. Die Graphinstanz wird dafür nicht neu aufgebaut. Filter und Legende verwenden eine gemeinsame begrenzte Werkzeugfläche; Inspector und Werkzeuge verdecken sich nicht gegenseitig.

| Kritischer Fall | Vorher | Danach |
|---|---:|---:|
| 1280×800, 4 Views: Toolbar-Höhe | 230 px | 66 px |
| 1280×800, 4 Views: Canvas-Höhe | 53 px vor überlagerter Auswahlleiste | 181 px mit reservierter Auswahlleiste |
| 1280×800, 4 Views: geöffneter Detailinhalt | 0 px | 170 px |
| 1280×800, 3 Views: Toolbar-Höhe | 374 px | 66 px |
| 1440×900, 3 Views: Toolbar-Höhe | 286 px | 66 px |

In allen acht Messfällen bleiben Übersicht und Nachbarschafts-Werkzeugleiste innerhalb der Panelbreite. Die Nachbarschaft besitzt eine zusätzliche Navigationszeile. Details sind bis zum letzten Inhalt scrollbar; bei niedrigen Panels wird dafür bewusst die Canvas-Fläche überlagert, während die Toolbar und der Schließen-Button erreichbar bleiben.

[Neue Messwerte](evidence/graph-layout-after-2026-10-27/measurements.json), [Vierer-Raster](evidence/graph-layout-after-2026-10-27/1280x800-4-views.png), [geöffnete Details](evidence/graph-layout-after-2026-10-27/1280x800-4-views-details.png), [drei Views](evidence/graph-layout-after-2026-10-27/1440x900-3-views.png) und [Nachbarschaft](evidence/graph-layout-after-2026-10-27/1440x900-3-views-neighborhood.png) dokumentieren den Vergleich mit denselben kontrollierten API-Daten.

Automatisierte Regressionen liegen in `frontend/e2e/graph-layout.spec.ts` und `KnowledgeGraphView.test.tsx`: Filterzustand, Quellenpriorisierung, Tastaturfokus, Legende, manuelle Verknüpfung samt Richtung/Beschreibung, Nachbarschaft/Nachladen, Größenwechsel ohne neue Canvas-Instanz sowie englische Texte bei vergrößerter UI. Die Browserfälle fangen API-Aufrufe ab und ändern keine Backend-Daten.

Abschlussprüfung: 82 betroffene Komponenten-/Integrationstests, alle neun Browserfälle und Produktionsbuild samt TypeScript erfolgreich. Der kritische Browserfall 1280×800 mit vier Views wurde zusätzlich gegen das aktualisierte Produktionsfrontend auf localhost:3000 erfolgreich ausgeführt.

Für Docker-Builds werden lokale Abhängigkeiten, Next-Ausgaben und Testberichte über `frontend/.dockerignore` ausgeschlossen. Dadurch wird die laufende Entwicklungsvorschau nicht in den Produktionsbuild kopiert.
