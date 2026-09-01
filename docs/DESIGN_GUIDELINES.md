# Doctwos Design Guidelines

**Stand:** 01.09.2026 — im Frontend umgesetzt

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
3. **Ein Markenspektrum.** Fujitsu-Rot kennzeichnet Auswahl und Fokus. Der
   Rot-Blau-Verlauf ist Primäraktionen und markanten Brand-Flächen vorbehalten.
   Statusfarben bleiben semantisch und werden nicht dekorativ genutzt.
4. **Asymmetrie mit Ordnung.** Geteilte Flächen, Randmarken und versetzte
   Komponenten erzeugen Eigenständigkeit, bleiben aber am 8-Pixel-Raster.
5. **Code ist Primärmaterial.** Pfade, Entitäten, Branches und technische Metadaten
   verwenden Monospace; Fließtext und Navigation eine sachliche Grotesk.

## Farbrollen

- `Canvas`: warmes Papier im Light Mode, tiefes Petrolschwarz im Dark Mode.
- `Surface`: klar abgegrenzte Arbeitsflächen, nie transparentes Glas.
- `Ink`: fast schwarz bzw. gebrochen weiß für belastbaren Kontrast.
- `Signal`: Fujitsu-Rot (`#E4002B`, im Dark Mode aufgehellt).
- `Brand Gradient`: Rot über Violett zu Blau (`#E4002B` → `#0064D2`).
- `Trace`: Fujitsu-Blau für technische Verbindungen und Informationszustände.
- Rot, Amber und Grün sind ausschließlich Fehler, Warnung und Erfolg.

## Form, Typografie und Bewegung

- Standardradius 6 px; große Container höchstens 10 px. Pills nur für Status.
- Flächen erhalten 1-px-Linien, keine weichen Ambient-Schatten.
- Space Grotesk für Display/Überschriften, Archivo für UI, IBM Plex Mono für Code.
- Überschriften dürfen eng und groß sein; Utility-Labels sind uppercase mit Tracking.
- Übergänge 120–180 ms. Bewegung erklärt Zustandswechsel, sie dekoriert nicht.

### Standarddarstellung und Dichte

- Die Desktop-Basisdarstellung verwendet eine zentrale UI-Skalierung von 110 %
  (effektiv 17,6 px Root-Schriftgröße). Dadurch wachsen rem-basierte
  Schriftgrößen, Bedienelemente und Abstände gemeinsam und die Oberfläche
  entspricht der Darstellung, die zuvor typischerweise mit 110 %
  Browser-Zoom genutzt wurde.
- Mobile Ansichten bleiben bei 100 % bzw. 16 px Root-Schriftgröße, damit die
  schmalen Arbeitsflächen und die responsive Navigation nicht unnötig an
  nutzbarer Breite verlieren.
- Kleine technische Kicker, Badges und Editor-Metadaten dürfen kompakt bleiben;
  Fließtext, Navigation und Bedienelemente verwenden weiterhin die regulären
  Typografie- und Mindestgrößen.

## Komponentenregeln

- Primärbuttons: Rot-Blau-Markenverlauf, weiße Schrift, klare Kontur.
- Sekundärbuttons: Surface + Border; Hover verändert Fläche oder Linie, nicht Glow.
- Navigation: aktive Elemente durch linke Signalmarke und Flächenwechsel.
- Inputs: mindestens 40 px hoch, sichtbarer Labeltext, 2-px-Fokusring.
- Panels: Kopfzeile, Inhaltsfläche und Resize-Kante müssen optisch unterscheidbar sein.
- Leere Zustände erklären die nächste Handlung; keine generischen Illustrationen.

## Verbotene Alt-Muster

- Blau-violette Mesh-Gradients und leuchtende Blur-Kreise
- Glassmorphism und großflächiges `backdrop-blur`
- beliebige Deko-Verläufe; zulässig ist ausschließlich der definierte Rot-Blau-Markenverlauf
- generische Netzwerk-/AI-Sparkle-Symbolik als Markenkennzeichen
- Beispielnamen oder Beispiel-E-Mail-Adressen in produktiven Ansichten
