# Eine neue Sprache anbinden

**Zweck (O-081):** "auf andere Sprachen skalierbar, wenn nötig" ist eine
Behauptung, die überprüfbar sein muss. Diese Anleitung ist die Probe darauf —
Schritt für Schritt, anhand des COBOL-Parsers (`parser/cobol/`) als einziger
existierender Referenzimplementierung. Stand 06.09.2026, nach O-077 (Registry
statt hartkodierter Weiche), O-078 (sprachneutrale Parse-Typen nach
`parser/core/model.py`), O-079 (Copybook-Vorlauf als registry-deklarierter
Hook) und O-080 (Frontend-Entity-Decorations waren schon immer sprachneutral,
nichts zu tun).

**Reine Anleitung, kein Code** — es gibt noch keinen zweiten Struktur-Parser,
und dieses Dokument baut absichtlich keinen auf Vorrat (CLAUDE.md Prinzip 3,
siehe auch die Vorgeschichte in O-077: eine ungenutzte `parser/languages/`-
Abstraktion gab es schon einmal und wurde wieder entfernt). Diese Datei
beschreibt nur, was zu tun wäre, wenn ein echter zweiter Struktur-Parser
gebraucht wird.

## Kurzfassung

1. Dateiendungen der neuen Sprache klassifizieren.
2. Struktur-Parser schreiben, der ein `ParseResult` liefert.
3. In `STRUCTURE_PARSERS` registrieren.
4. Golden-File-Testkorpus anlegen.
5. Persistenz, Backend-API, Graph, Frontend-Entity-Decorations: **nichts
   ändern** — die sind bereits sprachneutral.
6. Optional: CI-Job `parser-golden` erweitern.

## Geltungsbereich: nur Git-Quellen

`STRUCTURE_PARSERS` wird ausschließlich von `GitConnector._embed_document`
(`parser/connectors/git.py`) abgefragt. Die anderen Connectoren (Confluence,
Jira, WebDAV, FolderWatch, lokaler Upload) laufen immer über das generische
`CodeParser.chunk_file()` (`parser/code_parser.py`, siehe
`connectors/base.py`) — unabhängig davon, was in `STRUCTURE_PARSERS` steht.
Eine neue strukturierte Sprache wirkt sich also nur auf Dateien aus, die über
eine Git-Wissensquelle eingelesen werden. Das ist bewusst so (Quellcode kommt
praktisch immer aus Git) und keine Lücke, die diese Anleitung schließen muss
— falls doch einmal ein anderer Connector strukturiert parsen soll, braucht
es zuerst eine eigene Entscheidung, kein Nachziehen dieser Anleitung.

## Der Vertrag: `ParseResult`

Jeder Struktur-Parser ist eine Funktion, die eine Datei **komplett
in-memory** (docs/ENTSCHEIDUNGEN.md E-6, kein DB-Zugriff) in ein
`ParseResult` (`parser/core/model.py`) übersetzt:

```python
@dataclass
class ParseResult:
    program_name: str
    path: str
    source_format: SourceFormat        # Literal["fixed", "free"]
    entities: list[Entity] = ...
    edges: list[ParsedEdge] = ...
    chunks: list[Chunk] = ...
    errors: list[str] = ...
```

- **`Entity`** (`type`, `name`, `start_line`, `end_line`, `parent_name`,
  `qualified_name`, `meta`) — `type` muss einer der Werte aus `EntityType`
  sein (`program`, `copybook`, `section`, `paragraph`, `data_item`,
  `file_fd`, `sql_table`, `sql_block`) und muss dabei mit
  `backend/models/database.py::CodeEntity.type` übereinstimmen. Eine echte
  zweite Sprache braucht fast immer neue Werte hier (z. B. `class`/`method`
  für Java) — dafür `EntityType` erweitern **und** denselben String in
  `CodeEntity.type`s Dokumentationskommentar nachtragen (Backend/Parser-DB-
  Modell müssen laut CLAUDE.md ohnehin byte-identisch bleiben).
  `qualified_name` wird schon beim Parsen gebaut (z. B.
  `"MAIN.SECTION.PARA"`), nicht erst beim Persistieren.
- **`ParsedEdge`** (`type`, `src_name`, `dst_name`, `resolution`,
  `src_start_line`, `src_end_line`, `scope`, `meta`) — `type` aus `EdgeType`
  (`CALL`, `PERFORM`, `GOTO`, `COPY`, `DEFINES`, `USES`, `READS`, `WRITES`).
  `scope` ist der Programmname für lokal auflösbare Kanten (PERFORM/GOTO/
  USES/DEFINES) und `None` für global aufzulösende (CALL/COPY,
  docs/ENTSCHEIDUNGEN.md E-1) — eine neue Kantenart in dieselbe Kategorie
  einsortieren, keine dritte Auflösungsart erfinden. **Wichtiger Fallstrick:**
  `cobol_persist.py::persist_parse_result` erzwingt für jede globale Kante
  `resolution="unresolved"` (außer `"dynamic"`), egal was der Parser meldet
  — DB-seitig gilt "resolved" erst, wenn Pass 2
  (`parser/tasks/edge_resolver.py`) tatsächlich eine Ziel-Entity gefunden
  hat. Der Parser selbst darf/soll trotzdem schon zur Parse-Zeit eine
  Namensauflösung markieren (reine Konvention, keine DB-Aussage).
- **`Chunk`** (`content`, `start_line`, `end_line`, `meta`) — landet 1:1 in
  `DocumentChunk.metadata_json`. Chunk-Grenzen sollten an sinnvollen
  Struktureinheiten liegen (bei COBOL: Paragraphen,
  `cobol/chunking.py::chunk()`), nicht willkürlich — das ist, was Struktur-
  Parsing gegenüber dem generischen zeichenzahl-basierten
  `CodeParser.chunk_file()` überhaupt gewinnt.
- **`errors`**: nicht leer heißt nicht zwangsläufig "nichts geparst" — bei
  COBOL liefert z. B. eine fehlende DATA DIVISION trotzdem Programm-/
  Paragraph-Entities. `GitConnector` liest daraus nur `parse_status`
  (`"ok"` vs. `"fallback_text"`) für `SourceScanFile`/den Users-Tab.

**Zeilennummern sind heilig** (CLAUDE.md Prinzip 5): `start_line`/`end_line`
zeigen immer auf die physische Zeile der Originaldatei. Eine eingebundene
Datei (COBOLs Copybook, ein Java-`import`, ein Python-`from x import y` —
was auch immer die neue Sprache an fremdem Quelltext einbindet) wird **nie**
in den Text expandiert, sonst verschieben sich alle Zeilennummern der
einbindenden Datei und die Navigation (Klick im Graph → Zeile im Editor)
bricht. COBOL löst das, indem Copybooks als eigenständige Entities mit
eigenen Zeilennummern geparst werden (`cobol/parse.py::parse_copybook`) und
nur eine `COPY`-Kante auf sie zeigt — dasselbe Muster gilt für jede Sprache
mit einem äquivalenten Einbindungsmechanismus.

## Schritt 1: Dateiendungen klassifizieren

`connectors/git.py::_DEFAULT_EXTENSIONS` (bzw. `DOCTUS_COBOL_EXTENSIONS`-Env
oder `spaces["language_extensions"]` pro Wissensquelle, siehe
`_resolve_extension_config()`) ordnet Dateiendungen einem Sprachschlüssel
zu:

```python
_DEFAULT_EXTENSIONS: dict[str, set[str]] = {
    "cobol": {".cbl", ".cob", ".cobol"},
    "copybook": {".cpy", ".copy"},
    "jcl": {".jcl", ".proc", ".prc"},
}
```

`classify_extension()` liefert diesen Schlüssel als `doc["extra_meta"]
["language"]`; `_embed_document()` schlägt ihn danach in `STRUCTURE_PARSERS`
nach. **Der Schlüssel muss exakt übereinstimmen** — eine neue Sprache
braucht hier einen eigenen Eintrag (z. B. `"java": {".java"}`), sonst landet
sie unter `"text"` und bekommt nie den neuen Struktur-Parser zu sehen, egal
was Schritt 3 registriert.

## Schritt 2: Struktur-Parser schreiben

Eigenes Paket `parser/<sprache>/` analog `parser/cobol/` — reine
Parse-Logik, komplett DB-frei (E-6), kein Import aus `connectors/`,
`models/` oder `cobol_persist.py`. Einstiegsfunktion mit der Signatur, die
`StructureParser` in `cobol/registry.py` verlangt:

```python
def parse_program(text: str, path: str, copybook_index: CopybookIndex | None = None) -> ParseResult: ...
```

Der dritte Parameter heißt aus historischen Gründen `copybook_index` (COBOL
war die einzige Sprache, als er entstand) — er ist aber generisch: es ist
schlicht das Ergebnis, das `ParserEntry.prepare_source()` (Schritt 3, O-079)
für diese Sprache geliefert hat, `None` wenn kein Hook registriert ist. Eine
neue Sprache ohne quellenweite Vorabanalyse ignoriert den Parameter einfach
(Default `None`); eine Sprache mit einem COBOL-COPY-analogen Bedarf (z. B.
eine quellenweite Symboltabelle für `#include`) bekommt über denselben
Mechanismus ihren eigenen Vorlauf, ohne dass `GitConnector` dafür etwas
wissen muss.

## Schritt 3: In der Registry eintragen

`cobol/registry.py::STRUCTURE_PARSERS` ist die einzige Anschlussstelle:

```python
@dataclass(frozen=True)
class ParserEntry:
    parse: StructureParser
    prepare_source: PrepareSourceHook | None = None   # optional, O-079

STRUCTURE_PARSERS: dict[str, ParserEntry] = {
    "cobol": ParserEntry(parse=parse_program, prepare_source=_prepare_copybook_index),
    "copybook": ParserEntry(parse=parse_copybook, prepare_source=_prepare_copybook_index),
    "java": ParserEntry(parse=java_parse.parse_program),   # Beispiel, kein prepare_source nötig
}
```

Der Registry-Schlüssel ist derselbe String wie in Schritt 1
(`_DEFAULT_EXTENSIONS`). `GitConnector` kennt danach automatisch die neue
Sprache — `_embed_document()`/`_run_prepare_hooks()` fragen generisch über
`STRUCTURE_PARSERS.get(lang)` ab, ohne dass `connectors/git.py` je wieder
angefasst werden muss.

**Bewusst nicht Teil dieser Anleitung:** `cobol/registry.py` unter dem
`cobol/`-Paket zu belassen, obwohl es ab einem echten zweiten Eintrag streng
genommen keine COBOL-spezifische Datei mehr wäre. Ein Umzug (z. B. nach
`parser/core/registry.py`) ist dann eine eigene, kleine Aufräumarbeit — aber
kein Vorratsbau jetzt, wo noch niemand zweites drinsteht (derselbe Grundsatz
wie bei O-077/O-078).

## Schritt 4: Golden-File-Testkorpus

Analog `parser/tests/cobol_corpus/` (`fixtures/*.cbl` roh,
`golden/*.json` die erwartete `ParseResult`-Serialisierung):

- `parser/tests/<sprache>_corpus/fixtures/*.<ext>` — Testquelltexte, die
  bewusst kuriose/kaputte Fälle abdecken (COBOLs Korpus hat u. a. defekte
  Dateien, Umlaute, verschachtelte COPYs — siehe die `NN_*.cbl`-Namen dort
  als Vorbild für Benennung/Abdeckung).
- `parser/tests/<sprache>_corpus/golden/*.json` — **nie von Hand editieren.**
  Ein eigenes Gegenstück zu `scripts/regenerate_cobol_golden.py` erzeugt sie
  aus dem aktuellen Parser (`dataclasses.asdict(parse_fn(text, logical_path))`,
  `logical_path` reporelativ-konstant, damit die Golden Files zwischen
  lokalem Lauf und CI portabel bleiben).
- `parser/tests/test_<sprache>_golden.py` — Gegenstück zu
  `test_cobol_golden.py`: parametrisierter Vergleich jeder Fixture gegen
  ihre Golden-Datei, plus ein Test, der sicherstellt, dass jede Fixture
  tatsächlich eine Golden-Datei hat (verhindert eine neue Fixture, die
  nie geprüft wird).

**CI:** Der Haupt-Job `parser` (`.github/workflows/ci.yml`) läuft ohnehin
als `pytest tests/ -v` und deckt die neuen Tests automatisch ab. Der
zusätzliche, DB-lose `parser-golden`-Job ist mit `-k cobol` bewusst nur auf
COBOL zugeschnitten (schneller Fast-Fail ohne Postgres/Redis-Service, siehe
Kommentar dort) — wenn der neue Parser genauso reines In-Memory-Parsing ohne
DB-Zugriff ist (sollte er laut E-6 ohnehin sein), lohnt sich, den Filter zu
erweitern (z. B. `-k "cobol or java"`), sonst bleibt die neue Sprache auf
den langsameren Haupt-Job angewiesen.

## Schritt 5: Was NICHT geändert werden muss

Das ist der eigentliche Beleg für "skalierbar" — nicht die Behauptung,
sondern dass diese Liste tatsächlich leer bleibt:

- **`cobol_persist.py::persist_parse_result`** — trotz des Dateinamens
  bereits vollständig sprachneutral: nimmt ein `ParseResult` entgegen und
  schreibt es generisch nach `code_entities`/`code_edges` (UPSERT über
  `(source_id, file_path, qualified_name)`). Kein einziges COBOL-spezifisches
  Verhalten im Code selbst.
- **Backend-API/Graph/Callgraph** (`backend/api/*.py`,
  `backend/services/graph_retrieval.py`) — kein einziges Vorkommen des
  Strings `"cobol"` (geprüft per `grep -rl cobol backend/api backend/services`).
  Entities/Kanten jeder Sprache landen in denselben Tabellen und werden
  identisch angezeigt/durchsucht.
- **Frontend-Entity-Decorations** (`SplitPaneWorkspace.tsx`, Glyph-Margin,
  Hover, Klick-zu-Referenzen) — laut O-080 bereits rein datengetrieben
  (`projectEntities.filter(ent => ent.file_path === selectedFile)`, keine
  Sprachprüfung). Jede Sprache mit `CodeEntity`-Zeilen für eine Datei
  bekommt automatisch dieselben Decorations.

**Ausnahme, kein Widerspruch:** genuin sprachspezifische UI bleibt genuin
sprachspezifisch und sollte es auch bleiben. Das COBOL-Spaltenlineal
(Sequence/Indicator/Area A/Area B/Programm-ID, `SplitPaneWorkspace.tsx`s
`isCobol`-Zweig im Editor-Lineal) bildet COBOLs physisches ANSI-Fixed-
Format-Spaltenraster ab — ein Konzept ohne Äquivalent in den meisten anderen
Sprachen. Eine neue Sprache mit einem vergleichbaren eigenen Bedarf bekommt
einen eigenen, eigens benannten Fall, keine erzwungene Verallgemeinerung des
COBOL-Falls (O-080s zentraler Befund: eine Datenabfrage statt der
Sprachprüfung wäre hier falsch gewesen, nicht generischer).
