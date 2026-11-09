"""Erklärung einer Entität: wer sie nutzt, ihre für die Frage relevanten Teile, Quelltext und Ablauf.

Genutzt von explain_symbol und dem Belegpaket (aus mcp_server.py herausgelöst).
"""

import logging
import json
import re

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from api import entities as entity_api
from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    User,
)
from services.source_access import numbered as _numbered
from services.source_access import source_visible as _source_visible


from services.code_symbols import (
    _compact_entity,
)
from services.call_flow_page import (
    _call_flow_page,
    _data_access_summary,
    _flow_summary,
    _outline,
)

logger = logging.getLogger(__name__)


_USED_BY_TYPES = [
    "CALL",
    "CALLS",
    "DISPATCHES_TO",
    "PERFORM",
    "GOTO",
    "COPY",
    "EXTENDS",
    "IMPLEMENTS",
    "INSTANTIATES",
    "REFERENCES_METHOD",
]


def _used_by(db: Session, user: User, entity: CodeEntity, limit: int = 12) -> list[dict]:
    """Source units that reference this entity (callers, COPY users, subclasses); overloads count together."""
    dst_ids = [entity.id]
    if (
        entity.type in {"method", "constructor"}
        and entity.qualified_name
        and "(" in entity.qualified_name
    ):
        prefix = entity.qualified_name.split("(", 1)[0] + "("
        dst_ids += [
            row.id
            for row in db.query(CodeEntity.id)
            .filter(
                CodeEntity.project_id == entity.project_id,
                CodeEntity.type.in_(["method", "constructor"]),
                CodeEntity.qualified_name.like(prefix + "%"),
                ~CodeEntity.qualified_name.like("%@%"),
                CodeEntity.id != entity.id,
            )
            .limit(20)
            .all()
        ]
    rows = (
        db.query(CodeEdge, CodeEntity)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.project_id == entity.project_id,
            CodeEdge.type.in_(_USED_BY_TYPES),
            or_(
                CodeEdge.dst_entity_id.in_(dst_ids),
                and_(CodeEdge.dst_entity_id.is_(None), CodeEdge.dst_name == entity.name),
            ),
        )
        .order_by(CodeEntity.file_path, CodeEdge.src_start_line)
        .limit(400)
        .all()
    )
    visible: dict[int | None, bool] = {}
    units: dict[str, dict] = {}
    for edge, src in rows:
        if src.source_id not in visible:
            visible[src.source_id] = _source_visible(db, user, src.source_id)
        if not visible[src.source_id] or src.file_path == entity.file_path:
            continue
        unit = units.setdefault(
            src.file_path,
            {
                "unit": (src.file_path or "").rsplit("/", 1)[-1].rsplit(".", 1)[0],
                "file": src.file_path,
                "types": [],
                "lines": [],
                "resolution": edge.resolution,
            },
        )
        if edge.type not in unit["types"]:
            unit["types"].append(edge.type)
        if edge.src_start_line and len(unit["lines"]) < 3:
            unit["lines"].append(edge.src_start_line)
    items = list(units.values())
    return items[:limit] if limit else items


_SYMBOL_PATTERNS = [
    # COBOL: Programm.Absatz (`COPAUA0C.MAIN-PARA`, `COPAUA0C.1000-INITIALIZE`) und Absatznamen mit führender Zahl.
    re.compile(r"\b[A-Z][A-Z0-9]*\.[0-9A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),
    re.compile(r"\b[0-9]{2,5}-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b"),
    re.compile(r"\b[A-Za-z_$][\w$]*(?:[.#][A-Za-z_$][\w$]*)+(?:\(\))?"),
    re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),
    re.compile(r"\b[A-Z]{2,}[0-9][A-Z0-9]*\b"),
    re.compile(r"\b[A-Z][A-Z0-9]{4,}\b"),
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[A-Z]{2,}[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)*\b"),
    re.compile(r"\b[\w./-]+\.(?:cbl|cpy|java|xml)\b", re.I),
]
_NOT_SYMBOLS = {
    "z.b",
    "d.h",
    "u.a",
    "usw",
    "bzw",
    "e.g",
    "i.e",
    "etc",
    "cobol",
    "batch",
    "vsam",
    "cics",
    "json",
    "sql",
    "java",
    "http",
    "https",
}


def _extract_symbols(question: str) -> list[str]:
    """Names that look like code symbols in free text, in order of appearance, longest forms first."""
    found: list[tuple[int, str]] = []
    for pattern in _SYMBOL_PATTERNS:
        for match in pattern.finditer(question):
            term = match.group(0).rstrip(".,;:").removesuffix("()")
            if len(term) >= 4 and term.casefold() not in _NOT_SYMBOLS:
                found.append((match.start(), term))
    found.sort(key=lambda item: (item[0], -len(item[1])))
    terms: list[str] = []
    for _pos, term in found:
        key = term.casefold()
        if any(key == t.casefold() or key in t.casefold() for t in terms):
            continue
        terms = [t for t in terms if t.casefold() not in key] + [term]
    return terms[:8]


_CHILD_SKIP = {"section", "constructor"}
_HOUSEKEEPING = re.compile(
    r"OPEN|CLOSE|ABEND|DISPLAY-IO|IO-STATUS|TIMESTAMP|INIT-|^Z-|ERROR-", re.I
)
_DE_EN = {
    "ablehn": "reject fail invalid error",
    "zins": "interest rate",
    "datei": "dataset",
    "gelesen": "read",
    "lies": "read",
    "geschrieb": "write",
    "schreib": "write",
    "berechn": "compute calc",
    "anmeld": "signon login auth",
    "benutz": "user",
    "konto": "acct account",
    "karte": "card xref",
    "transakt": "tran transaction",
    "summe": "total",
    "bericht": "report rept",
    "menü": "menu",
    "menue": "menu",
    "prüf": "valid check edit lookup",
    "pruef": "valid check edit lookup",
    "validier": "valid check lookup",
    "formel": "compute calc",
    "buchung": "post write tran tx",
    "aktualis": "update",
    "anleg": "add create",
    "lösch": "delete",
    "sperr": "suspend lock",
    "passwort": "password pwd",
    "fehler": "error fail",
    "buch": "post",
    "weiterleit": "xctl link",
    "aufruf": "call",
    "authentifiz": "authenticate auth",
    "ausnahme": "exception",
    "regel": "rule policy",
    "richtlinie": "policy",
    "benachricht": "notification notify",
    "aufgabe": "task job",
    "erzeug": "create build",
    "gruppe": "group",
}


_GENERIC_WORDS = {
    "nenne",
    "nennen",
    "welche",
    "welcher",
    "welches",
    "welchen",
    "wird",
    "werden",
    "wurde",
    "batch",
    "programm",
    "programme",
    "program",
    "datei",
    "dateien",
    "file",
    "files",
    "nach",
    "ende",
    "eine",
    "einer",
    "einen",
    "dass",
    "beschreibe",
    "erkläre",
    "erklaere",
    "gelesenen",
    "geschrieben",
    "angepasst",
    "carddemo",
    "syncope",
    "apache",
    "cobol",
    "java",
    "klasse",
    "methode",
    "funktion",
    "ablauf",
    "läuft",
    "laeuft",
    "wenn",
    "oder",
    "sowie",
    "dabei",
    "dafür",
    "dafuer",
    "sich",
    "nicht",
    "ihre",
    "ihrer",
    "alle",
    "wann",
    "womit",
    "wozu",
}


def _question_stems(question: str) -> set[str]:
    """First five letters of the question words plus English code words for common German terms."""
    lowered = question.lower()
    stems = {t[:5] for t in re.findall(r"[a-zäöüß0-9]{4,}", lowered) if t not in _GENERIC_WORDS}
    for german, english in _DE_EN.items():
        if german in lowered:
            stems |= {t[:5] for t in english.split()}
    return stems


def _relevant_children(question: str, outline: list[dict], count: int = 6, sims=None) -> list[dict]:
    """Outline entries that cover the question: greedy by word overlap (names count double, already covered words
    do not count again), orchestration and embedding similarity as extras, then one step along PERFORM."""
    q_stems = _question_stems(question)
    entries = []
    for position, item in enumerate(outline):
        if item.get("type") in _CHILD_SKIP:
            continue
        tail = re.split(r"[.#]", item["symbol"].split("(", 1)[0])[-1]
        facts = item.get("facts", "")
        plain_facts = re.sub(
            r"(?:^|; )(?:calls|performs|cics|datasets|io|computes|sets|msgs) ", " ", facts
        )
        name_tokens = {
            t[:5] for t in re.findall(r"[a-zäöüß0-9]{3,}", tail.lower().replace("-", " "))
        }
        fact_tokens = {
            t[:5] for t in re.findall(r"[a-zäöüß0-9]{3,}", plain_facts.lower().replace("-", " "))
        }
        name_hit = q_stems & name_tokens
        fact_hit = (q_stems & fact_tokens) - name_hit
        # A paragraph or method that drives many others (PERFORM/CALL fan-out) usually carries the main flow.
        fan_out = facts.count(",") + (1 if facts else 0)
        base = min(3, fan_out // 3)
        if re.search(r"MAIN|PROCESS|EXECUTE|RUN", tail.upper()):
            base += 1
        if "xctl" in facts.lower() or "link" in facts.lower():
            if re.search(
                r"gestartet|startet|weiterleit|aufruf|weiter|programm|ruft", question.lower()
            ):
                base += 2
        if _HOUSEKEEPING.search(tail) and not _HOUSEKEEPING.search(question):
            base -= 3
        entries.append(
            {"item": item, "pos": position, "name": name_hit, "fact": fact_hit, "base": base}
        )
    if sims is not None and entries:
        preliminary = sorted(
            entries, key=lambda e: -(2 * len(e["name"]) + len(e["fact"]) + e["base"])
        )[:12]
        similarity = sims([e["item"] for e in preliminary]) or {}
        for entry in preliminary:
            entry["base"] += 8.0 * max(0.0, similarity.get(entry["item"]["symbol"], 0.0))
    covered: set[str] = set()
    chosen: list[dict] = []
    remaining = list(entries)
    while remaining and len(chosen) < count:

        def gain(e: dict) -> float:
            return 2 * len(e["name"] - covered) + len(e["fact"] - covered) + e["base"]

        best = max(remaining, key=lambda e: (gain(e), -e["pos"]))
        if gain(best) <= 0:
            break
        chosen.append(best["item"])
        covered |= best["name"] | best["fact"]
        remaining.remove(best)
    if not chosen:
        chosen = [e["item"] for e in entries[:count]]
    # One step further along the PERFORM chain: the paragraph a best match hands over to often holds the rest of the
    # answer (e.g. the posting written by the computation paragraph).
    by_tail = {
        re.split(r"[.#]", i["symbol"].split("(", 1)[0])[-1].upper(): i
        for i in outline
        if i.get("type") not in _CHILD_SKIP
    }
    extras: list[dict] = []
    for item in chosen[:2]:
        performed = re.search(r"performs ([^;]*)", item.get("facts", ""))
        for name in performed.group(1).split(", ") if performed else []:
            target = by_tail.get(name.strip().upper())
            if (
                target
                and target not in chosen
                and target not in extras
                and not _HOUSEKEEPING.search(name)
            ):
                extras.append(target)
    return (chosen + extras)[: count + 1]


def _explain_entity(
    db: Session,
    user: User,
    project_id: int,
    entity: CodeEntity,
    others: list[CodeEntity],
    mode: str,
    symbol: str,
    max_chars: int,
    start_line: int | None,
    end_line: int | None,
    *,
    with_context: bool = True,
    used_by_limit: int = 12,
    compact: bool = False,
) -> dict:
    """Source (or outline for large entities), callees, callers, data access and users of one entity."""
    low = start_line if start_line is not None else entity.start_line or 1
    high = end_line if end_line is not None else entity.end_line or 10**9
    pieces: list[tuple[int, str]] = []
    for chunk in entity_api._definition_chunks(
        entity, db, start_line=start_line, end_line=end_line
    ):
        first, last = max(low, chunk.start_line), min(high, chunk.end_line)
        if first > last:
            continue
        lines = chunk.content.splitlines()
        pieces.append(
            (first, "\n".join(lines[first - chunk.start_line : last - chunk.start_line + 1]))
        )
    source_budget = int(max_chars * (0.65 if with_context else 0.92))
    total_chars = sum(len(text) for _first, text in pieces)
    outline = None
    source = None
    if start_line is None and end_line is None and total_chars > source_budget:
        outline = _outline(db, entity)
    if not outline:
        outline = None
        parts, used, truncated, next_line, last_delivered = [], 0, False, None, None
        for first, text in pieces:
            room = source_budget - used
            if room <= 0:
                truncated, next_line = True, first
                break
            clipped = text[:room]
            if len(clipped) < len(text):
                clipped = clipped[: clipped.rfind("\n")] if "\n" in clipped else clipped
                truncated = True
            parts.append(_numbered(clipped, first, compact))
            used += len(clipped)
            last_delivered = first + max(0, len(clipped.splitlines()) - 1)
            if truncated:
                next_line = last_delivered + 1
                break
        source = {
            "start_line": pieces[0][0] if pieces else entity.start_line,
            "end_line": last_delivered if last_delivered is not None else entity.end_line,
            "text": "\n".join(parts),
            "truncated": truncated,
            "next_start_line": next_line,
        }
    response = {
        "project_id": project_id,
        "symbol": symbol,
        "resolution": "unique_exact_match"
        if mode == "exact" and not others
        else ("overloads" if others else "fuzzy"),
        "entity": _compact_entity(entity),
    }
    if source is not None:
        response["source"] = source
    else:
        kept, size = [], 0
        for item in outline:
            size += len(json.dumps(item, ensure_ascii=False))
            if size > max_chars and kept:
                break
            kept.append(item)
        response["outline"] = kept
        if len(kept) < len(outline):
            response["outline_omitted"] = len(outline) - len(kept)
        response["notice"] = (
            "Source not inlined (larger than the budget). Call explain_symbol with one outline symbol."
        )
    if source is not None and with_context:
        try:
            callees = _flow_summary(
                _call_flow_page(
                    db,
                    user,
                    project_id,
                    entity.id,
                    hops=1,
                    direction="outgoing",
                    scope="execution",
                    page_size=12,
                    cursor=None,
                    include_source=False,
                ),
                "outgoing",
            )
            callers = _flow_summary(
                _call_flow_page(
                    db,
                    user,
                    project_id,
                    entity.id,
                    hops=1,
                    direction="incoming",
                    scope="execution",
                    page_size=8,
                    cursor=None,
                    include_source=False,
                ),
                "incoming",
                8,
            )
        except (ValueError, HTTPException):
            callees, callers = [], []
        if callees:
            response["callees"] = callees
        if callers:
            response["callers"] = callers
        access = _data_access_summary(db, entity)
        if access:
            response["data_access"] = access
    if with_context:
        used_by = _used_by(db, user, entity, used_by_limit)
        if used_by:
            response["used_by"] = used_by
    if others:
        response["other_matches"] = [_compact_entity(e) for e in others[:6]]
    if source is not None and source["truncated"] and source["next_start_line"]:
        response["follow_up_actions"] = [
            {
                "tool": "explain_symbol",
                "arguments": {
                    "project_id": project_id,
                    "symbol": entity.qualified_name,
                    "start_line": source["next_start_line"],
                    "end_line": entity.end_line,
                    "max_chars": max_chars,
                },
                "reason": "Continue reading the rest of this symbol.",
            }
        ]
    return response
