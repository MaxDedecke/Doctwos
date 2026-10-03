#!/usr/bin/env python3
"""Fachliche Stichprobe der Java-Auflösung (O-309/O-352/O-366/O-367/O-368) gegen den Quelltext.

Zieht je Auflösungsgrund eine feste Zufallsstichprobe aufgelöster Kanten aus dem Index und prüft sie unabhängig
vom Resolver am Quelltext: (1) die Quellzeile enthält den Namen, (2) das Ziel heißt so, (3) bei Methoden passt die
Parameterzahl (Varargs berücksichtigt), (4) bei Receivern ist der im Quelltext deklarierte Typ das Ziel oder ein
Vorfahre davon (nur wenn eine Deklaration auffindbar ist, sonst „nicht prüfbar“).

Lauf im Backend-Container (liest Datenbank und Worktree):
    docker exec -w /app doctus-backend python /app/audit_java_resolution_sample.py SOURCE_ID [--per-reason 60]
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from core.db_setup import SessionLocal

WORKTREE = Path("/repos/wt")
_TYPE_TOKEN = re.compile(r"[A-Za-z_$][\w$]*")


def simple(name: str) -> str:
    return name.split("(", 1)[0].rsplit("#", 1)[-1].rsplit(".", 1)[-1]


def type_simple(declared: str) -> str:
    return _TYPE_TOKEN.findall(declared.split("<", 1)[0])[-1]


def ancestors(db, source_id: int, type_ids: set[int]) -> set[int]:
    seen, frontier = set(type_ids), set(type_ids)
    while frontier:
        rows = db.execute(text(
            "select dst_entity_id from code_edges where source_id=:s and type in ('EXTENDS','IMPLEMENTS') "
            "and resolution='resolved' and src_entity_id = any(:ids)"), {"s": source_id, "ids": list(frontier)}).all()
        frontier = {row[0] for row in rows if row[0]} - seen
        seen |= frontier
    return seen


def field_type(lines: list[str], name: str) -> str | None:
    pattern = re.compile(
        rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:private|protected|public|static|final|volatile|transient)\s+)+"
        rf"([A-Za-z_$][\w$.]*(?:<[^;(){{}}]*>)?)\s+{re.escape(name)}\s*[;=]")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1)
    return None


def declared_type(lines: list[str], line_no: int, name: str, prefer_field: bool = False) -> str | None:
    if prefer_field:
        found = field_type(lines, name)
        if found:
            return found
    pattern = re.compile(rf"([A-Za-z_$][\w$.]*(?:<[^;(){{}}]*>)?)\s+{re.escape(name)}\b\s*[;=,):]")
    for index in range(min(line_no, len(lines)) - 1, -1, -1):
        match = pattern.search(lines[index])
        if match and match.group(1) not in {"return", "new", "else", "throw", "case"}:
            return match.group(1)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id", type=int)
    parser.add_argument("--per-reason", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--show", type=int, default=6)
    args = parser.parse_args()
    db = SessionLocal()
    rows = db.execute(text("""
        select e.id, e.type, e.dst_name, e.meta_json::jsonb->>'resolution_reason' reason, e.src_start_line, e.dst_entity_id,
               s.file_path, s.id src_id, t.name tname, t.type ttype, t.parent_id tparent, t.meta_json::jsonb tmeta,
               e.meta_json::jsonb meta
        from code_edges e join code_entities s on s.id=e.src_entity_id join code_entities t on t.id=e.dst_entity_id
        where e.source_id=:s and e.resolution='resolved'
          and e.type in ('CALLS','REFERENCES_METHOD','READS','WRITES')
          and s.file_path not like '%/src/test/%'
        order by e.id"""), {"s": args.source_id}).mappings().all()
    buckets: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        buckets[(row["type"], row["reason"] or "-")].append(row)
    rng = random.Random(args.seed)
    cache: dict[str, list[str]] = {}
    summary, shown = {}, Counter()
    for key in sorted(buckets):
        sample = rng.sample(buckets[key], min(args.per_reason, len(buckets[key])))
        stats = Counter()
        for row in sample:
            path = WORKTREE / f"ks_{args.source_id}" / row["file_path"]
            if row["file_path"] not in cache:
                cache[row["file_path"]] = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
            lines = cache[row["file_path"]]
            meta = row["meta"] or {}
            name = meta.get("method_name") or simple(row["dst_name"])
            problems = []
            window = " ".join(lines[max(0, (row["src_start_line"] or 1) - 1):(meta.get("src_end_line") or row["src_start_line"] or 1) + 2])
            if not lines:
                stats["quelle_fehlt"] += 1
                continue
            if name not in window:
                problems.append("name_nicht_in_zeile")
            if row["type"] in {"CALLS", "REFERENCES_METHOD"} and simple(row["tname"]) not in {name, "<init>", simple(row["dst_name"])} \
                    and row["ttype"] != "constructor" and row["reason"] != "implicit_constructor_reference":
                problems.append("zielname_abweichend")
            if row["type"] == "CALLS" and row["ttype"] == "method":
                params = (row["tmeta"] or {}).get("parameter_types") or []
                given = meta.get("argument_count")
                varargs = any(str(p).endswith("...") or str(p).endswith("[]") for p in params[-1:])
                if given is not None and given != len(params) and not (varargs and given >= len(params) - 1):
                    problems.append("parameterzahl")
            receiver = meta.get("receiver")
            verified_receiver = None
            if row["reason"] in {"receiver_local_variable", "receiver_parameter", "receiver_field", "receiver_field_in_repository"} \
                    and receiver and re.fullmatch(r"[A-Za-z_$][\w$]*", receiver):
                declared = declared_type(lines, row["src_start_line"] or 1, receiver, row["reason"] in {"receiver_field", "receiver_field_in_repository"})
                if declared and declared != "var":
                    wanted = type_simple(declared)
                    owner = row["tparent"]
                    if owner:
                        names = db.execute(text("select id from code_entities where source_id=:s and name=:n and type in ('class','interface','enum','record','annotation_type')"),
                                           {"s": args.source_id, "n": wanted}).all()
                        reachable = ancestors(db, args.source_id, {n[0] for n in names}) if names else set()
                        verified_receiver = owner in reachable
                        if not verified_receiver:
                            problems.append(f"receivertyp:{wanted}")
            stats["geprueft"] += 1
            if problems:
                stats["abweichung"] += 1
                if shown[key] < args.show:
                    shown[key] += 1
                    print(f"  ABWEICHUNG {key} {row['file_path']}:{row['src_start_line']} {row['dst_name']} -> {row['tname']} {problems}")
            elif verified_receiver:
                stats["receiver_bestaetigt"] += 1
        summary[f"{key[0]}:{key[1]}"] = {"gesamt": len(buckets[key]), **stats}
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    total = sum(v.get("geprueft", 0) for v in summary.values())
    bad = sum(v.get("abweichung", 0) for v in summary.values())
    print(f"geprüft {total}, Abweichungen {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
