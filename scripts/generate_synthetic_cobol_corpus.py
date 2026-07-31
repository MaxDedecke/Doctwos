#!/usr/bin/env python3
"""
scripts/generate_synthetic_cobol_corpus.py
============================================
AP-9 (Härtung, NF-010 Lasttest): erzeugt einen synthetischen COBOL-
Ersatzkorpus, weil kein echter DRV-Bestand verfügbar ist (Plan §1.3 Punkt 4,
docs/UMSETZUNGSSTAND.md "Fachlich offen"). Ersetzt keine Abnahme am echten
Bestand — liefert nur ein erstes reales Signal für Parser-/Persistenz-/
Embedding-Durchsatz, bevor der echte Kundenbestand verfügbar ist.

Erzeugt Programme (.cbl) und Copybooks (.cpy) im Fixed-Format, mit demselben
7-/11-Spalten-Einrückungsstil wie parser/tests/cobol_corpus/fixtures/, plus
einem realistischen Cross-Reference-Graphen:
  - CALL 'PGMnnnnn' referenziert andere generierte Programme (statischer,
    global auflösbarer Aufrufgraph, Plan §6.4 Pass 2)
  - COPY CPYnnnnn [REPLACING ...] referenziert generierte Copybooks
  - PERFORM/PERFORM THRU/GO TO referenzieren programmlokale Paragraphen
  - EXEC SQL-Blöcke mit Host-Variablen (SELECT/INSERT/UPDATE/DECLARE CURSOR)
  - Datenfeld-Wiederverwendung über OF/IN-Qualifizierung (xref.py-Pfad)

Programmgrößen sind bewusst schief verteilt (70% klein/25% mittel/5% groß),
angelehnt an reale COBOL-Bestände statt an eine Gleichverteilung.

Nur Standardbibliothek, deterministisch über --seed. Ausgabe ist NICHT
committet (.gitignore: loadtest/) — nur dieses Skript ist der reproduzierbare
Teil.
"""

from __future__ import annotations

import argparse
import random
import subprocess
from pathlib import Path

AREA_A = " " * 7   # Spalte 8
AREA_B = " " * 11  # Spalte 12
AREA_C = " " * 15  # verschachtelte Statements (IF-Rumpf etc.)

WORDS = [
    "CUST", "ACCT", "BAL", "TXN", "RATE", "AMT", "DATE", "STAT", "CODE",
    "NAME", "ADDR", "REF", "POL", "CLM", "PREM", "TAX", "NET", "GROSS",
    "LIMIT", "FLAG", "TOTAL", "COUNT", "ID", "NR", "TYPE", "GRP",
]


def pic_clause(rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.4:
        return f"PIC X({rng.randint(2, 40)})"
    if kind < 0.7:
        return f"PIC 9({rng.randint(1, 9)})"
    if kind < 0.9:
        return f"PIC 9({rng.randint(1, 7)})V9({rng.randint(1, 2)})"
    return f"PIC S9({rng.randint(3, 9)}) COMP-3"


def field_name(rng: random.Random, prefix: str) -> str:
    return f"{prefix}-{rng.choice(WORDS)}-{rng.randint(1, 999):03d}"


def make_working_storage(rng: random.Random, n_groups: int) -> tuple[list[str], list[str]]:
    """Liefert (Zeilen, Feldnamen) — Feldnamen für PROCEDURE-DIVISION-Referenzen."""
    lines: list[str] = []
    field_names: list[str] = []
    for g in range(n_groups):
        group_name = f"WS-GROUP-{g:03d}"
        lines.append(f"{AREA_A}01  {group_name}.")
        n_fields = rng.randint(2, 6)
        for _ in range(n_fields):
            fn = field_name(rng, "WS")
            lines.append(f"{AREA_B}05  {fn:<20}{pic_clause(rng)}.")
            field_names.append(fn)
    lines.append(f"{AREA_A}01  WS-COUNTER          PIC 9(7) VALUE 0.")
    lines.append(f"{AREA_A}01  WS-EOF-FLAG          PIC X VALUE 'N'.")
    lines.append(f"{AREA_B}88  WS-EOF                         VALUE 'Y'.")
    field_names.append("WS-COUNTER")
    return lines, field_names


def make_paragraphs(
    rng: random.Random,
    n_paragraphs: int,
    field_names: list[str],
    call_targets: list[str],
) -> tuple[list[str], list[str]]:
    """Liefert (Zeilen, Paragraphennamen). Erster Paragraph ist MAIN-PARA."""
    names = ["MAIN-PARA"] + [f"PARA-{i:03d}" for i in range(1, n_paragraphs)]
    lines: list[str] = []

    for idx, name in enumerate(names):
        lines.append(f"{AREA_A}{name}.")
        n_stmts = rng.randint(2, 5)
        for _ in range(n_stmts):
            stmt_kind = rng.random()
            if stmt_kind < 0.3 and field_names:
                f1, f2 = rng.choice(field_names), rng.choice(field_names)
                lines.append(f"{AREA_B}ADD 1 TO {f1}.")
                lines.append(f"{AREA_B}MOVE {f1} TO {f2}.")
            elif stmt_kind < 0.45 and idx < len(names) - 1:
                # PERFORM eines spaeteren oder frueheren Paragraphen (kein Selbstaufruf)
                others = [n for n in names if n != name]
                if others:
                    target = rng.choice(others)
                    if rng.random() < 0.3:
                        thru_candidates = [n for n in names if n != name and n != target]
                        if thru_candidates:
                            lines.append(f"{AREA_B}PERFORM {target} THRU {rng.choice(thru_candidates)}.")
                            continue
                    lines.append(f"{AREA_B}PERFORM {target}.")
            elif stmt_kind < 0.6 and call_targets:
                target = rng.choice(call_targets)
                lines.append(f"{AREA_B}CALL '{target}'.")
            elif stmt_kind < 0.7 and field_names:
                f1 = rng.choice(field_names)
                lines.append(f"{AREA_B}IF {f1} > 0")
                lines.append(f"{AREA_C}DISPLAY 'OK'")
                lines.append(f"{AREA_B}END-IF.")
            elif stmt_kind < 0.8:
                lines.append(f"{AREA_B}EXEC SQL")
                table = f"T_{rng.choice(WORDS)}"
                lines.append(f"{AREA_C}SELECT COL1, COL2")
                lines.append(f"{AREA_C}  INTO :WS-COUNTER, :WS-EOF-FLAG")
                lines.append(f"{AREA_C}  FROM {table}")
                lines.append(f"{AREA_C} WHERE ID = :WS-COUNTER")
                lines.append(f"{AREA_B}END-EXEC.")
            else:
                lines.append(f"{AREA_B}DISPLAY 'STEP {idx}'.")
        if idx == len(names) - 1:
            lines.append(f"{AREA_B}STOP RUN.")

    return lines, names


def size_bucket(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.70:
        return "small"
    if r < 0.95:
        return "medium"
    return "large"


BUCKET_PARAMS = {
    # (working-storage-gruppen, paragraphen)
    "small": (2, 4, 3, 8),
    "medium": (6, 15, 10, 30),
    "large": (20, 45, 40, 120),
}


def generate_program(
    rng: random.Random,
    idx: int,
    all_program_ids: list[str],
    all_copybook_ids: list[str],
) -> str:
    pgm_id = f"PGM{idx:05d}"
    bucket = size_bucket(rng)
    g_lo, g_hi, p_lo, p_hi = BUCKET_PARAMS[bucket]
    n_groups = rng.randint(g_lo, g_hi)
    n_paragraphs = rng.randint(p_lo, p_hi)

    other_programs = [p for p in all_program_ids if p != pgm_id]
    call_targets = rng.sample(other_programs, k=min(5, len(other_programs))) if other_programs else []
    copy_targets = rng.sample(all_copybook_ids, k=min(2, len(all_copybook_ids))) if all_copybook_ids else []

    lines = [
        f"{AREA_A}IDENTIFICATION DIVISION.",
        f"{AREA_A}PROGRAM-ID. {pgm_id}.",
        f"{AREA_A}DATA DIVISION.",
        f"{AREA_A}WORKING-STORAGE SECTION.",
    ]
    ws_lines, field_names = make_working_storage(rng, n_groups)
    lines.extend(ws_lines)

    for cpy in copy_targets:
        if rng.random() < 0.4:
            lines.append(f"{AREA_A}COPY {cpy} REPLACING ==PREFIX== BY =={pgm_id}==.")
        else:
            lines.append(f"{AREA_A}COPY {cpy}.")

    lines.append(f"{AREA_A}PROCEDURE DIVISION.")
    proc_lines, _ = make_paragraphs(rng, n_paragraphs, field_names, call_targets)
    lines.extend(proc_lines)

    return "\n".join(lines) + "\n"


def generate_copybook(rng: random.Random, idx: int) -> str:
    cpy_id = f"CPY{idx:05d}"
    lines = [f"{AREA_A}01  {cpy_id}-REC."]
    n_fields = rng.randint(3, 12)
    for _ in range(n_fields):
        fn = field_name(rng, "CB")
        lines.append(f"{AREA_B}05  {fn:<20}{pic_clause(rng)}.")
    lines.append(f"{AREA_B}05  :TAG:-STATUS       PIC X(2).")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("loadtest/synthetic-corpus"))
    ap.add_argument("--programs", type=int, default=1200)
    ap.add_argument("--copybooks", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--git-init", action="store_true", help="Ausgabe als Git-Repo committen (fuer den Git-Konnektor)")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    out = args.out
    programs_dir = out / "programs"
    copybooks_dir = out / "copybooks"
    programs_dir.mkdir(parents=True, exist_ok=True)
    copybooks_dir.mkdir(parents=True, exist_ok=True)

    program_ids = [f"PGM{i:05d}" for i in range(args.programs)]
    copybook_ids = [f"CPY{i:05d}" for i in range(args.copybooks)]

    total_bytes = 0
    total_lines = 0

    for i, cpy_id in enumerate(copybook_ids):
        text = generate_copybook(rng, i)
        path = copybooks_dir / f"{cpy_id}.cpy"
        path.write_text(text)
        total_bytes += len(text.encode())
        total_lines += text.count("\n")

    for i, pgm_id in enumerate(program_ids):
        text = generate_program(rng, i, program_ids, copybook_ids)
        path = programs_dir / f"{pgm_id}.cbl"
        path.write_text(text)
        total_bytes += len(text.encode())
        total_lines += text.count("\n")

    print(f"Erzeugt: {len(program_ids)} Programme, {len(copybook_ids)} Copybooks")
    print(f"Gesamt: {total_lines:,} Zeilen, {total_bytes / 1024 / 1024:.1f} MiB in {out}")

    if args.git_init:
        subprocess.run(["git", "init", "-q"], cwd=out, check=True)
        subprocess.run(["git", "-C", str(out), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(out), "-c", "user.email=loadtest@doctus.local", "-c", "user.name=AP-9 Lasttest",
             "commit", "-q", "-m", "Synthetischer AP-9-Lasttestkorpus"],
            check=True,
        )
        print(f"Git-Repo initialisiert unter {out}")


if __name__ == "__main__":
    main()
