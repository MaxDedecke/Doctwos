# Doctus — Entscheidungslog

Fachliche/technische Festlegungen, die der Implementierungsplan offen gelassen hat.
Eine Zeile pro Entscheidung, mit Begründung und Fundstelle im Code. Wer eine
Entscheidung revidiert, ändert hier den Eintrag — nicht nur den Code.

| ID | Thema | Entscheidung | Status |
|----|-------|--------------|--------|
| E-1 | Kanten-Nachauflösung | `code_edges.scope_entity_id` eingeführt | umgesetzt |
| E-2 | XREF über Copybook-Grenzen | quellenweiter Feldindex, REPLACING wird mitgeführt | entschieden, offen in AP-2 |
| E-3 | Partial Clone vs. Offline | `--filter=blob:none` nur bei erreichbarem Remote | entschieden, offen in AP-3 |
| E-4 | `sql_block` als Entity-Typ | ja, achter Typ (D-1 aus dem Plan) | umgesetzt |
| E-5 | Login-Sperre bei Redis-Ausfall | zwei Zähler: Redis (Name+IP) und DB (Nutzer), der höhere gilt | umgesetzt |

---

## E-1 — Programmlokale Kanten dürfen nicht global aufgelöst werden

**Problem.** Der Plan (§5.4/§6.4) löst offene Kanten im Nachlauf-Pass über
`UPDATE code_edges SET dst_entity_id = … WHERE dst_name = code_entities.name` auf.
Das ist für `CALL` richtig (PROGRAM-IDs sind im Bestand eindeutig), aber falsch für
`PERFORM`, `GO TO` und `USES`: Paragraphennamen wie `INIT-PARA` oder Feldnamen wie
`WS-STATUS` existieren in hunderten Programmen. Ein globaler Join verdrahtet den
Call-Graph quer über Programmgrenzen — und zwar still, ohne Fehler.

**Entscheidung.** `code_edges` bekommt `scope_entity_id`: die Entity, innerhalb derer
ein Name aufgelöst werden darf (in der Regel das Programm). Der Nachlauf-Pass ist
zweigeteilt:

- **global** (`scope_entity_id IS NULL`): `CALL`, `COPY` → Auflösung über
  `source_id` + `dst_name`
- **lokal** (`scope_entity_id` gesetzt): `PERFORM`, `GO TO`, `USES`, `DEFINES` →
  Auflösung nur gegen Entities mit demselben `parent`-Baum

Programmlokale Kanten sind damit schon beim Parsen auflösbar und brauchen den
Nachlauf-Pass gar nicht — der bleibt für die echten Cross-Program-Kanten.

**Fundstelle.** `backend/models/database.py::CodeEdge.scope_entity_id`,
Index `ix_code_edges_scope_name`.

---

## E-2 — XREF endet nicht an der Copybook-Grenze

**Problem.** Regel 1 des Plans (§6.1) ist richtig: Copybooks werden nie in den
Programmtext expandiert, sonst verschieben sich alle Zeilennummern. Nur baut
`xref.py` seinen Namensindex aus den `DataItem`s **des Programms** — Felder, die
aus einem Copybook stammen (in COBOL-Beständen die Mehrheit), stehen nicht darin.
F-025 („Verwendungsstellen von Datenfeldern") wäre damit nur halb erfüllt.

**Entscheidung.** Der Namensindex wird quellenweit aufgebaut, nicht programmlokal:

1. Copybooks werden als eigene Entities mit eigenen `data_item`-Kindern geparst
   (Zeilennummern beziehen sich auf die **Copybook**-Datei — dort gehören sie hin).
2. Ein Programm mit `COPY X` erbt für die XREF-Auflösung den Feldindex von `X`,
   ohne dass Text expandiert wird. Die entstehende `USES`-Kante zeigt vom
   Paragraphen (im Programm, mit Programm-Zeilennummer) auf das `data_item`
   (im Copybook, mit Copybook-Zeilennummer). Genau dafür trägt jede Kante
   ihre eigene `src_start_line`.
3. `COPY … REPLACING` wird in `code_edges.meta_json.replacing` mitgeführt; die
   Auflösung wendet die Ersetzung auf die geerbten Feldnamen an, bevor sie matcht.
   Ist die Ersetzung nicht eindeutig anwendbar, bleibt die Kante `unresolved` —
   kein Raten.

**Offen bis AP-2.** Mengengerüst prüfen: XREF ist laut Risiko R5 die volumenstärkste
Kantenart; falls die Zeilenzahl explodiert, auf 01-Level-Gruppen aggregieren.

---

## E-3 — Partial Clone nur, solange der Remote erreichbar ist

**Problem.** §7.2 klont mit `--filter=blob:none`. Ein Partial Clone lädt Blobs erst
beim Zugriff nach — das braucht dauerhaft eine Verbindung zum Git-Server. In einer
abgeschotteten Umgebung (NF-002) oder wenn der Server wegfällt, brechen
Worktree-Operationen ohne offensichtlichen Zusammenhang zur Ursache.

**Entscheidung.** Der Filter wird konfigurierbar statt fest verdrahtet:

- `DOCTUS_GIT_PARTIAL_CLONE=1` (Default): `--filter=blob:none`, spart bei der
  Erstindexierung eines Monorepos den Großteil des Transfers.
- `DOCTUS_GIT_PARTIAL_CLONE=0`: vollständiger Blob-Transfer beim Klonen, danach
  ist der Bare-Store autark. Das ist die Einstellung für Deployments, in denen der
  Git-Server nach der Erstindexierung nicht mehr erreichbar ist.

Zusätzlich: nach Abschluss der Erstindexierung optional `git repack -a -d` +
`git fetch --refetch` zum „Auffüllen". Wird in AP-3 gemessen, nicht vorab entschieden.

**Offen bis AP-3.**

---

## E-4 — `sql_block` ist ein Entity-Typ

Der Plan stellt die Frage in §5.3 (D-1) selbst: F-032 verlangt Kanten
`SQL-Block → Datenfeld (USES)`, eine Kante braucht auf beiden Seiten einen Knoten.

**Entscheidung.** `sql_block` wird als achter Entity-Typ geführt. Er ist nicht
fokussierbar im Sinne von F-067 (kein eigenes Fokus-Objekt im Editor), existiert
aber als Kantenendpunkt und als Kontext-Träger für F-027.

**Fundstelle.** Typ-Kommentar an `CodeEntity.type`.

---

## E-5 — Die Login-Sperre darf nicht an Redis hängen

**Problem.** §11 des Plans schreibt für das Rate-Limit einen „Redis-Zähler pro
(username, IP)" vor. Redis ist in dieser Architektur aber ein Cache-artiger Dienst:
er wird neu gestartet, geflusht, läuft in kleinen Deployments auch mal gar nicht.
Hängt die Sperre allein daran, ist sie mit einem Neustart des Containers aufgehoben —
und wer Passwörter durchprobiert, muss nur warten, bis jemand deployt.

**Entscheidung.** Zwei Zähler, deren höherer Wert gilt:

- **Redis, pro (Benutzername, IP)**, Zeitfenster 15 Minuten. Greift auch für
  *unbekannte* Benutzernamen — sonst bliebe das Durchprobieren von Namen ungebremst,
  und am unterschiedlichen Sperrverhalten wäre ablesbar, welche Konten existieren.
- **DB, pro Nutzer** (`users.failed_login_count` / `users.locked_until`). Dauerhaft,
  überlebt jeden Redis-Neustart, ist die Sperre, die ein Administrator im Users-Tab
  sieht.

Das Entsperren räumt **beide** Seiten ab (`login_throttle.clear_user()`, SCAN über alle
IP-Buckets dieses Namens). Nur die DB-Spalten zu leeren genügt nicht: die Redis-Sperre
liefe unabhängig weiter, der Nutzer bekäme bis zum Ablauf der TTL weiter 423 — und die
Verwaltung meldete „entsperrt". Genau so gefunden bei der Erststart-Abnahme.

Backoff: 5 Fehlversuche frei, ab dem 6. Sperre von 60 s mit Verdopplung je weiterem
Fehlversuch, **gedeckelt bei 1 h**. Der Deckel ist kein Komfort, sondern eine
Sicherheitsentscheidung: ohne ihn wäre ein Konto nach ~20 Versuchen praktisch
dauerhaft gesperrt — ein Denial-of-Service gegen jeden, dessen Benutzernamen man kennt.

Fällt Redis aus, bleibt die DB-Sperre allein wirksam: die Anmeldung wird dadurch nie
unmöglich, aber auch nie ungebremst.

**Fundstelle.** `backend/core/login_throttle.py`, Verwendung in `backend/api/auth.py::login`.
