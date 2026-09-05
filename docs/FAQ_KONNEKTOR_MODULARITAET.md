# FAQ — Konnektor-Modularität & mainframe-native SCM-Systeme (O-042)

**Stand:** 05.09.2026
**Zweck:** Antworten auf wiederkehrende Fragen aus Vertriebs-/Kundengesprächen zu
O-042 (fehlender Konnektor für mainframe-native Quellcode-Verwaltung), damit
diese nicht bei jedem Gespräch neu hergeleitet werden müssen. Ergänzt den
Eintrag in [OFFENE_ENTWICKLUNGSPUNKTE.md](OFFENE_ENTWICKLUNGSPUNKTE.md).

---

**F: Kann Doctus COBOL-Bestände anbinden, die nicht in Git liegen?**

A: Heute nein. `parser/connectors/git.py` funktioniert providerneutral mit
jedem Git-Hoster (GitHub, GitLab, Azure Repos, Bitbucket, …), aber eben nur
mit Git als Protokoll. Ein Bestand, der noch mainframe-nativ in Endevor,
ChangeMan, Micro Focus/PVCS, IBM RTC/CMVC oder direkt als z/OS-PDS-Dataset
verwaltet wird, lässt sich damit aktuell gar nicht anbinden.

---

**F: Welches System ist am weitesten verbreitet?**

A: Allgemeines Branchenwissen (keine für Doctus verifizierte Marktstudie):

- **CA/Broadcom Endevor** — gilt als Marktführer, besonders in großen
  Konzernen (Banken, Versicherungen).
- **ChangeMan ZMF** (heute OpenText, früher Micro Focus/Serena) — der
  klassische zweite große Player, ebenfalls stark im Finanz-/
  Versicherungsumfeld.
- IBM RTC/CMVC ist eher rückläufig/nischig, PVCS weitgehend Legacy.
- Ein dritter, oft übersehener Weg: viele ältere Umgebungen (gerade
  öffentlicher Sektor/Versicherungen mit langer Historie) haben **gar kein**
  kommerzielles SCM, sondern verwalten COBOL-Code direkt als
  **z/OS-PDS-Member**. Ein reiner PDS-Zugriffskonnektor deckt zwar keine
  Versions-/Freigabehistorie ab, funktioniert aber bei praktisch jedem
  Mainframe-Kunden, ob mit oder ohne kommerzielles SCM obendrüber.

---

**F: Ist Doctus technisch schon modular genug, um weitere Systeme anzubinden?**

A: Ja, am entscheidenden Punkt schon — das ist kein Neubau, sondern ein
etabliertes, bereits siebenfach genutztes Muster:

- Jeder Connector (Confluence, Jira, Folder, WebDAV, Git, …) erbt von
  `BaseConnector` (`parser/connectors/base.py`) und muss nur **eine**
  Methode implementieren: `fetch_documents()`, die ein einheitliches
  `Document`-Format liefert (`title`, `content`, `url`, `storage_key`,
  `extra_meta`).
- Die COBOL-Erkennung läuft **generisch in der Basisklasse**
  (`base.py:157-159`): `lang = doc["extra_meta"]["language"]` →
  `CodeParser(lang).chunk_file(...)`. Das ist nicht Git-spezifisch —
  `GitConnector` setzt einfach `extra_meta={"language": "cobol", ...}`,
  danach übernimmt derselbe COBOL-Parser, derselbe Aufrufgraph, dieselbe
  Embedding-Pipeline, die auch heute für Git-Bestände läuft.
- Neuer Connector = neue Klasse + ein Eintrag in
  `parser/connectors/registry.py` (dort wörtlich dokumentiert: "Neuen
  Connector in 2 Schritten hinzufügen").
- Kleiner ehrlicher Zusatz: am Frontend braucht ein neuer Quellentyp noch
  ein eigenes Formular-Feld-Set in `SourcesSetupTab.tsx` (z. B.
  Endevor-Zugangsdaten statt Git-URL/Token) — überschaubare, eigenständige
  UI-Arbeit, keine Architekturänderung.

**Fazit:** "Wir unterstützen heute Git, weitere Mainframe-SCM-Systeme lassen
sich über dieselbe Schnittstelle ergänzen" ist eine technisch gedeckte
Aussage. Der Aufwand pro weiterem System ist im Wesentlichen "wie spreche
ich das jeweilige API/Protokoll", nicht "wie baue ich das nochmal von Grund
auf".

---

**F: Was wäre für einen nativen Endevor-Konnektor konkret neu zu bauen?**

A: Nur der eine Baustein, der bei jedem Connector unterschiedlich ist: eine
`fetch_documents()`-Implementierung, die gegen Endevors REST-Schnittstelle
("Endevor Web Services") Elemente entlang der Hierarchie
Environment → System → Subsystem → Type → Element/Stage auflistet und ihren
COBOL-Quelltext zieht. Alles danach (Parsing, Graph, Embedding, Speicherung)
ist bereits vorhanden und unverändert wiederverwendbar.

---

**F: Warum wurde das nicht einfach direkt gebaut?**

A: Zwei Gründe, beide bewusst vor dem Schreiben von Code geklärt statt
danach entdeckt:

1. **Unverifizierbar ohne echtes System.** Anders als jede andere Änderung
   in diesem Repo lässt sich ein Endevor-Konnektor nicht gegen den
   laufenden Doctus-Stack testen — Broadcom Endevor läuft nur auf einem
   echten oder lizenzierten Mainframe, den es hier nicht gibt. Code gegen
   eine geratene API-Form zu schreiben und als "fertig" zu präsentieren,
   birgt das Risiko, beim ersten Kundentermin nicht zu passen.
2. **Möglicherweise unnötig.** Broadcom bietet zusätzlich
   "**Endevor Bridge for Git**" an — wenn ein Kunde das bereits einsetzt,
   synchronisiert Broadcom die Endevor-Elemente automatisch in ein
   Git-Repo. Dafür würde der **bestehende** `GitConnector` vermutlich schon
   ausreichen, ganz ohne neuen Code.

**Die entscheidende, noch offene Frage für Vertrieb/Kunde:**

> Setzt [Zielkunde] zusätzlich "Endevor Bridge for Git" ein — oder läuft
> Endevor klassisch über ISPF/Batch-SCL ohne Git-Anbindung?

| Antwort | Konsequenz |
|---|---|
| Ja, Bridge for Git im Einsatz | Vermutlich kein neuer Code nötig — bestehender `GitConnector` reicht. |
| Nein, klassischer Zugriff | Nativer Endevor-REST-Konnektor nötig — dafür wird zwingend ein **echter Endevor-Testzugang** gebraucht, sonst keine Verifikation möglich. |

---

**F: Warum nicht einfach die Zowe-CLI (Endevor-Plugin) nutzen — die gibt's doch fertig?**

A: Scheidet aus. Zowe ist EPL-2.0-lizenziert, das verstößt gegen
CLAUDE.md Prinzip 2 ("Strikt Open Source, nur MIT/BSD/Apache-2.0"). Ein
nativer Konnektor müsste stattdessen direkt gegen Endevors REST-API sprechen
(passend zu Coding-Regel 4: "Keine schweren SDKs — `httpx` direkt").

---

## Referenzen

- [OFFENE_ENTWICKLUNGSPUNKTE.md](OFFENE_ENTWICKLUNGSPUNKTE.md) — O-042 (Status/nächste Aktion)
- `parser/connectors/base.py` — `BaseConnector`, `Document`-Format
- `parser/connectors/registry.py` — Connector-Registrierung
- `parser/connectors/git.py` — Referenzimplementierung für einen Code-Connector
