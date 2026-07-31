# Doctwos Design Guidelines

## Leitidee: Structured Intelligence

Doctwos ist kein Chatbot mit Code-Anhang, sondern ein Arbeitsinstrument zur
Navigation großer, langlebiger Softwaresysteme. Die Oberfläche wirkt deshalb
präzise, ruhig und redaktionell: klare Raster, markante Typografie, hohe
Informationsdichte und wenige, bewusst gesetzte Signalfarben.

## Visuelle Prinzipien

1. **Werkzeug statt Showroom.** Keine Glow-Wolken, Glasflächen oder dekorativen
   Farbverläufe. Tiefe entsteht durch Ebenen, Linien und Kontrast.
2. **Editoriale Hierarchie.** Große, knappe Überschriften treffen auf kompakte
   Mono-Labels. Inhalte stehen vor Dekoration.
3. **Eine Signalfarbe.** Electric Mint kennzeichnet Auswahl, Fokus und primäre
   Aktionen. Statusfarben bleiben semantisch und werden nicht dekorativ genutzt.
4. **Asymmetrie mit Ordnung.** Geteilte Flächen, Randmarken und versetzte
   Komponenten erzeugen Eigenständigkeit, bleiben aber am 8-Pixel-Raster.
5. **Code ist Primärmaterial.** Pfade, Entitäten, Branches und technische Metadaten
   verwenden Monospace; Fließtext und Navigation eine sachliche Grotesk.

## Farbrollen

- `Canvas`: warmes Papier im Light Mode, tiefes Petrolschwarz im Dark Mode.
- `Surface`: klar abgegrenzte Arbeitsflächen, nie transparentes Glas.
- `Ink`: fast schwarz bzw. gebrochen weiß für belastbaren Kontrast.
- `Signal`: Electric Mint (`#35F2B5` dark / `#007A5E` light).
- `Trace`: Cyan für technische Verbindungen und Informationszustände.
- Rot, Amber und Grün sind ausschließlich Fehler, Warnung und Erfolg.

## Form, Typografie und Bewegung

- Standardradius 6 px; große Container höchstens 10 px. Pills nur für Status.
- Flächen erhalten 1-px-Linien, keine weichen Ambient-Schatten.
- Space Grotesk für Display/Überschriften, Archivo für UI, IBM Plex Mono für Code.
- Überschriften dürfen eng und groß sein; Utility-Labels sind uppercase mit Tracking.
- Übergänge 120–180 ms. Bewegung erklärt Zustandswechsel, sie dekoriert nicht.

## Komponentenregeln

- Primärbuttons: vollflächige Signalfarbe, dunkle Schrift, klare Kontur.
- Sekundärbuttons: Surface + Border; Hover verändert Fläche oder Linie, nicht Glow.
- Navigation: aktive Elemente durch linke Signalmarke und Flächenwechsel.
- Inputs: mindestens 40 px hoch, sichtbarer Labeltext, 2-px-Fokusring.
- Panels: Kopfzeile, Inhaltsfläche und Resize-Kante müssen optisch unterscheidbar sein.
- Leere Zustände erklären die nächste Handlung; keine generischen Illustrationen.

## Verbotene Alt-Muster

- Blau-violette Mesh-Gradients und leuchtende Blur-Kreise
- Glassmorphism und großflächiges `backdrop-blur`
- Farbverläufe auf Buttons oder Avataren
- generische Netzwerk-/AI-Sparkle-Symbolik als Markenkennzeichen
- Beispielnamen oder Beispiel-E-Mail-Adressen in produktiven Ansichten
